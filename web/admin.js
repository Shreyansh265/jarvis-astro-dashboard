// Admin Overview tab. Only ever rendered for an account whose own
// profiles.is_admin is true (checked in auth-gate.js before the tab
// button is even unhidden) -- but every mutation here still goes through
// the admin_set_banned RPC, which independently re-checks admin status
// server-side, so there's no client-side-only gate a user could bypass.
//
// Login-location resolution (IP -> city/country) is intentionally not
// wired up yet -- it reads from Supabase's own auth audit log via an
// admin-gated RPC that lands in a later commit, once its real column
// shape has been verified live rather than guessed.

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
      <td>${u.email}</td>
      <td>${(u.created_at || "").slice(0, 10)}</td>
      <td class="empty-note">not yet available</td>
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
}
