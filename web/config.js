// Safe to be public: Supabase's "anon" key is designed for browser use and
// is constrained by Row Level Security policies (see supabase/schema.sql).
// Writes are only permitted on 'portfolio' and 'chat_log' — everything else
// is read-only from the browser and only written by the GitHub Actions jobs
// using a separate, private service_role key that never touches this repo.
window.JARVIS_CONFIG = {
  SUPABASE_URL: "https://upnxvtwsscchftwmtapm.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVwbnh2dHdzc2NjaGZ0d210YXBtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQyNDc1MDcsImV4cCI6MjA5OTgyMzUwN30.Eedf4-JndZmgaPPyZWguwoYDgi9mgaKEOmC1hRmqmUU"
};
