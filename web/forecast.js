// This Week's Signals tab: a day-by-day sector outlook the user customizes
// (whole sectors or a specific stock inside one), plus helpers the Dashboard's
// "Sectors Poised to Rise" section reuses.
//
// Honesty rules baked into the rendering:
//  * Most sector conditions last weeks and only the Moon + aspects change
//    day to day, so a steady week is shown as "steady", not five fake-
//    distinct cards -- and the sky events that DO change are listed first.
//  * A stock inherits its sector's forecast. There is no per-stock
//    astrology, so stock rows carry a badge saying so and no separate
//    confidence number.
//  * "No astrological signal" (including Silver, which has no rule at all)
//    is its own state, never drawn as a flat neutral forecast.

const SECTOR_GROUPS = [
  { label: "Commodities", sectors: ["Gold", "Silver", "Energy", "Materials_Mining"] },
  { label: "Information Technology", sectors: ["Technology"] },
  { label: "Financials", sectors: ["Financials"] },
  { label: "Healthcare", sectors: ["Healthcare"] },
  { label: "Industrials", sectors: ["Industrials"] },
  { label: "Consumer", sectors: ["Consumer_Discretionary", "Consumer_Staples"] },
  { label: "Real Estate & Utilities", sectors: ["Real_Estate", "Utilities"] },
  { label: "Media & Communication", sectors: ["Communication_Media"] },
  { label: "Broad Markets", sectors: ["US_Broad", "Canada_Broad"] },
];

const SECTOR_LABEL = {
  Gold: "Gold", Silver: "Silver", Energy: "Crude Oil & Energy", Materials_Mining: "Metals & Mining",
  Technology: "Information Technology", Financials: "Financials", Healthcare: "Healthcare",
  Industrials: "Industrials", Consumer_Discretionary: "Consumer Spending",
  Consumer_Staples: "Everyday Essentials", Real_Estate: "Real Estate", Utilities: "Utilities",
  Communication_Media: "Media & Communication", US_Broad: "US Market", Canada_Broad: "Canada",
};

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const weekState = { offset: null, selected: null, pickSector: null, pickQuery: "", etfCache: {} };

function sectorLabel(sector) { return SECTOR_LABEL[sector] || String(sector).replace(/_/g, " "); }

function _utcDate(dateStr) { return new Date(dateStr + "T00:00:00Z"); }
function _isoDate(d) { return d.toISOString().slice(0, 10); }
function todayUtc() { return _isoDate(new Date()); }

function mondayOf(dateStr) {
  const d = _utcDate(dateStr);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return _isoDate(d);
}

function weekDates(offset) {
  const monday = _utcDate(mondayOf(todayUtc()));
  monday.setUTCDate(monday.getUTCDate() + offset * 7);
  const out = [];
  for (let i = 0; i < 5; i++) {
    const d = new Date(monday);
    d.setUTCDate(d.getUTCDate() + i);
    out.push(_isoDate(d));
  }
  return out;
}

function _dayLabel(dateStr) {
  const d = _utcDate(dateStr);
  return `${DAY_NAMES[d.getUTCDay()]} ${d.getUTCDate()}`;
}

function _forecastIndex() {
  const idx = new Map();
  for (const r of dataCache.sectorForecast) idx.set(`${r.sector}|${r.forecast_date}`, r);
  return idx;
}

function _dayMeta(dateStr) {
  return dataCache.forecastDays.find(d => d.forecast_date === dateStr) || null;
}

// "bullish" | "bearish" | "mixed" (signal but neutral) | "nosignal" | "closed" | "unknown"
function cellState(row, meta) {
  if (meta && meta.is_trading_day === false) return "closed";
  if (!row) return "unknown";
  if (!row.has_signal) return "nosignal";
  if (row.direction === "bullish") return "bullish";
  if (row.direction === "bearish") return "bearish";
  return "mixed";
}

const CELL_ARROW = { bullish: "▲", bearish: "▼", mixed: "◆", nosignal: "·", closed: "✕", unknown: "?" };
const CELL_WORD = {
  bullish: "Looks up", bearish: "Looks down", mixed: "Mixed signals",
  nosignal: "No astrological signal", closed: "Market closed", unknown: "Not forecast yet",
};

// Next-N-trading-days net signed score for a sector (used by the Dashboard's
// "Sectors Poised to Rise" too). Only days with real forecast rows count.
function weeklyNet(sector, days = 5) {
  const today = todayUtc();
  const rows = dataCache.sectorForecast
    .filter(r => r.sector === sector && r.forecast_date >= today && r.is_trading_day !== false)
    .sort((a, b) => a.forecast_date.localeCompare(b.forecast_date))
    .slice(0, days);
  if (!rows.length) return null;
  const net = rows.reduce((s, r) => s + Number(r.signed_score || 0), 0);
  const up = rows.filter(r => r.has_signal && r.direction === "bullish").length;
  const down = rows.filter(r => r.has_signal && r.direction === "bearish").length;
  const avgStrength = rows.reduce((s, r) => s + Number(r.strength || 0), 0) / rows.length;
  return { net, up, down, days: rows.length, avgStrength, rows };
}

function _rowSummary(sector, dates, idx) {
  const states = dates.map(d => ({ d, s: cellState(idx.get(`${sector}|${d}`), _dayMeta(d)), r: idx.get(`${sector}|${d}`) }))
    .filter(x => x.s !== "closed" && x.s !== "unknown");
  if (!states.length) return "Forecast fills in after the next daily run.";
  if (states.every(x => x.s === "nosignal")) return "No astrological signal this week.";
  const first = states[0].s;
  if (states.every(x => x.s === first)) {
    const avg = Math.round(states.reduce((s, x) => s + Number(x.r.strength || 0), 0) / states.length);
    return `Steady all week: ${CELL_WORD[first].toLowerCase()} (strength about ${avg}/100).`;
  }
  return "Shifts during the week — tap a day to see why.";
}

function _watchRows() {
  return dataCache.sectorWatch.map(w => ({
    key: `w${w.id}`, id: w.id, sector: w.sector, ticker: w.ticker,
    stockName: w.ticker ? _parseKind((dataCache.sectorUniverse.find(u => u.sector === w.sector && u.ticker === w.ticker) || {}).name || w.ticker).label : null,
  }));
}

function renderWeekTab() {
  const gridEl = document.getElementById("week-grid");
  if (!gridEl) return;
  if (weekState.offset === null) {
    const dow = new Date().getUTCDay();
    weekState.offset = (dow === 0 || dow === 6) ? 1 : 0;
  }
  document.querySelectorAll("[data-week-offset]").forEach(b =>
    b.classList.toggle("active", Number(b.dataset.weekOffset) === weekState.offset));

  const dates = weekDates(weekState.offset);
  const idx = _forecastIndex();
  const rows = _watchRows();
  const today = todayUtc();

  document.getElementById("week-range").textContent = `${_dayLabel(dates[0])} – ${_dayLabel(dates[4])}`;

  // What changes this week (non-Moon events, plus the Moon only when it
  // reaches its exalted/debilitated signs -- the other Moon moves are noise).
  const events = [];
  for (const d of dates) {
    const meta = _dayMeta(d);
    if (!meta) continue;
    for (const e of meta.events || []) {
      if (/^Moon moves into/.test(e) && !/(Taurus|Scorpio)$/.test(e)) continue;
      events.push(`${_dayLabel(d)}: ${e}`);
    }
  }
  document.getElementById("week-events").innerHTML = events.length
    ? `<div class="week-events-title">What changes in the sky this week</div>
       <ul class="week-events-list">${events.map(e => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`
    : `<div class="empty-note">No major sky changes this week — the signals below mostly hold steady.</div>`;

  if (!rows.length) {
    gridEl.innerHTML = `
      <div class="week-empty">
        <p>You're not following any sectors yet. Pick some below, or start with the sectors Graha's sky reads most strongly this week.</p>
        <button type="button" id="week-start-top">Start with Graha's top sectors</button>
      </div>`;
    document.getElementById("week-start-top").addEventListener("click", startWithTopSectors);
    document.getElementById("week-detail").innerHTML = "";
    renderSectorPicker();
    return;
  }

  gridEl.innerHTML = `
    <div class="week-head">
      <div></div>
      ${dates.map(d => `<div class="week-head-day ${d === today ? "today" : ""}">${_dayLabel(d)}</div>`).join("")}
      <div></div>
    </div>
    ${rows.map(r => {
      const title = r.ticker
        ? (r.stockName === r.ticker ? escapeHtml(r.ticker) : `${escapeHtml(r.stockName)} <span class="week-ticker">${escapeHtml(r.ticker)}</span>`)
        : escapeHtml(sectorLabel(r.sector));
      const sub = r.ticker
        ? `<div class="week-badge">Sector signal applied to ${escapeHtml(r.stockName)} (${escapeHtml(sectorLabel(r.sector))})</div>`
        : `<div class="week-badge week-badge-sector">Whole sector</div>`;
      return `
      <div class="week-row-wrap">
        <div class="week-row">
          <div class="week-row-label">${title}${sub}</div>
          ${dates.map(d => {
            const fr = idx.get(`${r.sector}|${d}`);
            const st = cellState(fr, _dayMeta(d));
            const strength = fr && fr.has_signal ? Number(fr.strength || 0) : 0;
            const sel = weekState.selected && weekState.selected.key === r.key && weekState.selected.date === d;
            return `<button type="button" class="day-cell state-${st} ${d === today ? "is-today" : ""} ${sel ? "selected" : ""}"
                      style="--tint:${(0.12 + strength / 100 * 0.38).toFixed(2)}"
                      data-cell-key="${r.key}" data-cell-date="${d}" title="${CELL_WORD[st]}">
                      <span class="day-arrow">${CELL_ARROW[st]}</span>
                      ${st === "bullish" || st === "bearish" || st === "mixed" ? `<span class="day-strength">${Math.round(strength)}</span>` : ""}
                    </button>`;
          }).join("")}
          <button type="button" class="week-remove" data-remove-watch="${r.id}" title="Remove from my list" aria-label="Remove">×</button>
        </div>
        <div class="week-row-summary">${escapeHtml(_rowSummary(r.sector, dates, idx))}</div>
      </div>`;
    }).join("")}
    <div class="week-legend">▲ looks up · ▼ looks down · ◆ mixed · · no astrological signal · ✕ market closed · the number is strength out of 100</div>`;

  gridEl.querySelectorAll("[data-cell-key]").forEach(btn => btn.addEventListener("click", () => {
    weekState.selected = { key: btn.dataset.cellKey, date: btn.dataset.cellDate };
    renderWeekTab();
  }));
  gridEl.querySelectorAll("[data-remove-watch]").forEach(btn => btn.addEventListener("click", () => removeWatch(btn.dataset.removeWatch)));

  renderWeekDetail(rows, idx);
  renderSectorPicker();
}

function _statusSentence(row, st) {
  if (st === "nosignal") return "Graha's sky shows no clear influence on this sector for this day.";
  if (st === "bullish") return `The sky leans UP for this sector (strength ${Math.round(row.strength)}/100).`;
  if (st === "bearish") return `The sky leans DOWN for this sector (strength ${Math.round(row.strength)}/100).`;
  if (st === "mixed") return `Mixed signals — pulls in both directions roughly cancel out (strength ${Math.round(row.strength)}/100).`;
  return CELL_WORD[st];
}

async function _etfMove(sector) {
  if (weekState.etfCache[sector] !== undefined) return weekState.etfCache[sector];
  try {
    const rows = await SB.select("predictions",
      `sector=eq.${encodeURIComponent(sector)}&select=date,ticker,price_at_prediction&order=date.desc&limit=6`);
    const priced = rows.filter(r => r.price_at_prediction != null);
    if (priced.length >= 2) {
      const newest = Number(priced[0].price_at_prediction), oldest = Number(priced[priced.length - 1].price_at_prediction);
      weekState.etfCache[sector] = { ticker: priced[0].ticker, pct: Math.round((newest - oldest) / oldest * 1000) / 10, n: priced.length - 1 };
    } else weekState.etfCache[sector] = null;
  } catch (_) { weekState.etfCache[sector] = null; }
  return weekState.etfCache[sector];
}

async function renderWeekDetail(rows, idx) {
  const el = document.getElementById("week-detail");
  const sel = weekState.selected;
  const r = sel && rows.find(x => x.key === sel.key);
  if (!r) {
    el.innerHTML = `<div class="empty-note">Tap any day above to see exactly why Graha reads it that way.</div>`;
    return;
  }
  const fr = idx.get(`${r.sector}|${sel.date}`);
  const st = cellState(fr, _dayMeta(sel.date));
  const name = r.ticker ? (r.stockName === r.ticker ? r.ticker : `${r.stockName} (${r.ticker})`) : sectorLabel(r.sector);
  const chips = (fr && fr.plain_reasons || []).map(p => `<li class="reason-chip">${escapeHtml(p)}</li>`).join("");
  const astro = (fr && fr.reasons || []);

  el.innerHTML = `
    <div class="week-detail-card state-${st}">
      <div class="week-detail-title">${escapeHtml(name)} · ${_dayLabel(sel.date)}</div>
      <div class="week-detail-status">${CELL_ARROW[st]} ${escapeHtml(fr ? _statusSentence(fr, st) : CELL_WORD[st])}</div>
      ${chips ? `<div class="week-detail-sub">Why</div><ul class="reason-chips">${chips}</ul>` : ""}
      ${astro.length ? `<button type="button" class="ghost read-more-btn" id="week-astro-toggle">show the astrological reasoning</button>
        <div class="long-term-note" id="week-astro-detail" hidden>${escapeHtml(astro.join(" · "))}</div>` : ""}
      ${r.ticker ? `<div class="week-caveat">Graha has no separate reading for ${escapeHtml(r.stockName)} — it shows its sector's signal. Individual stocks can move quite differently from their sector.</div>` : ""}
      <div class="week-etf" id="week-etf"></div>
    </div>`;
  const tog = document.getElementById("week-astro-toggle");
  if (tog) tog.addEventListener("click", () => {
    const d = document.getElementById("week-astro-detail");
    d.hidden = !d.hidden;
    tog.textContent = d.hidden ? "show the astrological reasoning" : "hide the astrological reasoning";
  });

  const move = await _etfMove(r.sector);
  const etfEl = document.getElementById("week-etf");
  if (etfEl && move) {
    etfEl.innerHTML = `Reality check: the ${escapeHtml(sectorLabel(r.sector))} fund (${escapeHtml(move.ticker)}) moved
      <strong class="${move.pct >= 0 ? "bullish" : "bearish"}">${move.pct >= 0 ? "+" : ""}${move.pct}%</strong> over the last ${move.n} sessions Graha logged.`;
  }
}

// Any ticker a user types must at least look like one (US tickers, BRK.B,
// spot pairs like XAU/USD). The sector forecast it inherits doesn't depend on
// the symbol being "real", so this only guards against junk input.
const TICKER_RE = /^[A-Z0-9.\/^-]{1,12}$/;
const PICKER_MAX_RESULTS = 40;

// " · ETF" / " · Spot" suffixes (added in rulerships.py) become badges.
function _parseKind(name) {
  if (name.endsWith(" · ETF")) return { label: name.slice(0, -6), kind: "ETF" };
  if (name.endsWith(" · Spot")) return { label: name.slice(0, -7), kind: "Spot price" };
  return { label: name, kind: null };
}

// Case-insensitive search over one sector's stocks and funds: exact ticker,
// ticker prefix, name prefix, then anything containing the text. Typing "etf"
// lists the funds, "gold" lists everything gold-named, etc.
function searchUniverse(sector, query) {
  const all = dataCache.sectorUniverse.filter(u => u.sector === sector);
  const q = query.trim().toLowerCase();
  if (!q) return all;
  const scored = [];
  for (const u of all) {
    const t = u.ticker.toLowerCase(), n = u.name.toLowerCase();
    let score = -1;
    if (t === q) score = 0;
    else if (t.startsWith(q)) score = 1;
    else if (n.startsWith(q)) score = 2;
    else if (t.includes(q) || n.includes(q)) score = 3;
    if (score >= 0) scored.push({ u, score });
  }
  scored.sort((a, b) => a.score - b.score || a.u.ticker.localeCompare(b.u.ticker));
  return scored.map(x => x.u);
}

function renderPickerResults() {
  const el = document.getElementById("picker-results");
  const s = weekState.pickSector;
  if (!el || !s) return;
  const have = new Set(dataCache.sectorWatch.map(w => `${w.sector}|${w.ticker || ""}`));
  const q = weekState.pickQuery || "";
  const hits = searchUniverse(s, q);
  const shown = hits.slice(0, PICKER_MAX_RESULTS);
  const total = dataCache.sectorUniverse.filter(u => u.sector === s).length;

  const rows = shown.map(u => {
    const { label, kind } = _parseKind(u.name);
    const added = have.has(`${s}|${u.ticker}`);
    return `<div class="picker-result">
      <div><span class="picker-result-name">${escapeHtml(label)}</span>
        <span class="week-ticker">${escapeHtml(u.ticker)}</span>
        ${kind ? `<span class="picker-kind">${escapeHtml(kind)}</span>` : ""}</div>
      <button type="button" class="picker-add" data-add-stock="${escapeHtml(u.ticker)}" ${added ? "disabled" : ""}>${added ? "✓ Added" : "+ Add"}</button>
    </div>`;
  }).join("");

  // Not in Graha's list? Let the user add the ticker they typed anyway.
  const typed = q.trim().toUpperCase();
  const exact = dataCache.sectorUniverse.some(u => u.sector === s && u.ticker.toUpperCase() === typed);
  const custom = typed && !exact && TICKER_RE.test(typed)
    ? `<div class="picker-result picker-custom">
         <div><span class="picker-result-name">Add "${escapeHtml(typed)}" to ${escapeHtml(sectorLabel(s))}</span>
           <div class="week-badge">Not in Graha's list — your own pick. It will use ${escapeHtml(sectorLabel(s))}'s signal.</div></div>
         <button type="button" class="picker-add" data-add-stock="${escapeHtml(typed)}" ${have.has(`${s}|${typed}`) ? "disabled" : ""}>${have.has(`${s}|${typed}`) ? "✓ Added" : "+ Add"}</button>
       </div>` : "";

  const status = !total
    ? `<div class="empty-note">The stock list loads after the next engine run.</div>`
    : (q.trim()
        ? `<div class="empty-note">${hits.length ? `${hits.length} match${hits.length > 1 ? "es" : ""} in ${escapeHtml(sectorLabel(s))}${hits.length > shown.length ? ` (showing the first ${shown.length} — keep typing to narrow it down)` : ""}` : `No match in ${escapeHtml(sectorLabel(s))}'s list.`}</div>`
        : `<div class="empty-note">${total} stocks &amp; funds in ${escapeHtml(sectorLabel(s))} — type to search, or scroll.</div>`);

  el.innerHTML = `${status}<div class="picker-results-list">${rows}${custom}</div>`;
  el.querySelectorAll("[data-add-stock]").forEach(b => b.addEventListener("click", () => addWatch(s, b.dataset.addStock)));
}

function renderSectorPicker() {
  const el = document.getElementById("sector-picker");
  if (!el) return;
  const have = new Set(dataCache.sectorWatch.map(w => `${w.sector}|${w.ticker || ""}`));
  el.innerHTML = SECTOR_GROUPS.map(g => `
    <div class="picker-group">
      <div class="picker-group-label">${escapeHtml(g.label)}</div>
      <div class="picker-chips">
        ${g.sectors.map(s => `<button type="button" class="picker-chip ${weekState.pickSector === s ? "active" : ""}" data-pick-sector="${s}">${escapeHtml(sectorLabel(s))}</button>`).join("")}
      </div>
    </div>`).join("") + `<div id="picker-choose"></div>`;

  el.querySelectorAll("[data-pick-sector]").forEach(b => b.addEventListener("click", () => {
    weekState.pickSector = weekState.pickSector === b.dataset.pickSector ? null : b.dataset.pickSector;
    weekState.pickQuery = "";
    renderSectorPicker();
  }));

  const chooseEl = document.getElementById("picker-choose");
  const s = weekState.pickSector;
  if (!s) { chooseEl.innerHTML = `<div class="empty-note">Pick a sector above, then add the whole sector or search for a specific stock or fund in it.</div>`; return; }
  chooseEl.innerHTML = `
    <div class="picker-choose-card">
      <div class="picker-group-label">${escapeHtml(sectorLabel(s))}</div>
      <button type="button" class="picker-add" data-add-sector="${s}" ${have.has(`${s}|`) ? "disabled" : ""}>${have.has(`${s}|`) ? "✓ Whole sector added" : "+ Whole sector"}</button>
      <input id="picker-search" type="search" autocomplete="off" spellcheck="false"
             placeholder="Search ${escapeHtml(sectorLabel(s))} stocks &amp; ETFs — name or ticker">
      <div id="picker-results"></div>
      <div class="empty-note">A stock or fund uses its sector's signal — Graha doesn't read individual stocks separately.</div>
      <div class="form-error" id="picker-error"></div>
    </div>`;
  const input = document.getElementById("picker-search");
  input.value = weekState.pickQuery || "";
  input.addEventListener("input", () => { weekState.pickQuery = input.value; renderPickerResults(); });
  chooseEl.querySelectorAll("[data-add-sector]").forEach(b => b.addEventListener("click", () => addWatch(b.dataset.addSector, null)));
  renderPickerResults();
}

async function _reloadWatch() {
  dataCache.sectorWatch = await SB.select("sector_watch", "order=added_at.asc").catch(() => []);
  renderWeekTab();
}

async function addWatch(sector, ticker) {
  try {
    await SB.insert("sector_watch", { sector, ticker });
    await _reloadWatch();
  } catch (e) {
    const err = document.getElementById("picker-error");
    if (err) err.textContent = /409|duplicate|unique/i.test(e.message) ? "Already on your list." : `Could not add: ${e.message}`;
  }
}

async function removeWatch(id) {
  try {
    await SB.del("sector_watch", `id=eq.${Number(id)}`);
    await _reloadWatch();
  } catch (e) { alert(`Could not remove: ${e.message}`); }
}

async function startWithTopSectors() {
  const scored = Object.keys(SECTOR_LABEL)
    .map(s => ({ s, w: weeklyNet(s) }))
    .filter(x => x.w && x.w.rows.some(r => r.has_signal))
    .sort((a, b) => Math.abs(b.w.net) - Math.abs(a.w.net))
    .slice(0, 4);
  const chosen = scored.length ? scored.map(x => x.s) : ["Gold", "Energy", "Technology", "Financials"];
  try {
    await SB.insert("sector_watch", chosen.map(sector => ({ sector, ticker: null })));
    await _reloadWatch();
  } catch (e) { alert(`Could not add sectors: ${e.message}`); }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-week-offset]").forEach(btn => btn.addEventListener("click", () => {
    weekState.offset = Number(btn.dataset.weekOffset);
    weekState.selected = null;
    renderWeekTab();
  }));
});
