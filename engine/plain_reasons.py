"""
Deterministic plain-English phrasing for sector signals -- no LLM, no
astrological jargon in the output beyond the planet's name. Built directly
from the same planet-condition logic signals.py scores with (never by
regexing signals.py's reason strings), so the phrasing can't drift from
what actually moved the score.
"""
from rulerships import EXALTATION, DEBILITATION, PLANET_SECTOR_RULES

PLANET_THEME = {
    "Sun": "big-picture confidence",
    "Moon": "day-to-day mood",
    "Mercury": "communication, tech and deal-making",
    "Venus": "spending and comfort",
    "Mars": "drive, energy and heavy industry",
    "Jupiter": "growth and optimism",
    "Saturn": "caution and restriction",
    "Rahu": "sudden swings and hype",
    "Ketu": "uncertainty and letting go",
}

SECTOR_PLAIN = {
    "Energy": "crude oil & energy",
    "Financials": "banks & finance",
    "Technology": "information technology",
    "Healthcare": "healthcare",
    "Industrials": "industrials",
    "Materials_Mining": "metals & mining",
    "Consumer_Discretionary": "consumer spending",
    "Consumer_Staples": "everyday essentials",
    "Utilities": "utilities",
    "Real_Estate": "real estate",
    "Communication_Media": "media & communications",
    "Gold": "gold",
    "Silver": "silver",
    "Canada_Broad": "Canadian markets",
    "US_Broad": "the overall US market",
}

NODES = ("Rahu", "Ketu")


def planet_condition(planet: str, pos: dict) -> str:
    """exalted | debilitated | retrograde | neutral -- mirrors
    signals._planet_base_tone's precedence exactly."""
    sign = pos[planet]["sign"]
    if planet in EXALTATION and sign == EXALTATION[planet]:
        return "exalted"
    if planet in DEBILITATION and sign == DEBILITATION[planet]:
        return "debilitated"
    if pos[planet]["is_retrograde"]:
        return "retrograde"
    return "neutral"


def planet_phrase(planet: str, pos: dict) -> str:
    cond = planet_condition(planet, pos)
    theme = PLANET_THEME.get(planet, "its themes")
    if cond == "exalted":
        return f"{planet} is at its strongest ({theme}): a tailwind"
    if cond == "debilitated":
        return f"{planet} is at its weakest ({theme}): a headwind"
    if cond == "retrograde" and planet in NODES:
        return f"{planet}'s steady background pull ({theme}): a small risk of sudden moves"
    if cond == "retrograde":
        return f"{planet} is moving backwards ({theme}): expect choppy, reversal-prone trading"
    return f"{planet} is quiet ({theme})"


def aspect_phrase(asp: dict) -> str:
    p1, p2 = asp["planet1"], asp["planet2"]
    if asp["tone"] == "bullish":
        return f"{p1} and {p2} are working together: a helping hand"
    if asp["tone"] == "bearish":
        return f"{p1} and {p2} are pulling against each other: a drag"
    return f"{p1} and {p2} are close together: amplifies whatever else is going on"


def _priority(cond: str, planet: str) -> int:
    if cond in ("exalted", "debilitated"):
        return 0
    if cond == "retrograde" and planet not in NODES:
        return 1
    return 2


def _tone_of(cond: str, planet: str) -> str:
    """up | down | mixed -- which way this single factor pushes its sectors."""
    if cond == "exalted":
        return "up"
    if cond == "debilitated":
        return "down"
    return "mixed"


_MARK = {"up": "▲ ", "down": "▼ ", "mixed": "◆ "}


def sector_plain_reasons(sector: str, contributing_planets: list, pos: dict,
                         aspects: list, limit: int = 3, direction: str = None) -> list:
    """Up to `limit` short phrases for one sector on one day. Each is marked
    ▲ (helps), ▼ (hurts) or ◆ (mixed/choppy) so a mostly-bearish day can't
    read as a contradiction, and factors pointing the SAME way as the
    sector's overall direction are listed first (then strongest-first:
    exalted/debilitated, real retrogrades, aspects, node background)."""
    want = {"bullish": "up", "bearish": "down"}.get(direction)
    ranked = []
    for planet in contributing_planets:
        cond = planet_condition(planet, pos)
        tone = _tone_of(cond, planet)
        ranked.append((tone, _priority(cond, planet), planet_phrase(planet, pos)))
    for asp in aspects:
        if asp["tone"] not in ("bullish", "bearish"):
            continue
        for planet in (asp["planet1"], asp["planet2"]):
            rule = PLANET_SECTOR_RULES.get(planet)
            if rule and sector in rule["sectors"]:
                ranked.append(("up" if asp["tone"] == "bullish" else "down", 1.5, aspect_phrase(asp)))
                break

    def key(item):
        tone, prio, _ = item
        matches = 0 if (want and tone == want) else (1 if tone == "mixed" else 2)
        return (matches if want else 0, prio)

    ranked.sort(key=key)
    out = []
    for tone, _, phrase in ranked:
        marked = _MARK[tone] + phrase
        if marked not in out:
            out.append(marked)
    return out[:limit]


def lead_condition(contributing_planets: list, pos: dict, direction: str = None):
    """The planet whose condition most deserves a historical example. Among
    non-neutral conditions, one that points the SAME way as the sector's
    direction wins (exalted for bullish, debilitated for bearish) so the
    example actually illustrates the lean being shown; then exalted/
    debilitated beats a real retrograde beats node background.
    Returns (planet, condition, sign, is_retrograde) or None."""
    aligned = {"bullish": "exalted", "bearish": "debilitated"}.get(direction)
    best = None
    for planet in contributing_planets:
        cond = planet_condition(planet, pos)
        if cond == "neutral":
            continue
        key = (0 if cond == aligned else 1, _priority(cond, planet))
        if best is None or key < best[0]:
            best = (key, planet, cond, pos[planet]["sign"], pos[planet]["is_retrograde"])
    if not best:
        return None
    return best[1], best[2], best[3], best[4]


def analog_key(sector: str, planet: str, condition: str, sign: str) -> str:
    return f"{sector}|{planet}|{condition}|{sign}"


def sky_events(prev_pos: dict, pos: dict, aspects: list, prev_aspects: list) -> list:
    """Human-readable changes between two consecutive days' skies: sign
    changes, retrograde stations/turns, and aspects that newly tighten."""
    events = []
    for planet, now in pos.items():
        before = prev_pos.get(planet)
        if not before:
            continue
        if planet == "Moon":
            if now["sign"] != before["sign"]:
                events.append(f"Moon moves into {now['sign']}")
            continue
        if now["sign"] != before["sign"]:
            events.append(f"{planet} moves into {now['sign']}")
        if planet not in NODES and now["is_retrograde"] != before["is_retrograde"]:
            if now["is_retrograde"]:
                events.append(f"{planet} turns retrograde (starts moving backwards)")
            else:
                events.append(f"{planet} turns direct (back to normal motion)")
    seen = {(a["planet1"], a["planet2"], a["aspect"]) for a in prev_aspects}
    for a in aspects:
        if "Moon" in (a["planet1"], a["planet2"]):
            continue  # Moon aspects come and go daily; too noisy to list
        if (a["planet1"], a["planet2"], a["aspect"]) not in seen and a["tone"] in ("bullish", "bearish"):
            events.append(aspect_phrase(a))
    return events
