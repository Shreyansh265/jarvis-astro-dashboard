const dataCache = {
  latestLog: null,
  latestPredictions: [],
  portfolio: [],
  paperAccount: null,
  recentTrades: [],
  weeklyReviews: [],
  suggestedStocks: [],
  marketSnapshot: [],
  dailyBrief: null,
  ruleWeights: [],
  equityHistory: [],
  mistakes: [],
};

function daysAgoISO(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

async function loadAll() {
  const marketSnapshotSince = daysAgoISO(120);
  const [
    latestLog, predictions, portfolio, paperAccount, recentTrades, weeklyReviews,
    suggestedStocks, marketSnapshot, dailyBriefs, ruleWeights, equityHistory, mistakes,
  ] = await Promise.all([
    SB.select("planetary_log", "order=date.desc&limit=1"),
    SB.select("predictions", "order=date.desc,created_at.desc&limit=40"),
    SB.select("portfolio", "order=created_at.desc"),
    SB.select("paper_account", "limit=1"),
    SB.select("paper_trades", "order=created_at.desc&limit=50"),
    SB.select("weekly_reviews", "order=week_start.desc&limit=6"),
    // Full history now (not just is_active=true) -- Astro Signals shows
    // every past pick, not only currently-tracked ones. Bounded so this
    // doesn't grow unbounded forever.
    SB.select("suggested_stocks", "order=date_suggested.desc&limit=300"),
    // Widened window (was just the latest day) so Astro Signals/Portfolio
    // can look up a price near an older suggestion/removal date, not just today.
    SB.select("market_snapshot", `date=gte.${marketSnapshotSince}&order=date.desc&limit=5000`),
    SB.select("daily_briefs", "order=date.desc&limit=1"),
    SB.select("rule_weights", "order=weight.desc"),
    SB.select("equity_history", "order=date.asc&limit=90"),
    SB.select("predictions", "was_correct=eq.false&order=date.desc&limit=8"),
  ]);

  dataCache.latestLog = latestLog[0] || null;
  dataCache.latestPredictions = dedupeLatestPerSector(predictions);
  dataCache.portfolio = portfolio;
  dataCache.paperAccount = paperAccount[0] || null;
  dataCache.recentTrades = recentTrades;
  dataCache.weeklyReviews = weeklyReviews;
  dataCache.suggestedStocks = suggestedStocks;
  dataCache.marketSnapshot = marketSnapshot;
  dataCache.dailyBrief = dailyBriefs[0] || null;
  dataCache.ruleWeights = ruleWeights;
  dataCache.equityHistory = equityHistory;
  dataCache.mistakes = mistakes;

  // Overview tab
  renderBrief();
  renderMovers();
  renderPortfolioPreview();
  renderPicksPreview();

  // This Week's Signals tab
  if (dataCache.latestLog) renderZodiacWheel(document.getElementById("orrery-container"), dataCache.latestLog.positions);
  renderSectorCards();
  renderAspects();

  // Astro Signals tab
  renderAstroStocks();

  // Portfolio tab
  renderPortfolioTable();

  // Graha 2.0 tab
  renderPaperTrading();
  renderOpenPositions();
  renderEquitySparkline();

  // Learning tab
  renderRuleWeights();
  renderMistakes();
  renderWeeklyReviews();
}

function dedupeLatestPerSector(predictions) {
  const seen = new Set();
  const out = [];
  for (const p of predictions) {
    if (!seen.has(p.sector)) { seen.add(p.sector); out.push(p); }
  }
  return out;
}

function renderBrief() {
  const el = document.getElementById("eli5-brief");
  if (!dataCache.dailyBrief) {
    el.innerHTML = `<p class="empty-note">Graha hasn't written today's brief yet — check back after the daily job runs.</p>`;
    return;
  }
  el.textContent = dataCache.dailyBrief.brief_text;
}

function renderMovers() {
  const rows = dataCache.marketSnapshot;
  const gainersEl = document.getElementById("gainers-list");
  const losersEl = document.getElementById("losers-list");
  if (!rows.length) {
    gainersEl.innerHTML = `<p class="empty-note">No market watch data yet.</p>`;
    losersEl.innerHTML = `<p class="empty-note">No market watch data yet.</p>`;
    return;
  }
  const latestDate = rows[0].date;
  const today = rows.filter(r => r.date === latestDate && r.percent_change != null);
  const gainers = [...today].sort((a, b) => b.percent_change - a.percent_change).slice(0, 5);
  const losers = [...today].sort((a, b) => a.percent_change - b.percent_change).slice(0, 5);

  const rowHtml = r => `
    <div class="mover-row">
      <span class="mover-ticker">${r.ticker}</span>
      <span class="holding-meta">${(r.sector || "").replace(/_/g, " ")}</span>
      <span class="mover-pct ${r.percent_change >= 0 ? "bullish" : "bearish"}">${r.percent_change >= 0 ? "+" : ""}${r.percent_change}%</span>
      <span class="holding-meta">$${r.price}</span>
      <button class="ghost" data-add-ticker="${r.ticker}" data-add-price="${r.price}">+ portfolio</button>
    </div>`;

  gainersEl.innerHTML = gainers.length ? gainers.map(rowHtml).join("") : `<p class="empty-note">No gainers today.</p>`;
  losersEl.innerHTML = losers.length ? losers.map(rowHtml).join("") : `<p class="empty-note">No losers today.</p>`;

  document.querySelectorAll("[data-add-ticker]").forEach(btn => {
    btn.addEventListener("click", async () => {
      await SB.insert("portfolio", { ticker: btn.dataset.addTicker, buy_price: parseFloat(btn.dataset.addPrice), quantity: 1, exchange: "NYSE" });
      await loadAll();
    });
  });
}

function renderPicksPreview() {
  const el = document.getElementById("picks-preview");
  const rows = dataCache.suggestedStocks.filter(r => r.is_active).slice(0, 4);
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No active picks right now.</p>`; return; }
  el.innerHTML = rows.map(r => `
    <div class="pick-preview-row">
      <span class="mover-ticker">${r.ticker}</span>
      <span class="sector-direction ${r.direction}">${r.direction}</span>
      <span class="holding-meta">${(r.sector || "").replace(/_/g, " ")}</span>
    </div>
  `).join("");
}

function _latestPriceFor(ticker) {
  const hit = dataCache.marketSnapshot.find(r => r.ticker === ticker);
  return hit ? Number(hit.price) : null; // marketSnapshot is ordered date.desc, so first match is latest
}

function renderPortfolioPreview() {
  const el = document.getElementById("portfolio-preview");
  const rows = dataCache.portfolio.filter(r => r.status !== "closed").slice(0, 4);
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No open holdings yet.</p>`; return; }
  el.innerHTML = rows.map(r => `
    <div class="holding">
      <div>
        <div>${r.ticker} <span class="holding-meta">× ${r.quantity}</span></div>
        <div class="holding-meta">bought $${r.buy_price} · ${r.buy_date}</div>
      </div>
    </div>
  `).join("");
}

function renderPortfolioTable() {
  const tbody = document.getElementById("portfolio-table-body");
  const rows = dataCache.portfolio;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-note">No holdings added yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const isOpen = r.status !== "closed";
    const currentOrSell = isOpen ? _latestPriceFor(r.ticker) : Number(r.sell_price);
    const pnl = (currentOrSell != null) ? (currentOrSell - r.buy_price) * r.quantity : null;
    const pnlPct = (currentOrSell != null && r.buy_price) ? Math.round(((currentOrSell - r.buy_price) / r.buy_price) * 10000) / 100 : null;
    return `
    <tr class="${pnl == null ? "" : (pnl >= 0 ? "row-bullish" : "row-bearish")}">
      <td>${r.ticker}</td>
      <td>${r.exchange}</td>
      <td>${r.quantity}</td>
      <td>${r.buy_date}</td>
      <td>$${r.buy_price}</td>
      <td>${currentOrSell != null ? "$" + currentOrSell : "—"}</td>
      <td>${r.sell_date || "—"}</td>
      <td class="${pnl == null ? "" : (pnl >= 0 ? "bullish" : "bearish")}">${pnl != null ? `$${pnl.toFixed(2)} (${pnlPct}%)` : "—"}</td>
      <td><span class="status-badge ${isOpen ? "open" : "closed"}">${isOpen ? "open" : "closed"}</span></td>
      <td>
        ${isOpen ? `<button class="ghost" data-sell-holding="${r.id}">sell</button>` : ""}
        <button class="ghost" data-remove-holding="${r.id}">remove</button>
      </td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll("[data-sell-holding]").forEach(btn => {
    btn.addEventListener("click", () => sellHolding(Number(btn.dataset.sellHolding)));
  });
  tbody.querySelectorAll("[data-remove-holding]").forEach(btn => {
    btn.addEventListener("click", () => removeHolding(Number(btn.dataset.removeHolding)));
  });
}

// ---------- Portfolio actions ----------
async function addHolding(e) {
  e.preventDefault();
  const ticker = document.getElementById("f-ticker").value.trim().toUpperCase();
  const price = parseFloat(document.getElementById("f-price").value);
  const qty = parseFloat(document.getElementById("f-qty").value) || 1;
  const exchange = document.getElementById("f-exchange").value;
  if (!ticker || !price) return;
  await SB.insert("portfolio", { ticker, buy_price: price, quantity: qty, exchange });
  document.getElementById("add-holding-form").reset();
  await loadAll();
}

async function sellHolding(id) {
  const priceStr = prompt("Sell price ($)?");
  if (priceStr === null) return;
  const sellPrice = parseFloat(priceStr);
  if (!sellPrice) return;
  const dateStr = prompt("Sell date (YYYY-MM-DD)?", new Date().toISOString().slice(0, 10)) || new Date().toISOString().slice(0, 10);
  // Selling PATCHes status/sell_price/sell_date instead of deleting the row,
  // so the trade stays in history -- "remove" (hard delete) is only for
  // correcting a mis-entered holding, not for closing a real position.
  await SB.update("portfolio", `id=eq.${id}`, { status: "closed", sell_price: sellPrice, sell_date: dateStr });
  await loadAll();
}

async function removeHolding(id) {
  await SB.del("portfolio", `id=eq.${id}`);
  await loadAll();
}

// ---------- Chat ----------
async function sendChat(e) {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  appendChatMsg("user", text);
  try { await SB.insert("chat_log", { role: "user", message: text }); } catch (_) {}

  const reply = await ChatEngine.ask(text, dataCache);
  appendChatMsg("agent", reply);
  try { await SB.insert("chat_log", { role: "agent", message: reply }); } catch (_) {}
}

function appendChatMsg(role, text) {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = `<span class="role">${role === "user" ? "you" : "graha"}</span>${text.replace(/\n/g, "<br>")}`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function loadChatHistory() {
  try {
    const rows = await SB.select("chat_log", "order=created_at.asc&limit=30");
    rows.forEach(r => appendChatMsg(r.role, r.message));
  } catch (_) {}
}

function tickClock() {
  document.getElementById("clock").textContent = new Date().toUTCString().replace(" GMT", " UTC");
}

document.addEventListener("DOMContentLoaded", () => {
  tickClock();
  setInterval(tickClock, 1000);
  document.getElementById("add-holding-form").addEventListener("submit", addHolding);
  document.getElementById("chat-form").addEventListener("submit", sendChat);
  loadAll();
  loadChatHistory();
});
