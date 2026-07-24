// This Week's Signals tab (sector grid + aspects) and Astro Stocks tab.
// Reads from the shared dataCache populated by app.js's loadAll().

function renderSectorCards() {
  const el = document.getElementById("sector-grid");
  const preds = dataCache.latestPredictions;
  if (!preds.length) { el.innerHTML = `<p class="empty-note">No signals logged yet — the daily job runs automatically on market days, or trigger it manually from the repo's Actions tab.</p>`; return; }
  el.innerHTML = preds.map((p, i) => `
    <div class="sector-card ${p.direction}">
      <div class="sector-card-top">
        <span class="sector-name">${p.sector.replace(/_/g, " ")}</span>
        <span class="sector-ticker">${p.ticker}</span>
      </div>
      <div class="sector-direction ${p.direction}">${p.direction} · ${p.possibility_indicator}%</div>
      <div class="possibility-bar-track"><div class="possibility-bar-fill" style="width:${p.possibility_indicator}%"></div></div>
      <div class="sector-reason">${(p.reasons || []).slice(0, 2).join(" · ")}</div>
      ${p.long_term_note ? `
        <button class="ghost read-more-btn" data-read-more="${i}">read more — the long-term case</button>
        <div class="long-term-note" id="long-term-note-${i}" hidden>${p.long_term_note}</div>
      ` : ""}
    </div>
  `).join("");

  el.querySelectorAll("[data-read-more]").forEach(btn => {
    btn.addEventListener("click", () => {
      const note = document.getElementById(`long-term-note-${btn.dataset.readMore}`);
      note.hidden = !note.hidden;
      btn.textContent = note.hidden ? "read more — the long-term case" : "show less";
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
