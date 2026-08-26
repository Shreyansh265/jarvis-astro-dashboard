// Auth session management via the real Supabase JS client, imported as an
// ES module straight from a CDN (esm.sh) -- no bundler, no build step,
// consistent with this project's no-tooling frontend, but using the real
// library specifically for session handling (refresh-token rotation
// across tabs, correct server-side revocation on logout, expiry timing)
// rather than reimplementing that over raw fetch -- those are exactly the
// subtle-bug-prone parts not worth re-deriving for a security-critical
// feature. Plain data CRUD stays hand-rolled in supabase-client.js.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabase = createClient(window.JARVIS_CONFIG.SUPABASE_URL, window.JARVIS_CONFIG.SUPABASE_ANON_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
});

window.Auth = {
  client: supabase,

  async signUp(email, password) {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    return data;
  },

  async signIn(email, password) {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data;
  },

  async signOut() {
    // Real revocation, not just clearing local storage -- a token
    // exfiltrated via some other bug must actually stop working on
    // logout, not just be forgotten by this one tab.
    await supabase.auth.signOut();
  },

  async getSession() {
    const { data } = await supabase.auth.getSession();
    return data.session;
  },

  async getMyProfile() {
    const session = await this.getSession();
    if (!session) return null;
    const res = await fetch(`${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/profiles?id=eq.${session.user.id}`, {
      headers: { apikey: window.JARVIS_CONFIG.SUPABASE_ANON_KEY, Authorization: `Bearer ${session.access_token}` },
    });
    const rows = await res.json();
    return rows[0] || null;
  },
};

supabase.auth.onAuthStateChange((event, session) => {
  window.dispatchEvent(new CustomEvent("auth-state-change", { detail: { event, session } }));
});

// Fires once, after the initial session check (from localStorage / URL
// fragment) has resolved -- the auth gate waits for this before deciding
// whether to show the login form or the dashboard, rather than assuming
// window.Auth is ready the instant this file is parsed (module scripts
// execute after all plain scripts but their top-level async work here
// still needs a moment).
supabase.auth.getSession().then(() => {
  window.dispatchEvent(new Event("auth-client-ready"));
});
