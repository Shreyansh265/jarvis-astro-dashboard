// This Week's Signals tab (sector grid + aspects) and Astro Stocks tab.
// Reads from the shared dataCache populated by app.js's loadAll().

function renderHorizonPicks() {
  const containers = { weekly: document.getElementById("horizon-weekly"),
                        monthly: document.getElementById("horizon-monthly"),
                        yearly: document.getElementById("horizon-yearly") };
  const rows = dataCache.horizonPicks;

  for (const horizon of ["weekly", "monthly", "yearly"]) {
    const el = containers[horizon];
    // horizonPicks is ordered period_start.desc, so the first period_start
    // seen per horizon is the current/latest one -- take only those rows.
    const forHorizon = rows.filter(r => r.horizon === horizon);
    if (!forHorizon.length) {
      el.innerHTML = `<p class="empty-note">No ${horizon} picks yet.</p>`;
      continue;
    }
    const latestPeriod = forHorizon[0].period_start;
    const current = forHorizon.filter(r => r.period_start === latestPeriod).sort((a, b) => a.rank - b.rank);
    el.innerHTML = current.map(r => `
      <div class="horizon-card ${r.today_tone === "bullish" ? "bullish" : (r.today_tone === "bearish" ? "bearish" : "")}">
        <div class="horizon-card-top">
          <span class="sector-name">${r.sector.replace(/_/g, " ")}</span>
          <span class="horizon-rank">#${r.rank}</span>
        </div>
        <div class="sector-direction ${r.today_tone === "bullish" ? "bullish" : "bearish"}">${r.today_tone}
          <span class="sample-quality-badge ${r.sample_quality}">${r.sample_quality} confidence</span>
        </div>
        <div class="sector-reason">Backtested hit-rate ${r.hit_rate != null ? Math.round(r.hit_rate * 100) + "%" : "—"}
          over ${r.sample_size} independent period(s) · driven by ${r.planet}</div>
        <div class="horizon-tickers">${(r.tickers || []).join(", ")}</div>
      </div>
    `).join("");
  }
}

function _multiline(text) {
  return escapeHtml(text).replace(/\n+/g, "<br>");
}

function _formatSector(sector) {
  return sector.replace(/_/g, " ");
}

async function _loadHorizonForSector(sector, horizon) {
  // Deliberately NOT reusing dataCache.horizonPicks here -- it's capped
  // at 60 rows across ALL horizons/periods combined, so a sector that
  // last ranked top-3 even a few months back can already be pushed out
  // of that shared cache, producing a false "never ranked" empty state.
  // This is a small dedicated query instead: the real most-recent period
  // this specific sector+horizon ever ranked in, or nothing.
  const rows = await SB.select("horizon_picks",
    `sector=eq.${encodeURIComponent(sector)}&horizon=eq.${horizon}&order=period_start.desc&limit=1`);
  return rows[0] || null;
}

function _horizonSectionHtml(horizon, label, row) {
  if (!row) {
    return `
      <div class="detail-section">
        <h3>${label}</h3>
        <p class="empty-note">Hasn't ranked in Graha's top 3 for the ${horizon} horizon yet — only the 3 strongest sectors get picked each period, so this is normal, not an error.</p>
      </div>`;
  }
  const tone = row.today_tone === "bullish" ? "bullish" : (row.today_tone === "bearish" ? "bearish" : "");
  return `
    <div class="detail-section">
      <h3>${label}</h3>
      <div class="sector-direction ${tone}">${escapeHtml(row.today_tone || "neutral")}
        <span class="sample-quality-badge ${row.sample_quality}">${escapeHtml(row.sample_quality)} confidence</span>
      </div>
      <div class="sector-reason">Backtested hit-rate ${row.hit_rate != null ? Math.round(row.hit_rate * 100) + "%" : "—"}
        over ${row.sample_size} independent period(s) · driven by ${escapeHtml(row.planet)} · as of ${row.period_start}</div>
    </div>`;
}

async function renderStockWatch() {
  const watch = dataCache.stockWatch;
  const form = document.getElementById("stock-watch-form");
  const summary = document.getElementById("stock-watch-summary");
  const summaryText = document.getElementById("stock-watch-summary-text");
  const cardEl = document.getElementById("stock-watch-card");

  if (!watch) {
    form.hidden = false;
    summary.hidden = true;
    cardEl.innerHTML = "";
    return;
  }

  form.hidden = true;
  summary.hidden = false;
  summaryText.innerHTML = `Currently tracking: <strong>${escapeHtml(watch.ticker)}</strong> (${escapeHtml(_formatSector(watch.sector))})`;
  cardEl.innerHTML = `<p class="empty-note">Loading full astro reading for ${escapeHtml(watch.ticker)}…</p>`;

  // Daily comes straight from the already-loaded dataCache -- its limit=40
  // window reliably covers "today" for any of the 15 sectors. Only the
  // weekly/monthly/yearly lookups need the dedicated scoped queries above.
  const pred = dataCache.latestPredictions.find(p => p.sector === watch.sector);
  const snapshot = _latestSnapshot(watch.ticker);
  // stock_detail's own sector fields are curated-ticker-only and stay
  // that way (see engine/portfolio_detail.py) -- only its PE/SMA/RSI/news
  // fields are used here, the astro sections above always come from this
  // user's own watch.sector, never from stock_detail's sector guess.
  const detail = dataCache.stockDetails.find(d => d.ticker === watch.ticker);

  let weeklyRow = null, monthlyRow = null, yearlyRow = null;
  try {
    [weeklyRow, monthlyRow, yearlyRow] = await Promise.all([
      _loadHorizonForSector(watch.sector, "weekly"),
      _loadHorizonForSector(watch.sector, "monthly"),
      _loadHorizonForSector(watch.sector, "yearly"),
    ]);
  } catch (e) {
    cardEl.innerHTML = `<p class="empty-note">Could not load the weekly/monthly/yearly read: ${escapeHtml(e.message)}</p>`;
    return;
  }

  const dailyHtml = pred ? `
    <div class="detail-section">
      <h3>Daily</h3>
      <div class="sector-direction ${pred.direction}">${escapeHtml(pred.direction)} · ${pred.possibility_indicator}%</div>
      <div class="sector-reason">${pred.plain_language_note ? _multiline(pred.plain_language_note) : escapeHtml((pred.reasons || []).slice(0, 3).join(" · "))}</div>
    </div>` : `
    <div class="detail-section">
      <h3>Daily</h3>
      <p class="empty-note">No signal logged yet today for this sector — check back after the daily job runs.</p>
    </div>`;

  const priceHtml = snapshot ? `
    <div class="detail-stats-row">
      <div class="stat-tile"><div class="stat-label">Price</div><div class="stat-value">$${snapshot.price}</div></div>
      <div class="stat-tile"><div class="stat-label">Change</div><div class="stat-value ${snapshot.percent_change >= 0 ? "bullish" : "bearish"}">${snapshot.percent_change != null ? snapshot.percent_change + "%" : "—"}</div></div>
    </div>` : "";

  const fundamentalsHtml = detail ? `
    <div class="detail-section">
      <h3>Technical &amp; Financial</h3>
      <div class="detail-stats-row">
        <div class="stat-tile"><div class="stat-label">SMA 20</div><div class="stat-value">${detail.sma_20 ?? "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">SMA 50</div><div class="stat-value">${detail.sma_50 ?? "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">RSI 14</div><div class="stat-value">${detail.rsi_14 ?? "—"}</div></div>
        <div class="stat-tile"><div class="stat-label">P/E</div><div class="stat-value">${detail.pe_ratio ?? "—"}</div></div>
      </div>
    </div>` : "";

  cardEl.innerHTML = `
    <div class="sector-card ${pred ? pred.direction : ""}">
      <div class="sector-card-top">
        <span class="sector-name">${escapeHtml(watch.ticker)}</span>
        <span class="sector-ticker">${escapeHtml(_formatSector(watch.sector))}</span>
      </div>
      ${priceHtml}
      ${dailyHtml}
      ${_horizonSectionHtml("weekly", "Weekly", weeklyRow)}
      ${_horizonSectionHtml("monthly", "Monthly", monthlyRow)}
      ${_horizonSectionHtml("yearly", "Yearly", yearlyRow)}
      ${fundamentalsHtml}
    </div>`;
}

function wireStockWatchForm() {
  const form = document.getElementById("stock-watch-form");
  if (!form) return;
  const changeBtn = document.getElementById("watch-change-btn");
  const stopBtn = document.getElementById("watch-stop-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticker = document.getElementById("watch-ticker").value.trim().toUpperCase();
    const sector = document.getElementById("watch-sector").value;
    if (!ticker || !sector) return;
    if (dataCache.stockWatch && !confirm(`Replace ${dataCache.stockWatch.ticker} with ${ticker}?`)) return;

    const submitBtn = document.getElementById("watch-submit-btn");
    submitBtn.disabled = true;
    try {
      await SB.upsert("stock_watch", { ticker, sector }, "user_id");
      form.reset();
      await loadAll();
    } catch (err) {
      alert(`Could not track ${ticker}: ${err.message}`);
    } finally {
      submitBtn.disabled = false;
    }
  });

  changeBtn.addEventListener("click", () => {
    const watch = dataCache.stockWatch;
    document.getElementById("stock-watch-summary").hidden = true;
    form.hidden = false;
    if (watch) {
      document.getElementById("watch-ticker").value = watch.ticker;
      document.getElementById("watch-sector").value = watch.sector;
    }
  });

  stopBtn.addEventListener("click", async () => {
    if (!confirm("Stop tracking this stock?")) return;
    try {
      await SB.del("stock_watch", `user_id=eq.${window.currentUser.id}`);
      await loadAll();
    } catch (err) {
      alert(`Could not stop tracking: ${err.message}`);
    }
  });
}
document.addEventListener("DOMContentLoaded", wireStockWatchForm);

function renderSectorCards() {
  const el = document.getElementById("sector-grid");
  const preds = dataCache.latestPredictions;
  if (!preds.length) { el.innerHTML = `<p class="empty-note">No signals logged yet — the daily job runs automatically on market days, or trigger it manually from the repo's Actions tab.</p>`; return; }
  el.innerHTML = preds.map((p, i) => {
    // plain_language_note (Claude, plain English, no astrology jargon) is
    // the primary explanation now -- the original astrological reasons/
    // long_term_note are demoted to an on-demand toggle, not deleted
    // (hiding that this is astrology-driven would contradict the
    // project's own honesty-first disclaimer). Falls back to the raw
    // reasons preview when plain_language_note isn't there yet (neutral
    // sector, or ANTHROPIC_API_KEY not configured yet).
    const primaryText = p.plain_language_note
      ? _multiline(p.plain_language_note)
      : escapeHtml((p.reasons || []).slice(0, 2).join(" · "));
    const hasAstroDetail = (p.reasons && p.reasons.length) || p.long_term_note;

    return `
    <div class="sector-card ${p.direction}">
      <div class="sector-card-top">
        <span class="sector-name">${p.sector.replace(/_/g, " ")}</span>
        <span class="sector-ticker">${p.ticker}</span>
      </div>
      <div class="sector-direction ${p.direction}">${p.direction} · ${p.possibility_indicator}%</div>
      <div class="possibility-bar-track"><div class="possibility-bar-fill" style="width:${p.possibility_indicator}%"></div></div>
      <div class="sector-reason">${primaryText}</div>
      ${hasAstroDetail ? `
        <button class="ghost read-more-btn" data-astro-toggle="${i}">show the astrological reasoning</button>
        <div class="long-term-note" id="astro-detail-${i}" hidden>
          ${p.reasons && p.reasons.length ? `<div class="sector-reason">${escapeHtml(p.reasons.join(" · "))}</div>` : ""}
          ${p.long_term_note ? `<div style="margin-top:8px">${_multiline(p.long_term_note)}</div>` : ""}
        </div>
      ` : ""}
    </div>
  `;
  }).join("");

  el.querySelectorAll("[data-astro-toggle]").forEach(btn => {
    btn.addEventListener("click", () => {
      const note = document.getElementById(`astro-detail-${btn.dataset.astroToggle}`);
      note.hidden = !note.hidden;
      btn.textContent = note.hidden ? "show the astrological reasoning" : "hide the astrological reasoning";
    });
  });
}

function renderAspects() {
  const el = document.getElementById("aspects-list");
  const aspects = (dataCache.latestLog && dataCache.latestLog.aspects) || [];
  if (!aspects.length) { el.innerHTML = `<p class="empty-note">No notable planetary aspects today.</p>`; return; }
  el.innerHTML = aspects.map(a => `
    <div class="aspect-row">
      <span class="aspect-tone ${a.tone === "bullish" ? "bullish" : (a.tone === "bearish" ? "bearish" : "")}">${a.aspect}</span>
      <span>${a.planet1} – ${a.planet2}</span>
      <span class="holding-meta">orb ${a.exact_diff}°</span>
    </div>
  `).join("");
}

// Note: this join only works because stock_picks.py only ever suggests
// tickers drawn from rulerships.SECTOR_TOP_STOCKS, and market_watch.py
// prices exactly that same curated list every day -- if stock_picks.py
// ever suggests outside that list, this lookup will silently come up empty.
function _snapshotAtOrBefore(ticker, cutoffDateStr) {
  // dataCache.marketSnapshot is ordered date.desc, so the first row for
  // this ticker with date <= cutoff is the closest-at-or-before match.
  // cutoffDateStr comparison is by UTC calendar date (not exact ET) --
  // an approximation, but it never looks ahead of the cutoff, which is
  // the property that actually matters here.
  return dataCache.marketSnapshot.find(r => r.ticker === ticker && r.date <= cutoffDateStr) || null;
}

function _latestSnapshot(ticker) {
  return dataCache.marketSnapshot.find(r => r.ticker === ticker) || null; // date.desc order -> first = latest
}

function renderAstroStocks() {
  const tbody = document.getElementById("stocks-table-body");
  const rows = dataCache.suggestedStocks;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-note">No stock picks yet — Graha suggests individual stocks once a sector clears a confidence bar.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(r => {
    const isActive = r.is_active;
    const priceRow = isActive ? _latestSnapshot(r.ticker) : _snapshotAtOrBefore(r.ticker, (r.removed_at || "").slice(0, 10));
    const comparePrice = priceRow ? Number(priceRow.price) : null;
    const pctSince = (comparePrice != null && r.price_at_suggestion)
      ? Math.round(((comparePrice - r.price_at_suggestion) / r.price_at_suggestion) * 10000) / 100
      : null;
    const suggestedAt = new Date(r.created_at);
    return `
    <tr class="${r.direction === "bullish" ? "row-bullish" : (r.direction === "bearish" ? "row-bearish" : "")}">
      <td>${r.date_suggested}</td>
      <td>${suggestedAt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</td>
      <td>${r.ticker}</td>
      <td>${(r.sector || "").replace(/_/g, " ")}</td>
      <td class="${r.direction === "bullish" ? "bullish" : (r.direction === "bearish" ? "bearish" : "")}">${r.direction}</td>
      <td>${r.price_at_suggestion != null ? "$" + r.price_at_suggestion : "—"}</td>
      <td>${comparePrice != null ? "$" + comparePrice : "—"} ${!isActive ? '<span class="holding-meta">(closed)</span>' : '<span class="holding-meta">(current)</span>'}</td>
      <td class="${pctSince == null ? "" : (pctSince >= 0 ? "bullish" : "bearish")}">${pctSince != null ? `${pctSince >= 0 ? "+" : ""}${pctSince}%` : "—"}</td>
      <td><span class="status-badge ${isActive ? "active" : "closed"}">${isActive ? "active" : "closed"}</span></td>
      <td>
        <button class="ghost" data-add-signal-ticker="${r.ticker}" data-add-signal-price="${comparePrice != null ? comparePrice : (r.price_at_suggestion || "")}">+ portfolio</button>
        ${isActive ? `<button class="ghost" data-remove-stock="${r.id}">remove</button>` : ""}
      </td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll("[data-remove-stock]").forEach(btn => {
    btn.addEventListener("click", async () => {
      await SB.rpc("remove_suggested_stock", { p_id: Number(btn.dataset.removeStock) });
      await loadAll();
    });
  });
  tbody.querySelectorAll("[data-add-signal-ticker]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const price = parseFloat(btn.dataset.addSignalPrice);
      if (!price) return;
      await SB.insert("portfolio", { ticker: btn.dataset.addSignalTicker, buy_price: price, quantity: 1, exchange: "NYSE" });
      await loadAll();
    });
  });
}
