const dataCache = { latestPredictions: [], portfolio: [], paperAccount: null, recentTrades: [], weeklyReviews: [] };

async function loadAll() {
  const [latestLog, predictions, portfolio, paperAccount, recentTrades, weeklyReviews] = await Promise.all([
    SB.select("planetary_log", "order=date.desc&limit=1"),
    SB.select("predictions", "order=date.desc&limit=40"),
    SB.select("portfolio", "order=created_at.desc"),
    SB.select("paper_account", "limit=1"),
    SB.select("paper_trades", "order=created_at.desc&limit=15"),
    SB.select("weekly_reviews", "order=week_start.desc&limit=4"),
  ]);

  dataCache.latestPredictions = dedupeLatestPerSector(predictions);
  dataCache.portfolio = portfolio;
  dataCache.paperAccount = paperAccount[0] || null;
  dataCache.recentTrades = recentTrades;
  dataCache.weeklyReviews = weeklyReviews;

  if (latestLog[0]) renderZodiacWheel(document.getElementById("orrery-container"), latestLog[0].positions);
  renderSectorCards();
  renderPortfolio();
  renderPaperTrading();
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

function renderSectorCards() {
  const el = document.getElementById("sector-grid");
  const preds = dataCache.latestPredictions;
  if (!preds.length) { el.innerHTML = `<p class="empty-note">No signals logged yet — the daily job runs automatically on market days, or trigger it manually from the repo's Actions tab.</p>`; return; }
  el.innerHTML = preds.map(p => `
    <div class="sector-card ${p.direction}">
      <div class="sector-card-top">
        <span class="sector-name">${p.sector.replace(/_/g, " ")}</span>
        <span class="sector-ticker">${p.ticker}</span>
      </div>
      <div class="sector-direction ${p.direction}">${p.direction} · ${p.possibility_indicator}%</div>
      <div class="possibility-bar-track"><div class="possibility-bar-fill" style="width:${p.possibility_indicator}%"></div></div>
      <div class="sector-reason">${(p.reasons || []).slice(0, 2).join(" · ")}</div>
    </div>
  `).join("");
}

function renderPortfolio() {
  const el = document.getElementById("portfolio-list");
  const rows = dataCache.portfolio;
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No holdings added yet.</p>`; return; }
  el.innerHTML = rows.map(r => `
    <div class="holding">
      <div>
        <div>${r.ticker} <span class="holding-meta">× ${r.quantity}</span></div>
        <div class="holding-meta">bought $${r.buy_price} · ${r.buy_date} · ${r.exchange}</div>
      </div>
      <button class="ghost" onclick="removeHolding(${r.id})">remove</button>
    </div>
  `).join("");
}

function renderPaperTrading() {
  const cashEl = document.getElementById("paper-cash");
  const listEl = document.getElementById("paper-trades");
  cashEl.textContent = dataCache.paperAccount ? `$${Number(dataCache.paperAccount.cash).toLocaleString(undefined, {maximumFractionDigits:2})}` : "—";
  const trades = dataCache.recentTrades;
  if (!trades.length) { listEl.innerHTML = `<p class="empty-note">No trades yet — the bot only enters when a sector's possibility indicator clears its threshold.</p>`; return; }
  listEl.innerHTML = trades.map(t => `
    <div class="trade-row">
      <span class="trade-action ${t.action}">${t.action}</span> ${t.quantity} ${t.ticker} @ $${t.price} <span class="holding-meta">${t.trade_date}</span>
      ${t.pnl != null ? `<span class="holding-meta"> · P&L $${t.pnl} (${t.pnl_pct}%)</span>` : ""}
      <div class="trade-reasoning">${t.reasoning}</div>
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
  div.innerHTML = `<span class="role">${role === "user" ? "you" : "agent"}</span>${text.replace(/\n/g, "<br>")}`;
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
