// Sends the welcome email on signup. Triggered by a Supabase Database
// Webhook on `profiles` INSERT (configured once, manually, in the
// Supabase dashboard -- see the deploy notes in the repo for the exact
// steps) rather than a client-side "call this after signup succeeds" --
// a webhook fires server-side regardless of what the browser does next,
// where a client-triggered call is skippable by an aborted/refreshed page
// load or a client that just doesn't bother calling it.
//
// verify_jwt is OFF for this function (see supabase/config.toml) --
// it's service-to-service, invoked by the database, not a signed-in
// browser, so there's no user JWT to verify. That means Supabase's
// platform-level gateway does NOT gate this URL at all -- it is a public
// endpoint by default. The x-webhook-secret check below, matched against
// an Edge Function secret only this project's webhook config knows, is
// the ONLY thing stopping this from being a public URL anyone could POST
// to as an open mail relay against the project's Resend sending
// reputation. It is checked FIRST, before anything else runs.
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY");
const WEBHOOK_SHARED_SECRET = Deno.env.get("WEBHOOK_SHARED_SECRET");
// Resend's shared onboarding@resend.dev sender works without a verified
// domain, but (Resend's own restriction, not this project's) can only
// actually deliver to the email address on the Resend account itself
// until a real sending domain is verified. Once a domain's verified,
// set WELCOME_EMAIL_FROM (e.g. "Graha <welcome@yourdomain.com>") as an
// Edge Function secret to switch over -- no code change needed.
const FROM_EMAIL = Deno.env.get("WELCOME_EMAIL_FROM") || "Graha <onboarding@resend.dev>";

function welcomeEmailHtml(): string {
  return `
  <div style="font-family: 'Georgia', serif; max-width: 560px; margin: 0 auto; color: #211e1b;">
    <h1 style="font-size: 22px; margin-bottom: 4px;">Welcome to Graha</h1>
    <p style="color: #6b625a; margin-top: 0;">Astro Trading Platform</p>
    <p>Your account is live. Graha reads real planetary positions every trading day and turns them into sector and stock signals -- plainly explained, with the underlying astrological reasoning always one click away if you want it.</p>
    <p>A few things waiting for you on the dashboard:</p>
    <ul>
      <li><strong>This Week's Signals</strong> -- today's sector-by-sector read, in plain English.</li>
      <li><strong>Astro Signals</strong> -- every individual stock Graha has ever suggested, tracked start to finish.</li>
      <li><strong>Graha 2.0</strong> -- your own automated paper-trading account, seeded with $20,000 in simulated cash (resettable any time from the Graha 2.0 tab).</li>
      <li><strong>Ask Graha</strong> -- ask it anything about how the platform works, or about your own signals, trades, and portfolio.</li>
    </ul>
    <p style="color: #6b625a; font-size: 12px; margin-top: 32px;">This is a simulated, educational, astrology-based signal system -- not licensed financial advice. All trading in Graha 2.0 is simulated money.</p>
  </div>`;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "Method not allowed." }, 405);

  const providedSecret = req.headers.get("x-webhook-secret");
  if (!WEBHOOK_SHARED_SECRET || providedSecret !== WEBHOOK_SHARED_SECRET) {
    return json({ error: "unauthorized" }, 401);
  }

  if (!RESEND_API_KEY) {
    console.error("send-welcome-email: RESEND_API_KEY not configured");
    return json({ error: "email not configured" }, 503);
  }

  let payload: { record?: { email?: string } };
  try {
    payload = await req.json();
  } catch {
    return json({ error: "invalid payload" }, 400);
  }

  const email = payload?.record?.email;
  if (!email) return json({ error: "no email in payload" }, 400);

  try {
    const resendRes = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM_EMAIL,
        to: email,
        subject: "Welcome to Graha — Astro Trading Platform",
        html: welcomeEmailHtml(),
      }),
    });

    if (!resendRes.ok) {
      console.error("Resend send failed:", resendRes.status, await resendRes.text());
      return json({ error: "send failed" }, 502);
    }

    return json({ ok: true });
  } catch (e) {
    console.error("send-welcome-email error:", e);
    return json({ error: "send failed" }, 500);
  }
});
