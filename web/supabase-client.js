// Minimal Supabase REST client for the browser -- no SDK bundle needed.
const SB = {
  async select(table, query = "") {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}?${query}`;
    const res = await fetch(url, { headers: SB._headers() });
    if (!res.ok) throw new Error(`Supabase select ${table} failed: ${res.status}`);
    return res.json();
  },
  async insert(table, row) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { ...SB._headers(), "Content-Type": "application/json", "Prefer": "return=representation" },
      body: JSON.stringify(row),
    });
    if (!res.ok) throw new Error(`Supabase insert ${table} failed: ${res.status} ${await res.text()}`);
    return res.json();
  },
  async del(table, query) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/${table}?${query}`;
    const res = await fetch(url, { method: "DELETE", headers: SB._headers() });
    if (!res.ok) throw new Error(`Supabase delete ${table} failed: ${res.status}`);
    return true;
  },
  async rpc(fnName, args = {}) {
    const url = `${window.JARVIS_CONFIG.SUPABASE_URL}/rest/v1/rpc/${fnName}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { ...SB._headers(), "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    if (!res.ok) throw new Error(`Supabase rpc ${fnName} failed: ${res.status} ${await res.text()}`);
    return res.status === 204 ? null : res.json();
  },
  _headers() {
    const key = window.JARVIS_CONFIG.SUPABASE_ANON_KEY;
    return { apikey: key, Authorization: `Bearer ${key}` };
  },
};
