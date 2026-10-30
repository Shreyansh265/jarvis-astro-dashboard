// Pick of the Week, the shared "why ▸" explainer, tracked-stock week cells and
// the candlestick chart.
//
// Honesty rules baked into the rendering:
//  * "Signal alignment" is how many astrological factors line up. It is NEVER
//    shown as a probability or an odds bar.
//  * Every call sits next to Graha's own scored record with the sample size.
//    Percentages appear only once there are at least RECORD_MIN_N scored picks;
//    below that the raw counts are shown, with a 95% interval after that.
//  * A stock with no confirmed company chart is labelled "sector only".

const RECORD_MIN_N = 20;
const RISK_KEY = "graha-risk-usd";
const EVIDENCE_KEY = "evidence_cc-1";
const technicalsCache = {};

// ---------- small helpers ----------
function wilsonInterval(k, n, z = 1.96) {
  if (!n) return null;
  const p = k / n, d = 1 + z * z / n;
  const centre = (p + z * z / (2 * n)) / d;
  const half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

function recordOf(rows) {
  const done = rows.filter(r => r.status === "complete");
  return {
    n: done.length,
    right: done.filter(r => r.was_correct === true).length,
    wrong: done.filter(r => r.was_correct === false).length,
    flat: done.filter(r => r.was_correct === null || r.was_correct === undefined).length,
  };
}

function recordHtml(rec, label = "Pick of the Week") {
  if (!rec.n) return `<div class="record-line">Graha's record on ${escapeHtml(label)}: none scored yet — the first result appears after Friday's close.</div>`;
  const scored = rec.right + rec.wrong;
  let detail = `${rec.right} right, ${rec.wrong} wrong${rec.flat ? `, ${rec.flat} flat (no call)` : ""}`;
  if (scored >= RECORD_MIN_N) {
    const [lo, hi] = wilsonInterval(rec.right, scored);
    detail += ` — ${Math.round(rec.right / scored * 100)}% (95% range ${Math.round(lo * 100)}–${Math.round(hi * 100)}%)`;
  }
  const verdict = scored >= RECORD_MIN_N
    ? "Even so, one pick a week needs a long record to tell skill from luck."
    : `Too few to say anything yet — a coin flip alone can produce streaks. About ${RECORD_MIN_N} scored picks before percentages show, 100+ before skill can be told from luck.`;
  return `<div class="record-line">Graha's record on ${escapeHtml(label)}: <strong>${detail}</strong> (${rec.n} week${rec.n > 1 ? "s" : ""}). ${verdict}</div>`;
}

function evidenceHtml() {
  const ev = dataCache.analogCache && dataCache.analogCache[EVIDENCE_KEY];
  if (!ev || !ev.methods) return `<div class="record-line">The long-history replay of these same rules hasn't been run yet, so there is no multi-year evidence to show.</div>`;
  const pick = ev.methods.pick_of_week_replay, base = ev.baselines || {};
  if (!pick || !pick.scored) return `<div class="record-line">Replay found no comparable weeks.</div>`;
  const ci = pick.ci95 && pick.ci95[0] !== null ? ` (95% range ${Math.round(pick.ci95[0] * 100)}–${Math.round(pick.ci95[1] * 100)}%)` : "";
  const mix = pick.bullish_share !== null ? `${Math.round(pick.bullish_share * 100)}% of its calls were "up"` : "";
  return `<div class="record-line">Replaying these exact rules over ${ev.weeks} past weeks (${escapeHtml(ev.start)} on, ${ev.stocks} stocks): the weekly pick was right
    <strong>${Math.round(pick.accuracy * 100)}%</strong>${ci} of ${pick.scored} scored weeks. Doing nothing clever scores
    ${base.always_up !== undefined ? `${Math.round(base.always_up * 100)}% by always saying "up" and ${Math.round(base.always_down * 100)}% by always saying "down"` : "about the same"};
    ${mix}. Survivorship caveat: only stocks that still exist today.</div>`;
}

function whyButton(ticker, sector, label = "why ▸") {
  return `<button type="button" class="why-btn" data-why="${escapeHtml(ticker)}" data-why-sector="${escapeHtml(sector || "")}" aria-haspopup="dialog">${label}</button>`;
}

function stockDisplayName(ticker) {
  const chart = (dataCache.companyCharts || {})[ticker];
  if (chart && chart.name) return chart.name;
  return _parseKind(_stockName(ticker)).label;
}

function pickRows() { return (dataCache.weeklyPicks || []).filter(p => p.pick_of_week); }
function radarRows() { return (dataCache.weeklyPicks || []).filter(p => !p.pick_of_week); }

// The pick for the week in focus (weekend -> the coming week). Matches on the
// Monday of week_start because a holiday week's first trading day is a Tuesday.
function currentPickRow() {
  const focus = currentPicksWeekStart();
  const rows = pickRows().sort((a, b) => b.week_start.localeCompare(a.week_start));
  return rows.find(p => mondayOf(p.week_start) === focus) || null;
}

function latestPickRow() {
  return pickRows().sort((a, b) => b.week_start.localeCompare(a.week_start))[0] || null;
}

function todaysStockReading(ticker) {
  const rows = (dataCache.stockForecast || []).filter(r => r.ticker === ticker)
    .sort((a, b) => a.forecast_date.localeCompare(b.forecast_date));
  const today = todayUtc();
  return rows.find(r => r.forecast_date >= today) || rows[rows.length - 1] || null;
}

function basisChip(basis, chart) {
  if (basis === "company") return `<span class="basis-chip company" title="Uses the company's own chart (cast for its first day of trading) plus its sector's sky">Company chart + sector</span>`;
  const why = chart && chart.confidence === "verify" ? "first-trade date not yet confirmed" : "no company chart on file";
  return `<span class="basis-chip sector" title="${escapeHtml(why)}">Sector only</span>`;
}

function dirWord(direction) { return direction === "bullish" ? "UP" : (direction === "bearish" ? "DOWN" : "no clear lean"); }
function dirGlyph(direction) { return direction === "bullish" ? "▲" : (direction === "bearish" ? "▼" : "◆"); }

// ---------- technicals (lazy) ----------
async function loadTechnicals(ticker) {
  if (ticker in technicalsCache) return technicalsCache[ticker];
  try {
    const rows = await SB.select("stock_technicals", `ticker=eq.${encodeURIComponent(ticker)}&order=as_of.desc&limit=1`);
    technicalsCache[ticker] = rows[0] || null;
  } catch (_) { technicalsCache[ticker] = null; }
  return technicalsCache[ticker];
}

// ---------- candlestick chart (SVG; colors come from CSS tokens) ----------
function candleSvg(bars, levels = {}) {
  if (!bars || bars.length < 5) return "";
  const W = 600, H = 230, padL = 6, padR = 100, padT = 10, padB = 20;
  const vals = bars.flatMap(b => [Number(b[2]), Number(b[3])]);
  const lv = Object.values(levels).map(l => l && Number(l.value)).filter(v => v && isFinite(v));
  const hi = Math.max(...vals, ...lv), lo = Math.min(...vals, ...lv);
  const span = (hi - lo) || 1;
  const y = v => padT + (hi - v) / span * (H - padT - padB);
  const step = (W - padL - padR) / bars.length, bw = Math.max(2, step * 0.62);
  const candles = bars.map((b, i) => {
    const [, o, h, l, c] = b.map((v, k) => k === 0 ? v : Number(v));
    const up = c >= o, x = padL + step * i + step / 2;
    const top = y(Math.max(o, c)), bot = y(Math.min(o, c));
    return `<line class="wick ${up ? "up" : "down"}" x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y(h).toFixed(1)}" y2="${y(l).toFixed(1)}"/>` +
           `<rect class="body ${up ? "up" : "down"}" x="${(x - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, bot - top).toFixed(1)}"/>`;
  }).join("");
  const lines = Object.entries(levels).filter(([, l]) => l && isFinite(Number(l.value))).map(([k, l]) => {
    const yy = y(Number(l.value)).toFixed(1);
    return `<line class="lvl lvl-${k}" x1="${padL}" x2="${W - padR}" y1="${yy}" y2="${yy}"/>` +
           `<text class="lvl-text lvl-${k}" x="${W - padR + 4}" y="${(Number(yy) + 3).toFixed(1)}">${escapeHtml(l.label)} ${Number(l.value).toFixed(2)}</text>`;
  }).join("");
  const first = bars[0][0], last = bars[bars.length - 1][0];
  return `<svg class="candle-chart" viewBox="0 0 ${W} ${H}" role="img"
      aria-label="Daily candlestick chart, ${bars.length} sessions from ${escapeHtml(first)} to ${escapeHtml(last)}">
    ${lines}${candles}
    <text class="axis-text" x="${padL}" y="${H - 5}">${escapeHtml(first)}</text>
    <text class="axis-text" x="${W - padR}" y="${H - 5}" text-anchor="end">${escapeHtml(last)}</text>
  </svg>`;
}

// ---------- trader's desk ----------
const VERDICT_TEXT = {
  agree: ["Price action agrees", "agree"], mixed: ["Price action is mixed", "mixed"],
  disagree: ["Price action disagrees", "disagree"], "no-trade": ["No-trade zone", "notrade"],
};

function _cap(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : t; }

function riskAmount() {
  try { const v = Number(localStorage.getItem(RISK_KEY)); return v > 0 ? v : 100; } catch (_) { return 100; }
}

function sharesFor(riskUsd, riskPerShare) {
  if (!riskPerShare || riskPerShare <= 0) return null;
  return Math.floor(riskUsd / riskPerShare);
}

function deskHtml(desk, idPrefix) {
  if (!desk) return `<div class="desk desk-empty">The trader's-desk check wasn't available when this pick was frozen, so there is no price-action read.</div>`;
  if (!desk.checks || !desk.checks.length) return `<div class="desk desk-empty">No trade read: ${escapeHtml(desk.reason || "not enough price history")}.</div>`;
  const [text, cls] = VERDICT_TEXT[desk.verdict] || ["", ""];
  const risk = riskAmount();
  const shares = sharesFor(risk, desk.risk_per_share);
  return `<div class="desk desk-${cls}">
    <div class="desk-head"><span class="desk-verdict ${cls}">${escapeHtml(text)}</span>
      <span class="desk-aligned">aligned ${desk.aligned} of ${desk.of} checks</span></div>
    <div class="desk-reason">${escapeHtml(_cap(desk.reason || ""))}. This never changes the astrological call — it says whether price action backs it.</div>
    <ul class="desk-checks">${desk.checks.map(c => `<li class="${c.ok ? "ok" : "no"}"><span class="mark" aria-hidden="true">${c.ok ? "✓" : "✗"}</span><strong>${escapeHtml(c.name)}</strong> — ${escapeHtml(c.detail)}</li>`).join("")}</ul>
    <div class="desk-levels">
      <div><span class="k">Stop</span><span class="v">$${Number(desk.stop).toFixed(2)}</span></div>
      <div><span class="k">Target</span><span class="v">$${Number(desk.target).toFixed(2)}</span></div>
      <div><span class="k">Reward : risk</span><span class="v">${desk.reward_risk !== null && desk.reward_risk !== undefined ? desk.reward_risk + " : 1" : "—"}</span></div>
      <div><span class="k">Risk / share</span><span class="v">$${Number(desk.risk_per_share).toFixed(2)}</span></div>
    </div>
    <div class="desk-invalidation">${escapeHtml(desk.invalidation || "")}</div>
    <label class="desk-size" for="${idPrefix}-risk">If I risk $<input id="${idPrefix}-risk" class="risk-input" type="number" min="1" step="1" value="${risk}" inputmode="numeric" data-risk-input data-risk-per-share="${desk.risk_per_share}" data-shares-out="${idPrefix}-shares"> on this idea, that is about
      <strong id="${idPrefix}-shares">${shares === null ? "—" : shares}</strong> share${shares === 1 ? "" : "s"} <span class="holding-meta">(kept in this browser only — Graha never stores your account size; not advice)</span></label>
  </div>`;
}

document.addEventListener("input", (e) => {
  const inp = e.target.closest && e.target.closest("[data-risk-input]");
  if (!inp) return;
  const v = Number(inp.value);
  if (v > 0) { try { localStorage.setItem(RISK_KEY, String(v)); } catch (_) { /* storage blocked */ } }
  const out = document.getElementById(inp.dataset.sharesOut);
  const s = sharesFor(v, Number(inp.dataset.riskPerShare));
  if (out) out.textContent = v > 0 && s !== null ? String(s) : "—";
});

// ---------- Pick of the Week hero ----------
function _weekRange(pick) {
  const mon = mondayOf(pick.week_start), fri = new Date(_utcDate(mon)); fri.setUTCDate(fri.getUTCDate() + 4);
  return `${_dayLabel(mon)} – ${_dayLabel(_isoDate(fri))}`;
}

function emptyPickHtml() {
  const anyEver = pickRows().length;
  return `<div class="pick-empty">
    <div class="pick-kicker">PICK OF THE WEEK</div>
    <p>${anyEver
      ? "No pick is frozen for this week. Graha only names a stock when a sector's sky leans strongly and consistently across the week and the stock isn't contradicted by its own chart — on a quiet week that means none, and it won't invent one."
      : "Each weekend Graha freezes one stock for the coming week, called up or down from astrology alone, and scores it after Friday's close. The first one appears after the next Sunday run."}</p>
  </div>`;
}

async function renderPick(containerId, opts = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;
  let pick = currentPickRow();
  let stale = false;
  if (!pick) {
    pick = latestPickRow();
    stale = !!pick;
    if (!pick) { el.innerHTML = emptyPickHtml(); return; }
  }
  const up = pick.direction === "bullish";
  const f = pick.factors || {};
  const chart = (dataCache.companyCharts || {})[pick.ticker];
  const basis = f.composite ? f.composite.chart_basis : "sector";
  const today = todaysStockReading(pick.ticker);
  const todayLine = today
    ? `<div class="pick-today"><span class="k">Today's reading</span> <span class="${today.direction === "bullish" ? "bullish" : (today.direction === "bearish" ? "bearish" : "")}">${dirGlyph(today.direction)} ${today.direction === "neutral" ? "mixed signals" : `leans ${dirWord(today.direction)}`}</span>
        <span class="holding-meta">signal alignment ${Math.round(Number(today.strength))}/100 · ${today.chart_basis === "company" ? "company chart + sector" : "sector only"} · not a probability</span></div>`
    : `<div class="pick-today"><span class="k">Today's reading</span> <span class="holding-meta">fills in after the next daily run</span></div>`;
  const complete = pick.status === "complete";
  const result = complete
    ? `<div class="bt-verdict ${pick.was_correct === null ? "flat" : (pick.was_correct ? "right" : "wrong")}">${pick.was_correct === null ? "— Flat week (no call)" : (pick.was_correct ? "✔ Right" : "✘ Wrong")}: ${escapeHtml(pick.ticker)} ${Number(pick.stock_return_pct) >= 0 ? "rose" : "fell"} ${Math.abs(Number(pick.stock_return_pct)).toFixed(2)}% over the week</div>` : "";

  el.innerHTML = `
    <div class="pick-hero-card ${up ? "up" : "down"}">
      <div class="pick-kicker">PICK OF THE WEEK · ${escapeHtml(_weekRange(pick))}${stale ? ` <span class="stale-tag">last frozen pick — the next one is frozen on Sunday</span>` : ""}</div>
      <div class="pick-main">
        <div class="pick-id">
          <span class="pick-ticker">${escapeHtml(pick.ticker)}</span>
          <span class="pick-name">${escapeHtml(stockDisplayName(pick.ticker))}</span>
          <span class="pick-sector">${escapeHtml(sectorLabel(pick.sector))}</span>
        </div>
        <div class="pick-call ${up ? "up" : "down"}">${up ? "▲ UP" : "▼ DOWN"} <span class="pick-call-sub">this week</span></div>
      </div>
      <div class="pick-chips">${basisChip(basis, chart)}
        <span class="basis-chip neutral">signal alignment ${Math.round(Number(pick.strength))}/100 — not a probability</span>
        <span class="basis-chip neutral">frozen ${pick.picked_at ? escapeHtml(_dayLabel(pick.picked_at.slice(0, 10))) : ""}</span></div>
      <div class="pick-reasoning">${escapeHtml(pick.reasoning || "")}</div>
      ${todayLine}
      ${result}
      <div class="pick-chart" id="${containerId}-chart"><div class="empty-note">Loading price chart…</div></div>
      ${deskHtml(pick.trader_desk, containerId)}
      ${recordHtml(recordOf(pickRows()))}
      <div class="pick-actions">${whyButton(pick.ticker, pick.sector, "Why this pick ▸")}
        <button type="button" class="ghost" data-goto-tab="backtest">See the scored history →</button></div>
      <div class="pick-fine">An astrological lean, not a forecast of price. Astrology has no demonstrated predictive power over markets; Graha shows its own scored record so you can judge for yourself.</div>
    </div>`;

  // Chart bars load lazily so the 60-bar history isn't part of every page load.
  const tech = await loadTechnicals(pick.ticker);
  const chartEl = document.getElementById(`${containerId}-chart`);
  if (!chartEl) return;
  if (tech && tech.bars && tech.bars.length) {
    const d = pick.trader_desk || {};
    const lvl = {
      stop: d.stop ? { value: d.stop, label: "stop" } : null,
      target: d.target ? { value: d.target, label: "target" } : null,
      support: tech.support ? { value: tech.support, label: "support" } : null,
      resistance: tech.resistance ? { value: tech.resistance, label: "resist." } : null,
    };
    chartEl.innerHTML = candleSvg(tech.bars, lvl) +
      `<div class="holding-meta">Daily candles, last ${tech.bars.length} sessions to ${escapeHtml(tech.as_of)}. Stop/target are from the desk when the pick was frozen.</div>`;
  } else {
    chartEl.innerHTML = `<div class="empty-note">No price history stored for ${escapeHtml(pick.ticker)} yet — it appears after the next post-close run.</div>`;
  }
}

function renderPickViews() {
  renderPick("pick-hero");
  renderPick("pick-hero-signals");
  renderRadar();
}

function renderRadar() {
  const el = document.getElementById("radar-list");
  if (!el) return;
  const pick = currentPickRow() || latestPickRow();
  const week = pick ? mondayOf(pick.week_start) : currentPicksWeekStart();
  const rows = radarRows().filter(p => mondayOf(p.week_start) === week).sort((a, b) => (a.rank || 0) - (b.rank || 0));
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No other sector cleared the bar for the week of ${escapeHtml(_dayLabel(week))}.</p>`; return; }
  el.innerHTML = rows.map(p => `<div class="radar-row ${p.direction === "bullish" ? "up" : "down"}">
      <div><span class="week-ticker">${escapeHtml(p.ticker)}</span> ${escapeHtml(stockDisplayName(p.ticker))}
        <span class="holding-meta">${escapeHtml(sectorLabel(p.sector))}</span></div>
      <div class="radar-dir ${p.direction === "bullish" ? "bullish" : "bearish"}">${p.direction === "bullish" ? "▲ up" : "▼ down"}</div>
      ${whyButton(p.ticker, p.sector)}</div>`).join("");
}

// ---------- tracked stock: this week / next week ----------
function _signedOf(direction, strength) { return direction === "bullish" ? strength : (direction === "bearish" ? -strength : 0); }

function _stockCellRow(ticker, sector, date) {
  const sf = (dataCache.stockForecast || []).find(r => r.ticker === ticker && r.forecast_date === date);
  if (sf) {
    const strength = Number(sf.strength);
    return { dir: sf.direction, strength, basis: sf.chart_basis, has: sf.direction !== "neutral", signed: _signedOf(sf.direction, strength) };
  }
  const sr = (dataCache.sectorForecast || []).find(r => r.sector === sector && r.forecast_date === date);
  if (!sr) return null;
  const strength = Number(sr.strength || 0), has = !!sr.has_signal && sr.direction !== "neutral";
  return { dir: sr.direction, strength, basis: "sector", has: !!sr.has_signal, signed: has ? _signedOf(sr.direction, strength) : 0 };
}

function stockWeekHtml(ticker, sector, offset) {
  const dates = weekDates(offset);
  const today = todayUtc();
  let net = 0, counted = 0, up = 0, down = 0, basisSet = new Set();
  const cells = dates.map(d => {
    const meta = _dayMeta(d);
    const r = _stockCellRow(ticker, sector, d);
    let st = "unknown";
    if (meta && meta.is_trading_day === false) st = "closed";
    else if (r) {
      st = !r.has ? "nosignal" : (r.dir === "bullish" ? "bullish" : (r.dir === "bearish" ? "bearish" : "mixed"));
      basisSet.add(r.basis);
      net += r.signed; counted++;
      if (st === "bullish") up++;
      if (st === "bearish") down++;
    }
    const strength = r && r.has ? r.strength : 0;
    return `<div class="day-cell static state-${st} ${d === today ? "is-today" : ""}" style="--tint:${(0.12 + strength / 100 * 0.38).toFixed(2)}" title="${CELL_WORD[st]}">
      <span class="day-name">${_dayLabel(d)}</span><span class="day-arrow">${CELL_ARROW[st]}</span>
      ${["bullish", "bearish", "mixed"].includes(st) ? `<span class="day-strength">${Math.round(strength)}</span>` : ""}</div>`;
  }).join("");
  let lean;
  if (!counted) lean = `<span class="holding-meta">Forecast fills in after the next daily run.</span>`;
  else if (!up && !down) lean = `<span class="week-lean flat">◆ No clear lean</span> <span class="holding-meta">no astrological signal on the trading days shown</span>`;
  else {
    const dir = net > 0 ? "bullish" : (net < 0 ? "bearish" : null);
    lean = dir ? `<span class="week-lean ${dir}">${dirGlyph(dir)} Leans ${dirWord(dir)}</span> <span class="holding-meta">${up} up day${up === 1 ? "" : "s"}, ${down} down day${down === 1 ? "" : "s"}</span>`
               : `<span class="week-lean flat">◆ Evenly split</span> <span class="holding-meta">${up} up, ${down} down</span>`;
  }
  const basisTxt = basisSet.has("company") ? "company chart + sector" : "sector only";
  return `<div class="stock-week">
    <div class="stock-week-head"><strong>${offset === 0 ? "This week" : "Next week"}</strong> <span class="holding-meta">${_dayLabel(dates[0])} – ${_dayLabel(dates[4])}</span>
      <span class="stock-week-lean">${lean}</span><span class="basis-chip ${basisSet.has("company") ? "company" : "sector"}">${basisTxt}</span></div>
    <div class="stock-week-cells">${cells}</div></div>`;
}

function stockWeeksHtml(ticker, sector) {
  const chart = (dataCache.companyCharts || {})[ticker];
  const note = chart && chart.confidence === "known"
    ? `Uses ${escapeHtml(stockDisplayName(ticker))}'s own chart (its first day of trading, ${escapeHtml(chart.first_trade_date)}) plus ${escapeHtml(sectorLabel(sector))}'s sky.`
    : (chart ? `${escapeHtml(stockDisplayName(ticker))}'s first-trade date isn't confirmed yet, so this uses ${escapeHtml(sectorLabel(sector))}'s sky only.`
             : `Graha has no first-trade date on file for ${escapeHtml(ticker)}, so this is ${escapeHtml(sectorLabel(sector))}'s sky only — individual stocks can move quite differently from their sector.`);
  return `<div class="detail-section stock-weeks">
    <h3>This week &amp; next week ${whyButton(ticker, sector)}</h3>
    ${stockWeekHtml(ticker, sector, 0)}${stockWeekHtml(ticker, sector, 1)}
    <div class="holding-meta">${note} ▲ up · ▼ down · ◆ mixed · · no signal · the number is signal alignment, not a probability.</div>
  </div>`;
}

// ---------- the shared "why ▸" modal ----------
let whyOpener = null;

function _section(title, bodyHtml) { return bodyHtml ? `<div class="detail-section"><h3>${escapeHtml(title)}</h3>${bodyHtml}</div>` : ""; }
function _chips(list) { return list && list.length ? `<ul class="reason-chips">${list.map(r => `<li class="reason-chip">${escapeHtml(r)}</li>`).join("")}</ul>` : ""; }

async function whyHtml(ticker, sector) {
  const picks = (dataCache.weeklyPicks || []).filter(p => p.ticker === ticker).sort((a, b) => b.week_start.localeCompare(a.week_start));
  const pick = picks[0] || null;
  const f = pick && pick.factors ? pick.factors : null;
  const chart = (dataCache.companyCharts || {})[ticker];
  sector = sector || (pick && pick.sector) || ((dataCache.sectorUniverse.find(u => u.ticker === ticker) || {}).sector) || "";

  // Per-day factors for non-pick stocks are loaded on demand (kept out of the bulk load).
  let dayFactors = null;
  if (!f) {
    try {
      const rows = await SB.select("stock_forecast", `ticker=eq.${encodeURIComponent(ticker)}&forecast_date=gte.${todayUtc()}&order=forecast_date.asc&limit=1`);
      if (rows[0]) dayFactors = rows[0].factors;
    } catch (_) { /* not available -> sector-only explanation */ }
  }
  const tech = await loadTechnicals(ticker);

  // The sky for the sector: frozen pick reasons, else the strongest day this week.
  let sectorReasons = f ? (f.sector.plain_reasons || []) : (dayFactors && dayFactors.sector ? dayFactors.sector.plain_reasons : null);
  if (!sectorReasons || !sectorReasons.length) {
    const w = sector ? weeklyNet(sector, 5) : null;
    if (w && w.rows.length) {
      const best = w.rows.filter(r => r.has_signal).sort((a, b) => Number(b.strength) - Number(a.strength))[0];
      sectorReasons = best ? best.plain_reasons : [];
    }
  }

  const call = pick
    ? `<div class="why-call ${pick.direction === "bullish" ? "up" : "down"}">${pick.pick_of_week ? "Pick of the Week" : "On Graha's radar"}: ${pick.direction === "bullish" ? "▲ UP" : "▼ DOWN"} for the week of ${escapeHtml(_dayLabel(mondayOf(pick.week_start)))}
         <div class="holding-meta">${escapeHtml(pick.reasoning || "")}</div></div>`
    : `<div class="why-call">Graha hasn't named ${escapeHtml(ticker)} as a weekly pick. This shows how the sky reads for it.</div>`;

  const sectorSection = _section(`The sky for ${sector ? sectorLabel(sector) : "its sector"}`,
    sectorReasons && sectorReasons.length ? _chips(sectorReasons) : `<p class="empty-note">No notable sector-level astrological signal right now.</p>`);

  let companySection;
  const companyLines = f && f.company ? [...(f.company.supporting || [])] : (dayFactors && dayFactors.company ? dayFactors.company.plain : null);
  if (f && f.company) {
    companySection = _section(`${stockDisplayName(ticker)}'s own chart`,
      `<p class="why-p">Cast for its first day of trading (${escapeHtml(f.company.first_trade_date)}, ${escapeHtml(f.company.confidence)}). Net transit reading for the week: <strong>${Number(f.company.week_score) >= 0 ? "+" : ""}${Number(f.company.week_score).toFixed(0)}</strong> (positive supportive, negative challenging).</p>${_chips(companyLines)}`);
  } else if (companyLines && companyLines.length) {
    companySection = _section(`${stockDisplayName(ticker)}'s own chart`, `<p class="why-p">Today's transits to its first-trade chart:</p>${_chips(companyLines)}`);
  } else {
    const reason = chart ? (chart.confidence === "verify" ? "its first-trade date isn't confirmed yet" : "no transit is close enough to count today")
                         : "Graha has no first-trade date on file for it";
    companySection = _section("Company chart", `<p class="why-p">Not used: ${escapeHtml(reason)}. The read here is the sector's sky only, and individual stocks can move quite differently from their sector.</p>`);
  }

  const desk = pick && pick.trader_desk ? pick.trader_desk : null;
  let deskSection;
  if (desk) deskSection = _section("Trader's desk (when frozen)", deskHtml(desk, "why"));
  else if (tech) {
    deskSection = _section("Price action", `<div class="desk-levels">
      <div><span class="k">Trend</span><span class="v">${escapeHtml(tech.trend || "—")}</span></div>
      <div><span class="k">RSI 14</span><span class="v">${tech.rsi14 ?? "—"}</span></div>
      <div><span class="k">Support</span><span class="v">${tech.support ? "$" + Number(tech.support).toFixed(2) : "—"}</span></div>
      <div><span class="k">Resistance</span><span class="v">${tech.resistance ? "$" + Number(tech.resistance).toFixed(2) : "—"}</span></div></div>
      <div class="holding-meta">As of ${escapeHtml(tech.as_of)}. The full checklist (agree / disagree / no-trade) runs for weekly picks.</div>`);
  } else deskSection = "";

  const counter = f && f.counter_case ? _section("The case against", _chips(f.counter_case)) : "";
  const recordSection = _section("Graha's record",
    recordHtml(recordOf(pickRows())) + (radarRows().length ? recordHtml(recordOf(radarRows()), "radar picks (sector lead stocks)") : "") + evidenceHtml());

  return `<h3 class="why-title">${escapeHtml(stockDisplayName(ticker))} <span class="week-ticker">${escapeHtml(ticker)}</span> ${basisChip(f ? f.composite.chart_basis : (dayFactors && dayFactors.company ? "company" : "sector"), chart)}</h3>
    ${call}${sectorSection}${companySection}${deskSection}${counter}${recordSection}
    <div class="pick-fine">An astrological lean, not a forecast of price or investment advice.</div>`;
}

async function openWhy(ticker, sector, opener) {
  const modal = document.getElementById("why-modal");
  const body = document.getElementById("why-body");
  if (!modal || !body) return;
  whyOpener = opener || null;
  body.innerHTML = `<p class="empty-note">Loading the full reasoning for ${escapeHtml(ticker)}…</p>`;
  modal.hidden = false;
  document.getElementById("why-close").focus();
  try { body.innerHTML = await whyHtml(ticker, sector); }
  catch (e) { body.innerHTML = `<p class="empty-note">Could not load the explanation: ${escapeHtml(e.message)}</p>`; }
}

function closeWhy() {
  const modal = document.getElementById("why-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  if (whyOpener && document.contains(whyOpener)) whyOpener.focus();
  whyOpener = null;
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest("[data-why]");
  if (btn) { openWhy(btn.dataset.why, btn.dataset.whySector, btn); return; }
  if (e.target.id === "why-modal" || e.target.id === "why-close") closeWhy();
});
document.addEventListener("keydown", (e) => {
  const modal = document.getElementById("why-modal");
  if (!modal || modal.hidden) return;
  if (e.key === "Escape") { closeWhy(); return; }
  if (e.key === "Tab") {   // keep focus inside the dialog
    const focusable = modal.querySelectorAll("button, input, [href], [tabindex]:not([tabindex='-1'])");
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});
