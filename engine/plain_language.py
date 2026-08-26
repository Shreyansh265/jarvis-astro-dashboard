"""
Rewrites a sector's astrological signal reasoning into plain, jargon-free
English -- the primary content on the This Week's Signals tab (Epic 4).
The astrological reasons/long_term_note stay exactly as they were and are
still stored and shown (behind an on-demand "show the astrological
reasoning" toggle in the frontend) -- this is a second, translated view of
the SAME reasoning, not a replacement source of truth.

One plain HTTP call per non-neutral sector per day (~10-14/day) -- a small,
predictable batch cost, not a per-user-message cost like the chat feature.
Uses Haiku (not Sonnet/Opus) deliberately: this is a bounded rewriting task
with no open-ended reasoning required, run automatically every day whether
anyone reads it or not, so it's worth being cost-conservative here in a way
the interactive chat feature (chat.py / the chat Edge Function) isn't.

Plain requests.post over Anthropic's REST API, no SDK -- same "no bundler,
no SDK beyond what a specific security-critical surface needs" pattern
supabase_client.py already uses for Supabase.
"""
import os
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are Graha, an astrology-based market-signal bot. You've already "
    "decided a sector's direction using astrological reasoning; your only "
    "job here is to re-explain that SAME reasoning in plain, everyday "
    "English a beginner investor could follow. Do not use planet names, "
    "zodiac signs, or astrological terms (retrograde, conjunct, trine, "
    "aspect, house, ruler, etc). Instead, translate what each factor "
    "represents behaviorally -- impulsiveness, caution, expansion, "
    "restriction, communication breakdowns, disruption, steady growth, and "
    "so on -- into a plain description of market mood or investor "
    "behavior. Ground every sentence only in the reasons given below; "
    "never invent a fact, ticker, price, or news event that isn't already "
    "there. Write 4-5 plain sentences, and be honest this is a "
    "probabilistic signal, not a certainty or financial advice."
)


def build_plain_language_note(sector: str, ticker: str, direction: str,
                               reasons: list, long_term_note: str = None) -> str | None:
    """Returns None (never raises) if ANTHROPIC_API_KEY isn't configured,
    the sector is neutral (nothing bullish/bearish to plainly explain), or
    the call fails -- this is a nice-to-have layer over the always-present
    astrological reasons, never a hard dependency for the daily job."""
    if not ANTHROPIC_API_KEY or direction == "neutral" or not reasons:
        return None

    user_content = (
        f"Sector: {sector.replace('_', ' ')} (ticker {ticker})\n"
        f"Direction: {direction}\n"
        "Reasons:\n" + "\n".join(f"- {r}" for r in reasons)
        + (f"\n\nLonger-term context:\n{long_term_note}" if long_term_note else "")
    )

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 400,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        return text or None
    except Exception as e:
        print(f"plain_language: Anthropic call failed for {sector}: {e}")
        return None
