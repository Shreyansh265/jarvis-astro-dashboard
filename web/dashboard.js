// Dashboard tab sections: "Sectors Poised to Rise" and "Graha's Track Record".
// (Portfolio preview lives in app.js next to the Portfolio tab's price logic.)

// A sector must lean up on most of the next days AND clear this average strength
// to be called "poised" -- a faint lean isn't a tailwind (weekly picks use 65).
const POISED_MIN_STRENGTH = 60;
const CONDITION_WORD = { exalted: "at its strongest", debilitated: "at its weakest", retrograde: "moving backwards (retrograde)" };

function _analogHtml(key) {
  if (!key) return "";
  const a = dataCache.analogCache[key];
  if (!a) return `<div class="poised-analog">A past example appears here after the next weekly run.</div>`;
  const tag = `<span class="poised-analog-tag">Most recent occurrence — an illustration, not a prediction</span>`;
  if (!a.match_date || a.unverifiable_reason) {
    return `<div class="poised-analog">${tag}<br>No verifiable past example: ${escapeHtml(a.unverifiable_reason || "none found")}.</div>`;
  }
  const pct = Number(a.pct_move);
  let verdict = "";
  if (a.condition === "exalted") verdict = pct > 0 ? " — in line with the lean" : " — against the lean";
  if (a.condition === "debilitated") verdict = pct < 0 ? " — in line with the lean" : " — against the lean";
  const rule = (a.rule_n && a.rule_hit_rate !== null && a.rule_hit_rate !== undefined)
    ? `<br>Overall, this kind of setup pointed the right way in ${Math.round(a.rule_hit_rate * 100)}% of ${a.rule_n} independent weeks checked${a.rule_n < 10 ? " (small sample)" : ""}.` : "";
  return `<div class="poised-analog">${tag}<br>
    On <strong>${escapeHtml(a.match_date)}</strong> ${escapeHtml(a.planet)} was ${CONDITION_WORD[a.condition] || ""} in ${escapeHtml(a.sign)}, like now.
    Over the next ${a.days_after} trading days the ${escapeHtml(sectorLabel(a.sector))} fund (${escapeHtml(a.ticker)})
    moved <strong class="${pct >= 0 ? "bullish" : "bearish"}">${pct >= 0 ? "+" : ""}${pct}%</strong>${verdict}.${rule}</div>`;
}

function renderPoisedToRise() {
  const el = document.getElementById("poised-list");
  if (!el) return;
  if (!dataCache.sectorForecast.length) {
    el.innerHTML = `<p class="empty-note">The forecast fills in after the next daily run.</p>`;
    return;
  }
  const poised = Object.keys(SECTOR_LABEL)
    .map(sector => ({ sector, w: weeklyNet(sector) }))
    .filter(x => x.w && x.w.net > 0 && x.w.up >= Math.ceil(x.w.days * 0.6) && x.w.avgStrength >= POISED_MIN_STRENGTH)
    .sort((a, b) => b.w.net - a.w.net)
    .slice(0, 3);
  if (!poised.length) {
    el.innerHTML = `<p class="empty-note">No sector has a strong tailwind over the next few trading days — most are quiet. Graha won't invent one.</p>`;
    return;
  }
  el.innerHTML = `<div class="poised-grid">${poised.map(({ sector, w }) => {
    const ups = w.rows.filter(r => r.has_signal && r.direction === "bullish");
    const best = ups.reduce((a, b) => Number(b.strength) > Number(a.strength) ? b : a, ups[0]);
    const withKey = ups.find(r => r.analog_key) || best;
    const reasons = (best.plain_reasons || []).map(r => `<li class="reason-chip">${escapeHtml(r)}</li>`).join("");
    return `<div class="sector-card bullish poised-card">
      <div class="sector-card-top"><span class="sector-name">${escapeHtml(sectorLabel(sector))}</span>
        <span class="sector-direction bullish">▲ ${w.up} of ${w.days} days</span></div>
      <div class="week-badge">Average strength ${Math.round(w.avgStrength)}/100 over the next ${w.days} trading days</div>
      ${reasons ? `<div class="week-detail-sub" style="margin-top:10px">Why</div><ul class="reason-chips">${reasons}</ul>` : ""}
      ${_analogHtml(withKey.analog_key)}
    </div>`;
  }).join("")}</div>`;
}

function renderTrackRecord() {
  const el = document.getElementById("track-record");
  if (!el) return;
  const shownWeeks = backtestWeekStarts();
  const live = (dataCache.weeklyPicks || []).filter(p => p.status === "complete" && shownWeeks.includes(p.week_start));
  const ws = weeklyPickStats(live);
  const line = (label, s) => s.n
    ? `<div class="stat-tile"><div class="stat-label">${label}</div><div class="stat-value">${s.right} of ${s.n} right</div><div class="holding-meta">${Math.round(s.hitRate * 100)}%${s.excess === null ? "" : ` · ${s.excess >= 0 ? "+" : ""}${s.excess.toFixed(1)} pts vs market`}</div></div>`
    : `<div class="stat-tile"><div class="stat-label">${label}</div><div class="stat-value">—</div><div class="holding-meta">none scored yet</div></div>`;

  const sug = suggestionRows().filter(r => r.right !== null);
  const sugRight = sug.filter(r => r.right).length;

  const closed = (dataCache.recentTrades || []).filter(t => (t.action === "SELL" || t.action === "COVER") && t.pnl !== null && t.pnl !== undefined);
  const wins = closed.filter(t => Number(t.pnl) > 0).length;

  el.innerHTML = `
    <div class="trading-stats-row">
      ${line("Weekly picks: expected UP", ws.bullish)}
      ${line("Weekly picks: expected DOWN", ws.bearish)}
      <div class="stat-tile"><div class="stat-label">All suggestions so far</div>
        <div class="stat-value">${sug.length ? `${sugRight} of ${sug.length} right` : "—"}</div>
        <div class="holding-meta">${sug.length ? Math.round(sugRight / sug.length * 100) + "% (approx)" : "no priced suggestions yet"}</div></div>
    </div>
    <div class="holding-meta" style="margin-top:8px">Graha 2.0 paper trades: ${closed.length ? `${wins} of ${closed.length} recent closed trades were profitable` : "no closed trades yet"}.
      Weekly picks cover recent weeks only; small samples say little either way.</div>`;
}
