// Graha: a template/pattern-matching Q&A engine voiced as a 17-year astro
// trading veteran, NOT a free-form LLM. Every answer is generated from real
// rows in Supabase (predictions, trades, reviews), so Graha can't hallucinate
// a stock pick that isn't backed by a logged signal. "Memory" = the full
// chat_log + underlying data tables, which every answer can reference.

const ChatEngine = {
  async ask(userText, dataCache) {
    const text = userText.toLowerCase();

    if (/track record|accuracy|how (are you|is it) doing|been (right|wrong)/.test(text)) {
      return ChatEngine._answerAccuracy(dataCache);
    }
    if (/paper trad|bot|simulat/.test(text)) {
      return ChatEngine._answerPaperTrading(dataCache);
    }
    if (/portfolio|my stocks|my holdings/.test(text)) {
      return ChatEngine._answerPortfolio(dataCache);
    }
    if (/why.*(bullish|bearish|pick|choose|buy|sell)/.test(text) || /reason/.test(text)) {
      return ChatEngine._answerReasoning(text, dataCache);
    }
    if (/this week|sector|predict|outlook|bullish|bearish/.test(text)) {
      return ChatEngine._answerOutlook(dataCache);
    }
    if (/mistake|wrong|learn|improve/.test(text)) {
      return ChatEngine._answerLessons(dataCache);
    }
    return ChatEngine._help();
  },

  _answerOutlook(cache) {
    const preds = cache.latestPredictions || [];
    if (!preds.length) return "Nothing logged yet — the daily job runs on market days and will populate this. Check back after it fires.";
    const bullish = preds.filter(p => p.direction === "bullish").sort((a,b) => b.possibility_indicator - a.possibility_indicator);
    const bearish = preds.filter(p => p.direction === "bearish").sort((a,b) => b.possibility_indicator - a.possibility_indicator);
    let out = "**Here's how the sky reads today:**\n\n";
    if (bullish.length) out += "Bullish: " + bullish.slice(0,5).map(p => `${p.sector} (${p.ticker}, ${p.possibility_indicator}% confidence)`).join(", ") + "\n\n";
    if (bearish.length) out += "Bearish: " + bearish.slice(0,5).map(p => `${p.sector} (${p.ticker}, ${p.possibility_indicator}% confidence)`).join(", ");
    return out || "Quiet day — nothing strong enough either way to call out.";
  },

  _answerReasoning(text, cache) {
    const preds = cache.latestPredictions || [];
    const match = preds.find(p =>
      text.includes(p.sector.toLowerCase().replace(/_/g, " ")) || text.includes(p.ticker.toLowerCase())
    );
    if (!match) return "Tell me which sector or ticker you mean (e.g. \"why is Financials bearish?\") and I'll pull up the exact reasoning behind the call.";
    return `**${match.sector} (${match.ticker})** — ${match.direction}, ${match.possibility_indicator}% possibility indicator.\n\nGraha's read: ${match.reasons.join("; ")}\n\nContributing planets: ${match.contributing_planets.join(", ")}`;
  },

  _answerPaperTrading(cache) {
    const acct = cache.paperAccount;
    const trades = cache.recentTrades || [];
    if (!acct) return "Graha 2.0 hasn't been initialized yet.";
    let out = `**Graha 2.0** — cash: $${Number(acct.cash).toLocaleString()}\n\n`;
    if (!trades.length) { out += "No trades yet — nothing's cleared the confidence bar in either direction."; return out; }
    out += "Recent trades:\n" + trades.slice(0, 8).map(t =>
      `${t.trade_date} — ${t.action} ${t.quantity} ${t.ticker} (${t.position_type || "long"}) @ $${t.price}${t.pnl != null ? ` (P&L $${t.pnl})` : ""} — ${t.reasoning}`
    ).join("\n");
    return out;
  },

  _answerPortfolio(cache) {
    const rows = cache.portfolio || [];
    if (!rows.length) return "Your portfolio is empty. Add a stock using the Portfolio panel (ticker + price you bought it at) and I'll keep track of it.";
    return "**Your portfolio:**\n" + rows.map(r =>
      `${r.ticker} — ${r.quantity} @ $${r.buy_price} (bought ${r.buy_date}, ${r.exchange})`
    ).join("\n");
  },

  _answerAccuracy(cache) {
    const reviews = cache.weeklyReviews || [];
    if (!reviews.length) return "No weekly review has run yet — check back after the first Sunday review job. I review my own calls every day now, too, not just on Sundays.";
    const latest = reviews[0];
    return `**Latest weekly review** (${latest.week_start} → ${latest.week_end}):\n${latest.summary}`;
  },

  _answerLessons(cache) {
    const reviews = cache.weeklyReviews || [];
    if (!reviews.length) return "Nothing logged yet — this fills in after the first weekly review. See the Learning tab for the mistakes I've caught day-to-day in the meantime.";
    const lessons = (reviews[0].lessons || []).slice(0, 5);
    if (!lessons.length) return "Last week had no misses to learn from — every logged prediction matched the actual price direction.";
    return "**What I got wrong last week, and what I'm adjusting:**\n\n" + lessons.map(l => `• ${l.reason_it_missed}`).join("\n\n");
  },

  _help() {
    return "I'm Graha — ask me about this week's sector outlook, why a specific sector/stock is bullish or bearish, my paper trading bot's trades, your portfolio, or the accuracy/lessons from my reviews. Try one of those.";
  },
};
