// Ask Graha: genuinely LLM-backed (Claude, via the `chat` Supabase Edge
// Function -- see supabase/functions/chat/index.ts), not a pattern-matching
// engine. This file is a thin caller: it forwards the signed-in user's own
// session token so the function can identify them and read their own
// RLS-scoped data server-side; it never touches ANTHROPIC_API_KEY (which
// never reaches the browser at all). "Memory" is still the chat_log table
// plus every underlying data table the function reads fresh each request.

const ChatEngine = {
  async ask(userText) {
    const session = await window.Auth.getSession();
    if (!session) throw new Error("You're not signed in.");

    const res = await fetch(`${window.JARVIS_CONFIG.SUPABASE_URL}/functions/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
        apikey: window.JARVIS_CONFIG.SUPABASE_ANON_KEY,
      },
      body: JSON.stringify({ message: userText }),
    });

    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON error body */ }

    if (!res.ok) {
      throw new Error(data.error || `Graha's chat service returned an error (${res.status}).`);
    }
    return data.reply || "Graha didn't have anything to say — try rephrasing your question.";
  },
};
