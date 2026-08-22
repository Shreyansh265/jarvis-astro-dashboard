// QQQ Analysis tab. Reads from dataCache.qqqCalls (populated by app.js's
// loadAll()) -- one row per day from engine/qqq_daily_call.py, never a
// bare/empty call (always a lean + all three risk-tier notes).

function renderQqqAnalysis() {
  const rows = dataCache.qqqCalls; // ordered call_date.desc
  const leanEl = document.getElementById("qqq-today-lean");
  const tilesEl = document.getElementById("qqq-stat-tiles");
  const tiersEl = document.getElementById("qqq-risk-tiers");
  const tbody = document.getElementById("qqq-table-body");

  if (!rows.length) {
    leanEl.innerHTML = `<p class="empty-note">No QQQ call yet -- runs each morning as part of the daily job, or trigger it manually from the repo's Actions tab.</p>`;
    tilesEl.innerHTML = "";
    tiersEl.innerHTML = "";
    tbody.innerHTML = `<tr><td colspan="6" class="empty-note">Nothing logged yet.</td></tr>`;
    return;
  }

  const latest = rows[0];
  const leanClass = latest.combined_lean === "call" ? "bullish" : (latest.combined_lean === "put" ? "bearish" : "");
  leanEl.innerHTML = `<div class="qqq-lean-headline ${leanClass}">${(latest.combined_lean || "neutral").toUpperCase()}</div>
    <div class="holding-meta">${latest.call_date} · astro bias ${latest.astro_bias || "—"} (${latest.astro_confidence != null ? latest.astro_confidence + "%" : "—"}) · technical bias ${latest.technical_bias || "—"}</div>`;

  tilesEl.innerHTML = `
    <div class="stat-tile"><div class="stat-label">Pivot</div><div class="stat-value">$${latest.pivot ?? "—"}</div></div>
    <div class="stat-tile"><div class="stat-label">R1 / R2</div><div class="stat-value">$${latest.r1 ?? "—"} / $${latest.r2 ?? "—"}</div></div>
    <div class="stat-tile"><div class="stat-label">S1 / S2</div><div class="stat-value">$${latest.s1 ?? "—"} / $${latest.s2 ?? "—"}</div></div>
  `;

  tiersEl.innerHTML = `
    <div class="qqq-tier"><div class="qqq-tier-label">Aggressive</div><div>${latest.aggressive_note || ""}</div></div>
    <div class="qqq-tier"><div class="qqq-tier-label">Moderate</div><div>${latest.moderate_note || ""}</div></div>
    <div class="qqq-tier"><div class="qqq-tier-label">Conservative</div><div>${latest.conservative_note || ""}</div></div>
  `;

  tbody.innerHTML = rows.slice(0, 60).map(r => `
    <tr class="${r.combined_lean === "call" ? "row-bullish" : (r.combined_lean === "put" ? "row-bearish" : "")}">
      <td>${r.call_date}</td>
      <td class="${r.combined_lean === "call" ? "bullish" : (r.combined_lean === "put" ? "bearish" : "")}">${(r.combined_lean || "neutral").toUpperCase()}</td>
      <td>${r.astro_bias ?? "—"} ${r.astro_confidence != null ? `(${r.astro_confidence}%)` : ""}</td>
      <td>${r.technical_bias ?? "—"}</td>
      <td>$${r.pivot ?? "—"}</td>
      <td>${r.combined_lean === "neutral" ? "n/a" : (r.was_correct == null ? "pending" : `<span class="status-badge ${r.was_correct ? "active" : "closed"}">${r.was_correct ? "correct" : "incorrect"}</span>`)}</td>
    </tr>
  `).join("");
}
