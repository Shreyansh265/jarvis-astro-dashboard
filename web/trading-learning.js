// Paper Trading tab (ledger, equity, month-to-date progress) and Learning
// tab (rule confidence, mistakes, weekly review history).

const MONTHLY_TARGET_PCT = 15;

function renderPaperTrading() {
  const acct = dataCache.paperAccount;
  const history = dataCache.equityHistory;
  const latest = history.length ? history[history.length - 1] : null;
  const cash = acct ? Number(acct.cash) : null;
  const totalEquity = latest ? Number(latest.total_equity) : cash;

  document.getElementById("paper-cash").textContent =
    cash != null ? `$${cash.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—";
  document.getElementById("paper-equity").textContent =
    totalEquity != null ? `$${totalEquity.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—";

  let mtdPct = null;
  if (latest) {
    const currentMonth = latest.date.slice(0, 7);
    const monthStartRow = history.find(r => r.date.slice(0, 7) === currentMonth);
    if (monthStartRow && Number(monthStartRow.total_equity)) {
      mtdPct = Math.round(((totalEquity - monthStartRow.total_equity) / monthStartRow.total_equity) * 10000) / 100;
    }
  }
  const mtdEl = document.getElementById("paper-mtd");
  mtdEl.textContent = mtdPct != null ? `${mtdPct >= 0 ? "+" : ""}${mtdPct}%` : "—";
  mtdEl.className = "stat-value" + (mtdPct != null ? (mtdPct >= 0 ? " bullish" : " bearish") : "");

  const fillPct = mtdPct != null ? Math.max(0, Math.min(100, (mtdPct / MONTHLY_TARGET_PCT) * 100)) : 0;
  document.getElementById("goal-track-fill").style.width = `${fillPct}%`;

  const trades = dataCache.recentTrades;
  const listEl = document.getElementById("paper-trades");
  if (!trades.length) {
    listEl.innerHTML = `<p class="empty-note">No trades yet — Graha only enters when a sector's possibility indicator clears its threshold, in either direction.</p>`;
    return;
  }
  listEl.innerHTML = trades.map(t => `
    <div class="trade-row">
      <span class="trade-action ${t.action}">${t.action}</span>
      <span class="holding-meta">${t.position_type || "long"}</span>
      ${t.quantity} ${t.ticker} @ $${t.price} <span class="holding-meta">${t.trade_date}</span>
      ${t.pnl != null ? `<span class="holding-meta ${t.pnl >= 0 ? "bullish" : "bearish"}"> · P&L $${t.pnl} (price move ${t.pnl_pct}%)</span>` : ""}
      <div class="trade-reasoning">${t.reasoning}</div>
    </div>
  `).join("");
}

function renderOpenPositions() {
  const el = document.getElementById("open-positions");
  const trades = dataCache.recentTrades;
  const opens = {};
  // Reconstructed from the loaded trade window (most recent 50) -- a
  // position opened outside that window won't show here, but the ledger
  // below still carries the full recent history either way.
  [...trades].reverse().forEach(t => {
    if (t.action === "BUY" || t.action === "SHORT") opens[t.id] = t;
    else if ((t.action === "SELL" || t.action === "COVER") && opens[t.linked_buy_trade_id]) delete opens[t.linked_buy_trade_id];
  });
  const rows = Object.values(opens);
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No open positions right now.</p>`; return; }
  el.innerHTML = rows.map(t => `
    <div class="holding">
      <div>
        <div>${t.ticker} <span class="holding-meta">${t.position_type || "long"} × ${t.quantity}</span></div>
        <div class="holding-meta">opened $${t.price} · ${t.trade_date} · ${t.sector.replace(/_/g, " ")}</div>
      </div>
    </div>
  `).join("");
}

function renderEquitySparkline() {
  const el = document.getElementById("equity-sparkline");
  const history = dataCache.equityHistory;
  if (history.length < 2) { el.innerHTML = `<p class="empty-note">Not enough equity history yet for a chart.</p>`; return; }
  const values = history.map(r => Number(r.total_equity));
  const min = Math.min(...values), max = Math.max(...values);
  const w = 600, h = 80, pad = 4;
  const range = (max - min) || 1;
  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const trendUp = values[values.length - 1] >= values[0];
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" class="sparkline ${trendUp ? "bullish" : "bearish"}" preserveAspectRatio="none">
    <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" />
  </svg>`;
}

function renderRuleWeights() {
  const el = document.getElementById("rule-weights-list");
  const rows = dataCache.ruleWeights;
  if (!rows.length) { el.innerHTML = `<p class="empty-note">Graha hasn't learned anything yet — check back after the first review runs.</p>`; return; }
  el.innerHTML = rows.map(r => `
    <div class="weight-row">
      <span class="weight-planet">${r.planet}</span>
      <div class="possibility-bar-track weight-bar"><div class="possibility-bar-fill" style="width:${Math.round(r.weight * 100)}%"></div></div>
      <span class="holding-meta">${Math.round(r.weight * 100)}% · ${r.correct_count}✓ / ${r.incorrect_count}✗</span>
    </div>
  `).join("");
}

function renderMistakes() {
  const el = document.getElementById("mistakes-list");
  const rows = dataCache.mistakes;
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No misses on record yet — either everything's held up so far, or nothing's old enough to verify.</p>`; return; }
  el.innerHTML = rows.map(p => `
    <div class="review-item">
      <div class="review-summary">${p.sector.replace(/_/g, " ")} (${p.ticker}) — predicted ${p.direction} at ${p.possibility_indicator}%, actually went ${p.outcome_direction} (${p.outcome_pct_change}%)</div>
      <div class="review-lesson">Graha remembers: ${(p.contributing_planets || []).join(", ") || "no single planet"} had its confidence adjusted because of this.</div>
    </div>
  `).join("");
}

function renderWeeklyReviews() {
  const el = document.getElementById("review-strip");
  const reviews = dataCache.weeklyReviews;
  if (!reviews.length) { el.innerHTML = `<p class="empty-note">No weekly review yet — runs automatically every Sunday.</p>`; return; }
  el.innerHTML = reviews.map(r => `
    <div class="review-item">
      <div class="review-summary">${r.summary}</div>
      ${(r.lessons || []).slice(0, 3).map(l => `<div class="review-lesson">${l.reason_it_missed || JSON.stringify(l)}</div>`).join("")}
    </div>
  `).join("");
}
