// QQQ Analysis tab. Reads from dataCache.qqqSignals (populated by app.js's
// loadAll()) -- see engine/qqq_monitor.py for how these rows get written.

function renderQqqAnalysis() {
  const rows = dataCache.qqqSignals; // ordered ts.desc
  const tilesEl = document.getElementById("qqq-stat-tiles");
  const latestEl = document.getElementById("qqq-latest-signal");
  const sparkEl = document.getElementById("qqq-sparkline");
  const tbody = document.getElementById("qqq-table-body");

  if (!rows.length) {
    tilesEl.innerHTML = "";
    latestEl.innerHTML = `<p class="empty-note">No QQQ session data yet -- the intraday job runs ~9:25am ET on market days, or trigger it manually from the repo's Actions tab.</p>`;
    sparkEl.innerHTML = "";
    tbody.innerHTML = `<tr><td colspan="7" class="empty-note">Nothing logged yet.</td></tr>`;
    return;
  }

  const latest = rows[0];
  tilesEl.innerHTML = `
    <div class="stat-tile"><div class="stat-label">Price</div><div class="stat-value">$${latest.price}</div></div>
    <div class="stat-tile"><div class="stat-label">VWAP</div><div class="stat-value">$${latest.vwap ?? "—"}</div></div>
    <div class="stat-tile"><div class="stat-label">Pivot</div><div class="stat-value">$${latest.pivot ?? "—"}</div></div>
    <div class="stat-tile"><div class="stat-label">Signal</div><div class="stat-value ${latest.signal === "BUY" ? "bullish" : (latest.signal === "SHORT" ? "bearish" : "")}">${latest.signal}</div></div>
  `;
  latestEl.innerHTML = `<strong>${latest.signal}</strong> as of ${new Date(latest.ts).toLocaleTimeString()} — ${latest.reasoning || ""}<br>
    <span class="holding-meta">R2 ${latest.r2 ?? "—"} / R1 ${latest.r1 ?? "—"} / S1 ${latest.s1 ?? "—"} / S2 ${latest.s2 ?? "—"} · EMA9 ${latest.ema9 ?? "—"} / EMA20 ${latest.ema20 ?? "—"} · Opening range ${latest.opening_range_low ?? "—"}-${latest.opening_range_high ?? "—"}</span>`;

  const closes = rows.slice(0, 60).map(r => Number(r.price)).reverse();
  if (closes.length >= 2) {
    const min = Math.min(...closes), max = Math.max(...closes);
    const w = 600, h = 70, pad = 4;
    const range = (max - min) || 1;
    const points = closes.map((v, i) => {
      const x = pad + (i / (closes.length - 1)) * (w - pad * 2);
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    const trendUp = closes[closes.length - 1] >= closes[0];
    sparkEl.innerHTML = `<svg viewBox="0 0 ${w} ${h}" class="sparkline ${trendUp ? "bullish" : "bearish"}" preserveAspectRatio="none">
      <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" />
    </svg>`;
  } else {
    sparkEl.innerHTML = "";
  }

  tbody.innerHTML = rows.slice(0, 50).map(r => `
    <tr class="${r.signal === "BUY" ? "row-bullish" : (r.signal === "SHORT" ? "row-bearish" : "")}">
      <td>${new Date(r.ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</td>
      <td class="${r.signal === "BUY" ? "bullish" : (r.signal === "SHORT" ? "bearish" : "")}">${r.signal}</td>
      <td>$${r.price}</td>
      <td>$${r.vwap ?? "—"}</td>
      <td>$${r.pivot ?? "—"}</td>
      <td>${r.astro_bias ?? "—"} ${r.astro_possibility_indicator != null ? `(${r.astro_possibility_indicator}%)` : ""}</td>
      <td>${r.signal === "HOLD" ? "n/a" : `<span class="status-badge ${r.outcome === "correct" ? "active" : (r.outcome === "incorrect" ? "closed" : "")}">${r.outcome}</span>`}</td>
    </tr>
  `).join("");
}
