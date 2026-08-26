// Admin Overview tab. Only ever rendered for an account whose own
// profiles.is_admin is true (checked in auth-gate.js before the tab
// button is even unhidden) -- but every mutation here still goes through
// the admin_set_banned RPC, which independently re-checks admin status
// server-side, so there's no client-side-only gate a user could bypass.
//
// Login-location resolution (IP -> city/country) is lazy and client-side
// only: it reads recent login events from Supabase's own auth audit log
// via the admin_recent_logins RPC (admin-gated server-side, same as
// every other admin RPC), then resolves each *distinct* IP to a
// city/country with a free, unauthenticated, HTTPS-capable lookup
// (ipapi.co -- no key, no server-side secret needed). Nothing here is
// stored -- it's recomputed fresh every time the admin tab loads, so
// this never persists per-login location PII the way a login-triggered
// server-side capture would.

async function resolveLoginLocations() {
  let logins;
  try {
    logins = await SB.rpc("admin_recent_logins", { limit_count: 500 });
  } catch (e) {
    return {}; // best-effort -- the user list/ban controls still work without this
  }

  // Keep only the most recent login per user.
  const latestByUser = {};
  for (const row of logins || []) {
    if (!row.user_id) continue;
    const prev = latestByUser[row.user_id];
    if (!prev || row.logged_in_at > prev.logged_in_at) latestByUser[row.user_id] = row;
  }

  const distinctIps = [...new Set(Object.values(latestByUser).map(r => r.ip_address).filter(Boolean))];
  const geoByIp = {};
  await Promise.all(distinctIps.map(async (ip) => {
    try {
      const res = await fetch(`https://ipapi.co/${encodeURIComponent(ip)}/json/`);
      if (!res.ok) return;
      const data = await res.json();
      if (data && !data.error) {
        geoByIp[ip] = [data.city, data.country_name].filter(Boolean).join(", ");
      }
    } catch (_) {
      // best-effort geo lookup -- a single failed IP just falls back to "unknown" below
    }
  }));

  const locationByUser = {};
  for (const [userId, row] of Object.entries(latestByUser)) {
    locationByUser[userId] = row.ip_address ? (geoByIp[row.ip_address] || "unknown") : "unknown";
  }
  return locationByUser;
}

async function loadAdminOverview() {
  if (!window.currentUser || !window.currentUser.isAdmin) return;

  const countEl = document.getElementById("admin-user-count");
  const bannedEl = document.getElementById("admin-banned-count");
  const tbody = document.getElementById("admin-users-table-body");

  let users;
  try {
    users = await SB.select("profiles", "order=created_at.desc&limit=500");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-note">Could not load users: ${e.message}</td></tr>`;
    return;
  }

  countEl.textContent = users.length;
  bannedEl.textContent = users.filter(u => u.is_banned).length;

  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-note">No users yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = users.map(u => `
    <tr class="${u.is_banned ? "row-bearish" : ""}">
      <td>${escapeHtml(u.email)}</td>
      <td>${(u.created_at || "").slice(0, 10)}</td>
      <td class="empty-note" data-location-for="${u.id}">resolving…</td>
      <td><span class="status-badge ${u.is_banned ? "closed" : "active"}">${u.is_banned ? "banned" : "active"}</span></td>
      <td>${u.id === window.currentUser.id ? "" : `<button class="ghost" data-toggle-ban="${u.id}" data-currently-banned="${u.is_banned}">${u.is_banned ? "unban" : "ban"}</button>`}</td>
    </tr>
  `).join("");

  tbody.querySelectorAll("[data-toggle-ban]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const targetId = btn.dataset.toggleBan;
      const currentlyBanned = btn.dataset.currentlyBanned === "true";
      try {
        await SB.rpc("admin_set_banned", { target_user_id: targetId, banned: !currentlyBanned });
        await loadAdminOverview();
      } catch (e) {
        alert(`Could not update ban status: ${e.message}`);
      }
    });
  });

  // Fills in after the table's already rendered -- IP geo-resolution is a
  // network round trip per distinct IP and shouldn't block showing the
  // user list and ban controls.
  resolveLoginLocations().then(locationByUser => {
    tbody.querySelectorAll("[data-location-for]").forEach(td => {
      const userId = td.dataset.locationFor;
      td.textContent = locationByUser[userId] || "no login recorded";
      td.classList.remove("empty-note");
    });
  });
}
