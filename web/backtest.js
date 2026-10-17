// Backtest tab: Graha's frozen weekly picks and how each week actually went,
// plus every individual suggestion so far.
//
// Rules this tab follows:
//  * Only COMPLETED weeks show results. The current week lists its picks as
//    "in progress"; results unlock once the week_end bar exists (Friday
//    after the close) -- no partial, live-updating verdicts.
//  * "Expected up" and "expected down" picks are counted and scored
//    separately, and always shown next to the market (SPY) and the sector
//    fund, because a hit rate in a rising market is just the base rate.
//  * Small samples are labelled as such, never dressed up as skill.

const backtestState = { weekStart: null, showAllSuggestions: false };

function _stockName(ticker) {
  const u = (dataCache.sectorUniverse || []).find(x => x.ticker === ticker);
  return u ? u.name : ticker;
}

function _pct(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function _pctClass(n) { return n === null || n === undefined ? "" : (Number(n) >= 0 ? "bullish" : "bearish"); }

// The week "in focus": on a weekend that is the coming Monday's week (its
// picks were just frozen), otherwise this week.
function currentPicksWeekStart() {
  const t = todayUtc();
  const dow = _utcDate(t).getUTCDay();
  const monday = _utcDate(mondayOf(t));
  if (dow === 0 || dow === 6) monday.setUTCDate(monday.getUTCDate() + 7);
  return _isoDate(monday);
}

function backtestWeekStarts() {
  const cur = _utcDate(currentPicksWeekStart());
  const out = [];
  for (let i = 0; i < 5; i++) {
    const d = new Date(cur);
    d.setUTCDate(d.getUTCDate() - i * 7);
    out.push(_isoDate(d));
  }
  return out;
}

function _weekLabel(weekStart) {
  const start = _utcDate(weekStart);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 4);
  const f = d => `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()]} ${d.getUTCDate()}`;
  return `${f(start)} – ${f(end)}`;
}

// Pure stats helper (also used by the Dashboard's track record). Only
// completed picks count.
function weeklyPickStats(picks) {
  const out = {};
  for (const dir of ["bullish", "bearish"]) {
    const done = picks.filter(p => p.status === "complete" && p.direction === dir);
    const right = done.filter(p => p.was_correct).length;
    const withSpy = done.filter(p => p.stock_return_pct !== null && p.spy_return_pct !== null);
    const excess = withSpy.length
      ? withSpy.reduce((s, p) => s + (dir === "bullish" ? Number(p.stock_return_pct) - Number(p.spy_return_pct)
                                                        : Number(p.spy_return_pct) - Number(p.stock_return_pct)), 0) / withSpy.length
      : null;
    out[dir] = { n: done.length, right, hitRate: done.length ? right / done.length : null, excess };
  }
  return out;
}

function _statsHtml(stats, title) {
  const row = (label, s) => {
    if (!s.n) return `<div class="bt-stat"><div class="bt-stat-label">${label}</div><div class="bt-stat-value">—</div><div class="bt-stat-sub">no scored picks yet</div></div>`;
    return `<div class="bt-stat">
      <div class="bt-stat-label">${label}</div>
      <div class="bt-stat-value">${s.right} of ${s.n} right <span class="bt-stat-rate">(${Math.round(s.hitRate * 100)}%)</span></div>
      <div class="bt-stat-sub">${s.excess === null ? "" : `${s.excess >= 0 ? "+" : ""}${s.excess.toFixed(2)} pts vs the market on average · `}${s.n < 10 ? "small sample — not evidence of skill either way" : "decent sample"}</div>
    </div>`;
  };
  return `<div class="bt-stats-title">${escapeHtml(title)}</div>
    <div class="bt-stats">${row("Expected UP picks", stats.bullish)}${row("Expected DOWN picks", stats.bearish)}</div>`;
}

function _miniBars(closes, entry) {
  if (!closes || !closes.length || !entry) return "";
  const pcts = closes.map(c => (Number(c.close) - Number(entry)) / Number(entry) * 100);
  const max = Math.max(2, ...pcts.map(p => Math.abs(p)));
  return `<div class="mini-bars">${closes.map((c, i) => {
    const p = pcts[i], h = Math.max(4, Math.abs(p) / max * 100);
    return `<div class="mini-bar-col">
      <div class="mini-bar-half top">${p >= 0 ? `<div class="mini-bar up" style="height:${h}%"></div>` : ""}</div>
      <div class="mini-bar-half bottom">${p < 0 ? `<div class="mini-bar down" style="height:${h}%"></div>` : ""}</div>
      <div class="mini-bar-val ${p >= 0 ? "bullish" : "bearish"}">${p >= 0 ? "+" : ""}${p.toFixed(1)}%</div>
      <div class="mini-bar-day">${DAY_NAMES[_utcDate(c.date).getUTCDay()]}</div>
    </div>`;
  }).join("")}</div>`;
}

function _pickCard(p) {
  const up = p.direction === "bullish";
  const picked = p.picked_at ? `picked ${_dayLabel(p.picked_at.slice(0, 10))}` : "";
  const reasons = (p.plain_reasons || []).slice(0, 2).map(r => `<li class="reason-chip">${escapeHtml(r)}</li>`).join("");
  let result;
  if (p.status === "complete") {
    result = `
      <div class="bt-verdict ${p.was_correct ? "right" : "wrong"}">${p.was_correct ? "✔ Right" : "✘ Wrong"} — ${up ? "expected up" : "expected down"}, ${escapeHtml(p.ticker)} ${Number(p.stock_return_pct) >= 0 ? "rose" : "fell"} ${Math.abs(Number(p.stock_return_pct)).toFixed(2)}% over the week</div>
      ${_miniBars(p.daily_closes, p.entry_price)}
      <div class="bt-returns">
        <div class="stat-tile"><div class="stat-label">${escapeHtml(p.ticker)}</div><div class="stat-value ${_pctClass(p.stock_return_pct)}">${_pct(p.stock_return_pct)}</div></div>
        <div class="stat-tile"><div class="stat-label">Sector fund (${escapeHtml(p.etf_ticker || "—")})</div><div class="stat-value ${_pctClass(p.etf_return_pct)}">${_pct(p.etf_return_pct)}</div></div>
        <div class="stat-tile"><div class="stat-label">Market (SPY)</div><div class="stat-value ${_pctClass(p.spy_return_pct)}">${_pct(p.spy_return_pct)}</div></div>
      </div>
      <div class="holding-meta">Entry: Monday's open $${Number(p.entry_price).toFixed(2)} · result measured to Friday's close</div>`;
  } else {
    const today = todayUtc();
    const msg = p.week_end < today ? "Week is over — scoring after the close; results appear shortly."
      : (p.week_start > today ? "Week hasn't started yet — results unlock Friday after the close."
                               : "In progress — results unlock Friday after the close.");
    result = `<div class="bt-pending">⏳ ${msg}</div>`;
  }
  return `
    <div class="bt-pick ${up ? "up" : "down"} ${p.status === "complete" ? (p.was_correct ? "right" : "wrong") : "pending"}">
      <div class="bt-pick-top">
        <div><span class="bt-pick-name">${escapeHtml(_stockName(p.ticker))}</span> <span class="week-ticker">${escapeHtml(p.ticker)}</span></div>
        <span class="bt-dir ${up ? "up" : "down"}">${up ? "▲ Expected UP" : "▼ Expected DOWN"}</span>
      </div>
      <div class="week-badge">${escapeHtml(sectorLabel(p.sector))} · ${escapeHtml(picked)}</div>
      <div class="sector-reason">${escapeHtml(p.reasoning || "")}</div>
      ${reasons ? `<ul class="reason-chips">${reasons}</ul>` : ""}
      ${result}
    </div>`;
}

function renderWeeklyPicksReport() {
  const el = document.getElementById("bt-picks");
  if (!el) return;
  const weeks = backtestWeekStarts();
  if (!backtestState.weekStart || !weeks.includes(backtestState.weekStart)) backtestState.weekStart = weeks[0];
  const picks = dataCache.weeklyPicks || [];

  document.getElementById("bt-week-pills").innerHTML = weeks.map(w => {
    const n = picks.filter(p => p.week_start === w).length;
    return `<button type="button" class="ghost bt-pill ${w === backtestState.weekStart ? "active" : ""}" data-bt-week="${w}">${_weekLabel(w)}${w === weeks[0] ? " · current" : ""}<span class="bt-pill-n">${n ? n + " pick" + (n > 1 ? "s" : "") : "no picks"}</span></button>`;
  }).join("");
  document.querySelectorAll("[data-bt-week]").forEach(b => b.addEventListener("click", () => {
    backtestState.weekStart = b.dataset.btWeek;
    renderWeeklyPicksReport();
  }));

  const forWeek = picks.filter(p => p.week_start === backtestState.weekStart).sort((a, b) => (a.rank || 0) - (b.rank || 0));
  const complete4 = picks.filter(p => p.status === "complete" && weeks.slice(1).concat(weeks[0]).includes(p.week_start));
  document.getElementById("bt-stats").innerHTML =
    _statsHtml(weeklyPickStats(forWeek), `Selected week (${_weekLabel(backtestState.weekStart)})`) +
    _statsHtml(weeklyPickStats(complete4), "All shown weeks combined");

  if (!forWeek.length) {
    el.innerHTML = `<p class="empty-note">${backtestState.weekStart > todayUtc()
      ? "This week's picks are frozen on the weekend — nothing recorded yet."
      : "No strong picks were recorded for this week. Graha only picks sectors whose sky signal is strong and consistent across the week; on a quiet week that means none."}</p>`;
    return;
  }
  el.innerHTML = forWeek.map(_pickCard).join("");
}

function _suggestionWeek(dateStr) { return mondayOf(dateStr); }

function suggestionRows() {
  return (dataCache.suggestedStocks || []).map(s => {
    const snap = _latestSnapshot(s.ticker);
    const now = snap ? Number(snap.price) : null;
    const then = s.price_at_suggestion !== null && s.price_at_suggestion !== undefined ? Number(s.price_at_suggestion) : null;
    const change = (now !== null && then) ? (now - then) / then * 100 : null;
    const right = change === null ? null : (s.direction === "bullish" ? change > 0 : change < 0);
    return { ...s, now, then, change, right, week: _suggestionWeek(s.date_suggested) };
  });
}

function renderSuggestionHistory() {
  const el = document.getElementById("bt-suggestions");
  if (!el) return;
  const rows = suggestionRows();
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No suggestions yet.</p>`; return; }

  const weeks = [...new Set(rows.map(r => r.week))].sort().reverse();
  const shown = backtestState.showAllSuggestions ? weeks : weeks.slice(0, 4);
  const scored = rows.filter(r => r.right !== null);
  const rightN = scored.filter(r => r.right).length;

  el.innerHTML = `
    <div class="empty-note movers-note">Every stock Graha has suggested, measured from the price when it was suggested to the latest watchlist price (approximate — that scan is pre-market, so it's effectively the prior close). Overall: <strong>${rightN} of ${scored.length}</strong> moved the way Graha said${scored.length ? ` (${Math.round(rightN / scored.length * 100)}%)` : ""}.</div>
    ${shown.map(w => `
      <div class="bt-week-group">
        <div class="bt-week-group-title">Week of ${_weekLabel(w)}</div>
        <div class="table-scroll"><table class="data-table"><thead><tr>
          <th>Ticker</th><th>Sector</th><th>Graha said</th><th>Suggested at</th><th>Latest</th><th>Move</th><th>Verdict</th></tr></thead><tbody>
          ${rows.filter(r => r.week === w).map(r => `<tr class="${r.right === null ? "" : (r.right ? "row-bullish" : "row-bearish")}">
            <td>${escapeHtml(r.ticker)}</td><td>${escapeHtml(sectorLabel(r.sector))}</td>
            <td>${r.direction === "bullish" ? "▲ up" : "▼ down"}</td>
            <td>${r.then !== null ? "$" + r.then.toFixed(2) : "—"}</td>
            <td>${r.now !== null ? "$" + r.now.toFixed(2) : "—"}</td>
            <td class="${_pctClass(r.change)}">${_pct(r.change)}</td>
            <td>${r.right === null ? "—" : (r.right ? "✔ right" : "✘ wrong")}</td></tr>`).join("")}
        </tbody></table></div>
      </div>`).join("")}
    ${weeks.length > 4 ? `<button type="button" class="ghost" id="bt-toggle-all" style="margin-top:12px">${backtestState.showAllSuggestions ? "Show only the last 4 weeks" : `Show all ${weeks.length} weeks`}</button>` : ""}`;
  const t = document.getElementById("bt-toggle-all");
  if (t) t.addEventListener("click", () => { backtestState.showAllSuggestions = !backtestState.showAllSuggestions; renderSuggestionHistory(); });
}

function renderBacktestTab() {
  renderWeeklyPicksReport();
  renderSuggestionHistory();
}
