// Trading chrome: theme toggle, NYSE market-status badge, and the ticker strip.
//
// Honesty: every price Graha has is end-of-day / daily-scan data, not a live
// feed, so the strip says "as of <time> · daily scan" instead of animating like
// a live tape.

// ---------- theme toggle ----------
function currentTheme() { return document.documentElement.getAttribute("data-theme") || "dark"; }

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
    btn.setAttribute("aria-label", label);
    btn.title = label;
  }
}

function wireThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  applyTheme(currentTheme());
  btn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("graha-theme", next); } catch (_) { /* storage blocked: still switches for this visit */ }
  });
  // Until the user picks explicitly, follow the operating system.
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", (e) => {
      let saved = null;
      try { saved = localStorage.getItem("graha-theme"); } catch (_) { /* ignore */ }
      if (!saved) applyTheme(e.matches ? "light" : "dark");
    });
  }
}

// ---------- NYSE market status ----------
let marketCalendar = null;

async function loadMarketCalendar() {
  try {
    const res = await fetch("market-calendar.json", { cache: "no-cache" });
    if (res.ok) marketCalendar = await res.json();
  } catch (_) { /* badge degrades to weekday-only logic */ }
}

function _etParts(date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour12: false, weekday: "short",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).formatToParts(date).reduce((o, p) => { o[p.type] = p.value; return o; }, {});
  return {
    iso: `${parts.year}-${parts.month}-${parts.day}`,
    weekday: parts.weekday,
    minutes: (Number(parts.hour) % 24) * 60 + Number(parts.minute),
  };
}

function _isTradingDay(iso, weekday) {
  if (weekday === "Sat" || weekday === "Sun") return false;
  return !(marketCalendar && marketCalendar.holidays.includes(iso));
}

// Returns {state: "open"|"pre"|"after"|"closed", label}
function marketStatus(now = new Date()) {
  const et = _etParts(now);
  const trading = _isTradingDay(et.iso, et.weekday);
  const early = !!(marketCalendar && marketCalendar.early_closes.includes(et.iso));
  const OPEN = 9 * 60 + 30, CLOSE = (early ? 13 : 16) * 60, PRE = 4 * 60, AFTER = 20 * 60;
  if (trading) {
    if (et.minutes >= OPEN && et.minutes < CLOSE) return { state: "open", label: `NYSE open · closes ${early ? "1:00" : "4:00"}pm ET` };
    if (et.minutes >= PRE && et.minutes < OPEN) return { state: "extended", label: "Pre-market · opens 9:30am ET" };
    if (et.minutes >= CLOSE && et.minutes < AFTER) return { state: "extended", label: "After hours · closed" };
  }
  return { state: "closed", label: "NYSE closed" };
}

function renderMarketStatus() {
  const el = document.getElementById("market-status");
  if (!el) return;
  const s = marketStatus();
  el.className = `market-status ${s.state === "open" ? "open" : (s.state === "extended" ? "extended" : "")}`;
  el.innerHTML = `<span class="dot"></span>${escapeHtml(s.label)}`;
}

// ---------- ticker strip (sector funds from the daily scan) ----------
const TAPE_ORDER = ["US_Broad", "Technology", "Financials", "Energy", "Healthcare", "Industrials", "Materials_Mining",
  "Consumer_Discretionary", "Consumer_Staples", "Utilities", "Real_Estate", "Communication_Media", "Gold", "Silver", "Canada_Broad"];

function renderTickerTape() {
  const el = document.getElementById("ticker-tape");
  if (!el) return;
  const rows = (dataCache.recentPredictions || []).filter(p => p.price_at_prediction != null);
  const bySector = {};
  for (const p of rows) (bySector[p.sector] = bySector[p.sector] || []).push(p);   // newest first
  const items = [];
  let asOf = null;
  const seen = new Set();
  const tapeItem = (tk, now, pct) => `<span class="tape-item"><span class="tk">${escapeHtml(tk)}</span><span class="px">${now.toFixed(2)}</span>
      ${pct === null || pct === undefined ? "" : `<span class="${pct >= 0 ? "bullish" : "bearish"}">${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(2)}%</span>`}</span>`;
  // Broad-market funds first (market_snapshot, sector "Index"), newest date only.
  const snap = dataCache.marketSnapshot || [];
  const idxDate = (snap.find(r => r.sector === "Index") || {}).date;
  for (const tk of ["SPY", "QQQ", "DIA", "IWM"]) {
    const r = snap.find(x => x.sector === "Index" && x.ticker === tk && x.date === idxDate);
    if (!r) continue;
    seen.add(tk);
    items.push(tapeItem(tk, Number(r.price), r.percent_change === null ? null : Number(r.percent_change)));
    if (r.created_at && (!asOf || r.created_at > asOf)) asOf = r.created_at;
  }
  for (const sector of TAPE_ORDER) {
    const list = bySector[sector];
    if (!list || !list.length || seen.has(list[0].ticker)) continue;
    const now = Number(list[0].price_at_prediction);
    const prev = list.find(p => p.date < list[0].date);
    const pct = prev ? (now - Number(prev.price_at_prediction)) / Number(prev.price_at_prediction) * 100 : null;
    if (!asOf || (list[0].created_at && list[0].created_at > asOf)) asOf = list[0].created_at || asOf;
    items.push(tapeItem(list[0].ticker, now, pct));
  }
  if (!items.length) { el.hidden = true; return; }
  el.hidden = false;
  const stamp = asOf ? new Date(asOf).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "";
  el.innerHTML = items.join("") + `<span class="tape-asof">Sector funds · daily scan${stamp ? " · " + stamp : ""} · not live</span>`;
}

document.addEventListener("DOMContentLoaded", async () => {
  wireThemeToggle();
  await loadMarketCalendar();
  renderMarketStatus();
  setInterval(renderMarketStatus, 30000);
});
