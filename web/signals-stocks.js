// This Week's Signals tab (sector grid + aspects) and Astro Stocks tab.
// Reads from the shared dataCache populated by app.js's loadAll().

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

function renderAstroStocks() {
  const el = document.getElementById("stocks-list");
  const rows = dataCache.suggestedStocks;
  if (!rows.length) { el.innerHTML = `<p class="empty-note">No active stock picks right now — Graha suggests individual stocks once a sector clears a confidence bar.</p>`; return; }

  const latestPriceByTicker = {};
  dataCache.marketSnapshot.forEach(r => {
    const existing = latestPriceByTicker[r.ticker];
    if (!existing || r.date > existing.date) latestPriceByTicker[r.ticker] = r;
  });

  el.innerHTML = rows.map(r => {
    const current = latestPriceByTicker[r.ticker];
    const currentPrice = current ? current.price : null;
    const pctSince = (currentPrice != null && r.price_at_suggestion)
      ? Math.round(((currentPrice - r.price_at_suggestion) / r.price_at_suggestion) * 10000) / 100
      : null;
    return `
    <div class="stock-card ${r.direction}">
      <div class="sector-card-top">
        <span class="sector-name">${r.ticker}</span>
        <button class="ghost" data-remove-stock="${r.id}">remove</button>
      </div>
      <div class="sector-ticker">${(r.sector || "").replace(/_/g, " ")} · suggested ${r.date_suggested}</div>
      <div class="sector-direction ${r.direction}">${r.direction}</div>
      <div class="holding-meta">at suggestion: ${r.price_at_suggestion != null ? "$" + r.price_at_suggestion : "—"}
        · now: ${currentPrice != null ? "$" + currentPrice : "—"}
        ${pctSince != null ? `<span class="${pctSince >= 0 ? "bullish" : "bearish"}"> (${pctSince >= 0 ? "+" : ""}${pctSince}%)</span>` : ""}
      </div>
      <div class="sector-reason">${r.reasoning}</div>
    </div>`;
  }).join("");

  document.querySelectorAll("[data-remove-stock]").forEach(btn => {
    btn.addEventListener("click", async () => {
      await SB.rpc("remove_suggested_stock", { p_id: Number(btn.dataset.removeStock) });
      await loadAll();
    });
  });
}
