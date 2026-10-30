"""
Thin wrapper around Supabase's auto-generated REST API (PostgREST).
No SDK needed -- just plain HTTP with the anon key, using Row Level Security
policies (set up in supabase/schema.sql) to keep this safe for a public repo.
"""
import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
# Server-side jobs (GitHub Actions) use the service role key when available,
# which bypasses RLS -- needed to WRITE data. The frontend only ever uses
# the anon key and only ever READS (or writes via safe, narrow policies).
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", SUPABASE_ANON_KEY)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def insert(table: str, rows) -> list:
    if isinstance(rows, dict):
        rows = [rows]
    resp = requests.post(_url(table), headers=HEADERS, json=rows, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Supabase insert failed [{resp.status_code}]: {resp.text}")
    return resp.json()


def select(table: str, params: dict = None) -> list:
    resp = requests.get(_url(table), headers=HEADERS, params=params or {}, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Supabase select failed [{resp.status_code}]: {resp.text}")
    return resp.json()


def update(table: str, params: dict, patch: dict) -> list:
    resp = requests.patch(_url(table), headers=HEADERS, params=params, json=patch, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Supabase update failed [{resp.status_code}]: {resp.text}")
    return resp.json()


def schema_ready(min_version: int = 2) -> bool:
    """True once supabase/schema.sql at `min_version` has been applied.

    New-feature jobs call this first and skip themselves (loudly) when it's
    False, so the older jobs keep running until the schema is re-run."""
    try:
        rows = select("schema_version", {"select": "version", "order": "version.desc", "limit": "1"})
    except Exception as e:  # table missing -> PostgREST 404
        print(f"schema_version unavailable ({e}); treating schema as pre-v{min_version}")
        return False
    ok = bool(rows) and int(rows[0]["version"]) >= min_version
    if not ok:
        print(f"SKIPPING: schema is older than v{min_version} -- re-run supabase/schema.sql")
    return ok


def upsert(table: str, rows, on_conflict: str) -> list:
    headers = {**HEADERS, "Prefer": f"resolution=merge-duplicates,return=representation"}
    resp = requests.post(_url(table), headers=headers,
                          params={"on_conflict": on_conflict},
                          json=rows if isinstance(rows, list) else [rows], timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Supabase upsert failed [{resp.status_code}]: {resp.text}")
    return resp.json()
