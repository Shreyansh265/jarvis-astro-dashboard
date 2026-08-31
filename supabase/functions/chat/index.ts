// "Ask Graha" -- a genuinely LLM-backed chat (Claude, via the Anthropic API),
// replacing the earlier pattern-matching ChatEngine. This function exists at
// all because a static GitHub Pages frontend can't hold ANTHROPIC_API_KEY
// without exposing it to every visitor -- this is the one place in the whole
// project's history that needed a real live backend (everything else has
// been GitHub Actions batch jobs).
//
// Security shape (see Epic 4 plan for the full reasoning):
//   - verify_jwt stays on (this function's default) -- Supabase's own
//     gateway rejects any request without a valid signed-in user's JWT
//     before this code even runs.
//   - The Supabase client below is built from the ANON key + the caller's
//     OWN forwarded JWT, never the service_role key -- every context read
//     (predictions, portfolio, paper trades) is RLS-scoped exactly like a
//     normal browser request would be. A bug in this function's own query
//     logic still can't leak another user's data, because the database
//     enforces that boundary regardless.
//   - is_banned is checked explicitly, before any Anthropic spend --
//     RLS on the personal tables stops a banned user from reading/writing
//     their OWN rows, but it knows nothing about this function as a
//     separate trust boundary, and a ban should also stop someone from
//     continuing to spend the project's Anthropic budget.
//   - A simple per-user hourly rate cap (counting the caller's own
//     chat_log rows, RLS-scoped) sits in front of the Anthropic call too.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// SUPABASE_URL / SUPABASE_ANON_KEY are auto-injected into every Supabase
// Edge Function -- not something this project set manually.
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY");

const MODEL = "claude-sonnet-5";
const MAX_USER_MESSAGES_PER_HOUR = 30;
const MAX_MESSAGE_LEN = 2000;

const SYSTEM_PROMPT = `You are Graha, the AI assistant for an astrology-based stock/sector trading dashboard -- imagine a market analyst who's spent 17 years reading planetary transits against real price action: warm, direct, never breathlessly hyped. You can answer anything about how this platform works -- This Week's Signals, Astro Signals (individual stock picks), Graha 2.0 (the automated paper-trading bot, its reset button, its strategy), the Portfolio tracker, QQQ Analysis, how the daily astrology-to-signal pipeline works, what "possibility indicator" or "confidence" mean -- as well as questions about the specific signals/trades/portfolio data given to you below.

Ground rules, followed strictly:
- Only state facts that are either in the JSON data block you're given, or are true about how this platform generally works. If you don't know something or it isn't in your data, say so plainly instead of guessing.
- Never invent a specific stock pick, price, trade, or news event that isn't in the data provided.
- This is a simulated, educational, astrology-based signal system -- not licensed financial advice. If asked for direct "should I buy X" advice, answer using the platform's own signals/data where relevant, and be clear this isn't personalized financial advice from a licensed advisor.
- Keep answers focused and readable: a few short paragraphs or a tight list, not a wall of text, unless the question genuinely needs more.`;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (req.method !== "POST") return json({ error: "Method not allowed." }, 405);

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) return json({ error: "Not signed in." }, 401);

    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: { headers: { Authorization: authHeader } },
    });

    const { data: { user }, error: userErr } = await supabase.auth.getUser();
    if (userErr || !user) return json({ error: "Not signed in." }, 401);

    const { data: isBanned } = await supabase.rpc("current_user_is_banned");
    if (isBanned) return json({ error: "This account has been suspended." }, 403);

    let body: { message?: unknown };
    try {
      body = await req.json();
    } catch {
      return json({ error: "Invalid request body." }, 400);
    }
    const message = typeof body.message === "string" ? body.message.trim() : "";
    if (!message) return json({ error: "Empty message." }, 400);
    if (message.length > MAX_MESSAGE_LEN) {
      return json({ error: `Message is too long (${MAX_MESSAGE_LEN} character limit).` }, 400);
    }

    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const { count } = await supabase
      .from("chat_log")
      .select("id", { count: "exact", head: true })
      .eq("role", "user")
      .gte("created_at", oneHourAgo);
    if ((count ?? 0) >= MAX_USER_MESSAGES_PER_HOUR) {
      return json({ error: "You've hit the hourly chat limit for this account -- try again in a bit." }, 429);
    }

    if (!ANTHROPIC_API_KEY) {
      return json({
        error: "Ask Graha isn't fully switched on yet -- the site owner still needs to add an Anthropic API key.",
      }, 503);
    }

    // Every read below rides the same RLS-scoped client (caller's own JWT).
    // predictions/horizon_picks are shared/public-read; portfolio,
    // paper_account, paper_trades are this caller's own rows only.
    const [predictionsRes, portfolioRes, paperAccountRes, tradesRes, horizonRes] = await Promise.all([
      supabase.from("predictions").select("sector,ticker,direction,possibility_indicator,reasons,plain_language_note")
        .order("date", { ascending: false }).limit(20),
      supabase.from("portfolio").select("ticker,quantity,buy_price,buy_date,status,sell_price,sell_date")
        .order("created_at", { ascending: false }).limit(30),
      supabase.from("paper_account").select("cash").maybeSingle(),
      supabase.from("paper_trades").select("ticker,action,position_type,quantity,price,trade_date,pnl,pnl_pct,reasoning")
        .order("created_at", { ascending: false }).limit(20),
      supabase.from("horizon_picks").select("period_start,period_end,sector,ticker,rank,summary")
        .order("period_start", { ascending: false }).limit(10),
    ]);

    const context = {
      recent_sector_predictions: predictionsRes.data ?? [],
      users_own_portfolio: portfolioRes.data ?? [],
      users_own_paper_trading_cash: paperAccountRes.data?.cash ?? null,
      users_own_recent_paper_trades: tradesRes.data ?? [],
      recent_best_of_the_best_horizon_picks: horizonRes.data ?? [],
    };

    const anthropicRes = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 800,
        system: SYSTEM_PROMPT,
        messages: [{
          role: "user",
          content: `Data available to you (real, from Graha's own signal history and this user's own account -- nothing else is real; don't invent tickers, prices, or news beyond this):\n${JSON.stringify(context)}\n\nUser's question: ${message}`,
        }],
      }),
    });

    if (!anthropicRes.ok) {
      console.error("Anthropic API error:", anthropicRes.status, await anthropicRes.text());
      return json({ error: "Graha's brain is temporarily unavailable -- try again in a moment." }, 502);
    }

    const anthropicData = await anthropicRes.json();
    const reply = (anthropicData.content ?? [])
      .filter((b: { type: string }) => b.type === "text")
      .map((b: { text: string }) => b.text)
      .join("")
      .trim() || "Graha didn't have anything to say -- try rephrasing your question.";

    return json({ reply });
  } catch (e) {
    console.error("chat function error:", e);
    return json({ error: "Something went wrong on Graha's end." }, 500);
  }
});
