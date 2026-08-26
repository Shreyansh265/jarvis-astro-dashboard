// Minimal Supabase REST client for the browser -- no SDK bundle needed for
// plain data CRUD (auth session handling is the one place this project
// uses a real SDK -- see auth-client.js -- since refresh-token rotation
// and revocation are exactly the kind of subtle correctness surface not
// worth reinventing for a security-critical feature; that judgment
// doesn't apply to simple PostgREST calls, so this stays hand-rolled).
const SB = {
  async select(table, query = "") {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}?${query}`;
    const res = await fetch(url, { headers: await SB._headers() });
    if (!res.ok) throw new Error(`Supabase select ${table} failed: ${res.status}`);
    return res.json();
  },
  async insert(table, row) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { ...(await SB._headers()), "Content-Type": "application/json", "Prefer": "return=representation" },
      body: JSON.stringify(row),
    });
    if (!res.ok) throw new Error(`Supabase insert ${table} failed: ${res.status} ${await res.text()}`);
    return res.json();
  },
  async update(table, query, patch) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}?${query}`;
    const res = await fetch(url, {
      method: "PATCH",
      headers: { ...(await SB._headers()), "Content-Type": "application/json", "Prefer": "return=representation" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error(`Supabase update ${table} failed: ${res.status} ${await res.text()}`);
    return res.json();
  },
  async del(table, query) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}?${query}`;
    const res = await fetch(url, { method: "DELETE", headers: await SB._headers() });
    if (!res.ok) throw new Error(`Supabase delete ${table} failed: ${res.status}`);
    return true;
  },
  async rpc(fnName, args = {}) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/rpc/${fnName}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { ...(await SB._headers()), "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    if (!res.ok) throw new Error(`Supabase rpc ${fnName} failed: ${res.status} ${await res.text()}`);
    return res.status === 204 ? null : res.json();
  },
  // apikey is always the anon key (required by PostgREST for routing/
  // rate-limiting regardless of auth state). Authorization is the logged-
  // in user's own JWT once a session exists -- that's what makes
  // auth.uid() resolve inside RLS policies -- falling back to the anon
  // key alone before login (anonymous/public-read access only).
  async _headers() {
    const anonKey = window.JARVIS_CONFIG.SUPABASE_ANON_KEY;
    let accessToken = anonKey;
    if (window.Auth && window.Auth.client) {
      const { data } = await window.Auth.client.auth.getSession();
      if (data && data.session) accessToken = data.session.access_token;
    }
    return { apikey: anonKey, Authorization: `Bearer ${accessToken}` };
  },
};
