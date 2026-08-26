// Gates the whole dashboard behind sign-in/sign-up. Waits for
// auth-client.js's initial session check (auth-client-ready event) before
// deciding what to show, rather than assuming window.Auth is ready
// immediately -- it's a module script, its top-level async work needs a
// moment even though it always finishes before DOMContentLoaded fires.

let authClientReady = false;
window.addEventListener("auth-client-ready", () => { authClientReady = true; handleAuthState(); });

function showGate(mode) {
  document.getElementById("auth-gate").hidden = false;
  document.getElementById("dashboard-wrap").hidden = true;
  document.getElementById("auth-tabs").hidden = false;
  document.getElementById("auth-status-note").textContent = "";
  document.getElementById("signin-form").hidden = mode !== "signin";
  document.getElementById("signup-form").hidden = mode !== "signup";
}

function showDashboard() {
  document.getElementById("auth-gate").hidden = true;
  document.getElementById("dashboard-wrap").hidden = false;
}

async function handleAuthState() {
  if (!authClientReady) return;
  const session = await window.Auth.getSession();
  if (!session) {
    showGate("signin");
    return;
  }

  const profile = await window.Auth.getMyProfile();
  if (profile && profile.is_banned) {
    await window.Auth.signOut();
    document.getElementById("auth-status-note").textContent = "This account has been suspended.";
    document.getElementById("auth-tabs").hidden = true;
    document.getElementById("signin-form").hidden = true;
    document.getElementById("signup-form").hidden = true;
    document.getElementById("auth-gate").hidden = false;
    document.getElementById("dashboard-wrap").hidden = true;
    return;
  }

  window.currentUser = { id: session.user.id, email: session.user.email, isAdmin: !!(profile && profile.is_admin) };
  document.getElementById("admin-tab-btn").hidden = !window.currentUser.isAdmin;
  showDashboard();

  // Dashboard data loading only ever starts once auth has actually
  // succeeded -- app.js's own DOMContentLoaded handler no longer calls
  // loadAll()/loadChatHistory() directly.
  if (typeof loadAll === "function") loadAll();
  if (typeof loadChatHistory === "function") loadChatHistory();
  if (window.currentUser.isAdmin && typeof loadAdminOverview === "function") loadAdminOverview();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-auth-tab]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-auth-tab]").forEach(b => b.classList.toggle("active", b === btn));
      showGate(btn.dataset.authTab);
    });
  });

  document.getElementById("signin-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("signin-error");
    errEl.textContent = "";
    try {
      await window.Auth.signIn(
        document.getElementById("signin-email").value.trim(),
        document.getElementById("signin-password").value,
      );
      // onAuthStateChange fires and handleAuthState() re-runs from there.
    } catch (err) {
      errEl.textContent = err.message || "Sign in failed.";
    }
  });

  document.getElementById("signup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("signup-error");
    errEl.textContent = "";
    try {
      const data = await window.Auth.signUp(
        document.getElementById("signup-email").value.trim(),
        document.getElementById("signup-password").value,
      );
      if (data.session) {
        // Email confirmation is disabled on this project -- signed in immediately.
        return;
      }
      document.getElementById("signup-form").hidden = true;
      document.getElementById("auth-tabs").hidden = true;
      document.getElementById("auth-status-note").textContent =
        "Almost there — check your email to confirm your account, then sign in.";
    } catch (err) {
      errEl.textContent = err.message || "Sign up failed.";
    }
  });

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await window.Auth.signOut();
  });

  window.addEventListener("auth-state-change", () => handleAuthState());
  handleAuthState(); // in case auth-client-ready already fired before this listener attached
});
