// Escapes untrusted third-party text (e.g. news headlines from Finnhub)
// before it's interpolated into an innerHTML template string elsewhere in
// this file -- cheaper than restructuring every render function to safe
// DOM construction, and sufficient for content that's just displayed
// inline, not treated as trusted markup.
function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
// Refuses to render a link href unless it's actually http(s) -- blocks a
// javascript: or data: URI smuggled in through third-party news data.
function safeHttpUrl(url) {
  try {
    const u = new URL(url, window.location.href);
    return (u.protocol === "http:" || u.protocol === "https:") ? u.href : "#";
  } catch (_) {
    return "#";
  }
}

const dataCache = {
  latestLog: null,
  latestPredictions: [],
  portfolio: [],
  paperAccount: null,
  recentTrades: [],
  suggestedStocks: [],
  marketSnapshot: [],
  dailyBrief: null,
  equityHistory: [],
  horizonPicks: [],
  stockDetails: [],
  stockWatch: null,
  sectorForecast: [],
  forecastDays: [],
  sectorUniverse: [],
  sectorWatch: [],
  weeklyPicks: [],
  portfolioPrices: [],
  analogCache: {},
};

// New-feature tables get their own .catch so a not-yet-applied schema or an
// empty table can never reject the shared Promise.all and blank the dashboard.
function softSelect(table, query) {
  return SB.select(table, query).catch(() => []);
}

function daysAgoISO(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

async function loadAll() {
  const marketSnapshotSince = daysAgoISO(120);
  const [
    latestLog, predictions, portfolio, paperAccount, recentTrades,
    suggestedStocks, marketSnapshot, dailyBriefs, equityHistory,
    horizonPicks, stockDetails, stockWatch,
    sectorForecast, forecastDays, sectorUniverse, sectorWatch, weeklyPicks, portfolioPrices, analogRows,
  ] = await Promise.all([
    SB.select("planetary_log", "order=date.desc&limit=1"),
    SB.select("predictions", "order=date.desc,created_at.desc&limit=40"),
    SB.select("portfolio", "order=created_at.desc"),
    SB.select("paper_account", "limit=1"),
    SB.select("paper_trades", "order=created_at.desc&limit=50"),
    // Full history now (not just is_active=true) -- Astro Signals shows
    // every past pick, not only currently-tracked ones. Bounded so this
    // doesn't grow unbounded forever.
    SB.select("suggested_stocks", "order=date_suggested.desc&limit=300"),
    // Widened window (was just the latest day) so Astro Signals/Portfolio
    // can look up a price near an older suggestion/removal date, not just today.
    SB.select("market_snapshot", `date=gte.${marketSnapshotSince}&order=date.desc&limit=5000`),
    SB.select("daily_briefs", "order=date.desc&limit=1"),
    SB.select("equity_history", "order=date.asc&limit=90"),
    SB.select("horizon_picks", "order=period_start.desc,rank.asc&limit=60"),
    // Latest row per ticker is enough for "view details" -- bounded, not
    // full history (there's no need to keep every past day's snapshot
    // loaded client-side for this).
    SB.select("stock_detail", "order=detail_date.desc&limit=200"),
    // RLS already scopes this to just the caller's own row -- limit=1 is
    // a safety cap, same as paper_account above, not a real filter.
    SB.select("stock_watch", "limit=1"),
    softSelect("sector_forecast", `forecast_date=gte.${mondayOf(todayUtc())}&order=forecast_date.asc&limit=1000`),
    softSelect("forecast_days", `forecast_date=gte.${mondayOf(todayUtc())}&order=forecast_date.asc&limit=100`),
    softSelect("sector_universe", "order=sector.asc,ticker.asc&limit=500"),
    softSelect("sector_watch", "order=added_at.asc"),
    softSelect("weekly_picks", "order=week_start.desc,rank.asc&limit=200"),
    softSelect("portfolio_prices", "limit=500"),
    softSelect("analog_cache", "limit=500"),
  ]);

  dataCache.latestLog = latestLog[0] || null;
  dataCache.latestPredictions = dedupeLatestPerSector(predictions);
  dataCache.portfolio = portfolio;
  dataCache.paperAccount = paperAccount[0] || null;
  dataCache.recentTrades = recentTrades;
  dataCache.suggestedStocks = suggestedStocks;
  dataCache.marketSnapshot = marketSnapshot;
  dataCache.dailyBrief = dailyBriefs[0] || null;
  dataCache.equityHistory = equityHistory;
  dataCache.horizonPicks = horizonPicks;
  dataCache.stockDetails = stockDetails;
  dataCache.stockWatch = stockWatch[0] || null;
  dataCache.sectorForecast = sectorForecast;
  dataCache.forecastDays = forecastDays;
  dataCache.sectorUniverse = sectorUniverse;
  dataCache.sectorWatch = sectorWatch;
  dataCache.weeklyPicks = weeklyPicks;
  dataCache.portfolioPrices = portfolioPrices;
  dataCache.analogCache = Object.fromEntries(analogRows.map(r => [r.key, r.payload]));

  // Dashboard tab
  renderBrief();
  renderMovers();
  renderPortfolioPreview();
  renderPoisedToRise();
  renderTrackRecord();

  // This Week's Signals tab
  if (dataCache.latestLog) renderZodiacWheel(document.getElementById("orrery-container"), dataCache.latestLog.positions);
  renderWeekTab();
  renderAspects();

  // Astro Signals tab
  renderStockWatch();
  renderHorizonPicks();
  renderAstroStocks();

  // Portfolio tab
  renderPortfolioTable();

  // Backtest tab
  renderBacktestTab();

  // Graha 2.0 tab
  renderPaperTrading();
  renderOpenPositions();
  renderEquitySparkline();

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

// Latest known price for a ticker, with the date it's "as of". Prefers whichever
// source is newer: portfolio_prices (written post-close by portfolio_detail.py
// for every holding, curated or not) or market_snapshot (pre-market scan of the
// curated watchlist, effectively the prior close). Never fetched live.
function _priceInfoFor(ticker) {
  const pp = (dataCache.portfolioPrices || []).find(r => r.ticker === ticker);
  const snap = dataCache.marketSnapshot.find(r => r.ticker === ticker); // date.desc -> first is latest
  if (pp && (!snap || pp.as_of >= snap.date)) return { price: Number(pp.price), asOf: pp.as_of };
  if (snap) return { price: Number(snap.price), asOf: snap.date };
  return null;
}
function _latestPriceFor(ticker) {
  const info = _priceInfoFor(ticker);
  return info ? info.price : null;
}
function renderPortfolioPreview() {
  const el = document.getElementById("portfolio-preview");
  const rows = dataCache.portfolio.filter(r => r.status !== "closed");
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No open holdings yet — add one from the Portfolio tab, or use the "+ portfolio" buttons on the gainers/losers above.</p>`; return; }
  let totalCost = 0, totalNow = 0, priced = 0, newest = null;
  const lines = rows.slice(0, 6).map(r => {
    const info = _priceInfoFor(r.ticker);
    const cost = Number(r.buy_price) * Number(r.quantity);
    let pnlHtml = `<span class="holding-meta">price not available yet</span>`;
    if (info) {
      const now = info.price * Number(r.quantity), pnl = now - cost;
      pnlHtml = `<span class="${pnl >= 0 ? "bullish" : "bearish"}">${pnl >= 0 ? "+" : "-"}$${Math.abs(pnl).toFixed(2)} (${pnl >= 0 ? "+" : ""}${(pnl / cost * 100).toFixed(2)}%)</span>`;
    }
    return `<div class="holding">
      <div>
        <div>${escapeHtml(r.ticker)} <span class="holding-meta">× ${r.quantity}</span></div>
        <div class="holding-meta">bought $${r.buy_price} · now ${info ? "$" + info.price.toFixed(2) : "—"}</div>
      </div>
      <div>${pnlHtml}</div>
    </div>`;
  }).join("");
  for (const r of rows) {
    const info = _priceInfoFor(r.ticker);
    if (!info) continue;
    priced++;
    totalCost += Number(r.buy_price) * Number(r.quantity);
    totalNow += info.price * Number(r.quantity);
    if (!newest || info.asOf > newest) newest = info.asOf;
  }
  const total = totalNow - totalCost;
  el.innerHTML = lines + (priced
    ? `<div class="portfolio-total"><span>Total open P&amp;L${priced < rows.length ? ` (${priced} of ${rows.length} priced)` : ""}</span>
         <strong class="${total >= 0 ? "bullish" : "bearish"}">${total >= 0 ? "+" : "-"}$${Math.abs(total).toFixed(2)} (${totalCost ? (total >= 0 ? "+" : "") + (total / totalCost * 100).toFixed(2) : "0.00"}%)</strong></div>
       <div class="holding-meta">Prices as of ${newest} (daily scan, not live)</div>`
    : "") + (rows.length > 6 ? `<div class="holding-meta">+ ${rows.length - 6} more in the Portfolio tab</div>` : "");
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
        <button class="ghost" data-view-detail="${r.ticker}">details</button>
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
  tbody.querySelectorAll("[data-view-detail]").forEach(btn => {
    btn.addEventListener("click", () => openStockDetail(btn.dataset.viewDetail));
  });
}

// ---------- Stock detail modal ----------
function openStockDetail(ticker) {
  const backdrop = document.getElementById("stock-detail-backdrop");
  const content = document.getElementById("stock-detail-content");
  const detail = dataCache.stockDetails.find(d => d.ticker === ticker);

  if (!detail) {
    // Real dead-zone, not an edge case to discover in QA: a ticker added
    // to the portfolio today hasn't been through a post-close
    // portfolio_detail.py run yet.
    content.innerHTML = `
      <h2>${ticker}</h2>
      <p class="empty-note">Details compute after tonight's run (portfolio_detail.py runs post-market-close). Check back tomorrow.</p>`;
    backdrop.hidden = false;
    return;
  }

  const newsAsOf = detail.news_as_of ? new Date(detail.news_as_of).toLocaleString() : "—";
  const newsItems = detail.news || [];
  content.innerHTML = `
    <h2>${detail.ticker}</h2>
    <div class="holding-meta">as of ${detail.detail_date}</div>

    <div class="detail-section">
      <h3>Technical</h3>
      <div class="detail-stats-row">
        <div class="stat-tile"><div class="stat-label">SMA 20</div><div class="stat-value">${detail.sma_20 ?? "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">SMA 50</div><div class="stat-value">${detail.sma_50 ?? "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">RSI 14</div><div class="stat-value">${detail.rsi_14 ?? "—"}</div></div>
      </div>
      <div class="holding-meta">52-week range: ${detail.week52_low ?? "—"} – ${detail.week52_high ?? "—"}</div>
    </div>

    <div class="detail-section">
      <h3>Financial</h3>
      <div class="detail-stats-row">
        <div class="stat-tile"><div class="stat-label">P/E</div><div class="stat-value">${detail.pe_ratio ?? "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">Market Cap</div><div class="stat-value">${detail.market_cap != null ? "$" + Number(detail.market_cap).toLocaleString() : "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">Profit Margin</div><div class="stat-value">${detail.profit_margin != null ? Math.round(detail.profit_margin * 1000) / 10 + "%" : "—"}</div></div>
      </div>
    </div>

    <div class="detail-section">
      <h3>Macro / Sector Context</h3>
      <div class="empty-note movers-note">Grounded in this ticker's sector signal, not a real geopolitical event feed.</div>
      ${detail.sector ? `<div class="sector-direction ${detail.sector_direction}">${detail.sector.replace(/_/g, " ")} — ${detail.sector_direction} (${detail.sector_possibility_indicator}%)</div>
        <div class="sector-reason">${(detail.sector_reasons || []).join(" · ")}</div>
        ${detail.long_term_note ? `<div class="long-term-note">${detail.long_term_note}</div>` : ""}` : `<p class="empty-note">No sector context available for this ticker.</p>`}
    </div>

    <div class="detail-section">
      <h3>Recent News</h3>
      <div class="holding-meta">as of ${newsAsOf}</div>
      ${newsItems.length ? newsItems.map(n => `
        <div class="news-item">
          <a href="${escapeHtml(safeHttpUrl(n.url))}" target="_blank" rel="noopener">${escapeHtml(n.headline)}</a>
          <div class="holding-meta">${escapeHtml(n.source || "")}</div>
        </div>
      `).join("") : `<p class="empty-note">No recent news available.</p>`}
    </div>
  `;
  backdrop.hidden = false;
}

function closeStockDetail() {
  document.getElementById("stock-detail-backdrop").hidden = true;
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

  let reply;
  try {
    reply = await ChatEngine.ask(text);
  } catch (err) {
    // Network/auth/rate-limit/not-yet-configured errors from the chat
    // Edge Function all land here -- shown in the log, not written to
    // chat_log (it's not a real reply from Graha).
    appendChatMsg("agent", err.message || "Something went wrong reaching Graha — try again in a moment.");
    return;
  }
  appendChatMsg("agent", reply);
  try { await SB.insert("chat_log", { role: "agent", message: reply }); } catch (_) {}
}

function appendChatMsg(role, text) {
  // Built via safe DOM methods (textContent, not innerHTML string
  // interpolation) -- chat messages are user-authored, and once Ask
  // Graha is LLM-backed, agent replies are free-form generated text too.
  // Neither should ever be treated as trusted HTML.
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;

  const roleSpan = document.createElement("span");
  roleSpan.className = "role";
  roleSpan.textContent = role === "user" ? "you" : "graha";
  div.appendChild(roleSpan);

  const lines = String(text).split("\n");
  lines.forEach((line, i) => {
    div.appendChild(document.createTextNode(line));
    if (i < lines.length - 1) div.appendChild(document.createElement("br"));
  });

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
  document.getElementById("stock-detail-close").addEventListener("click", closeStockDetail);
  document.getElementById("stock-detail-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "stock-detail-backdrop") closeStockDetail();
  });
  // loadAll()/loadChatHistory() are no longer called here -- the whole
  // dashboard is gated behind sign-in now (see auth-gate.js), which
  // calls them itself only once a real session (and non-banned account)
  // is confirmed.
});
