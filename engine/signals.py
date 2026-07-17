"""
Converts today's planetary positions into per-sector signals:
direction (bullish/bearish/neutral), a 0-100 "possibility indicator",
and a plain-language reason -- so nothing is a black box.

The possibility indicator combines:
  1. The rule's LEARNED weight (how often this exact rule has been right
     historically -- starts at a neutral prior, gets adjusted by weekly_review.py)
  2. How many independent rules agree on the same sector/direction
  3. Whether the trigger is a strong classical signal (exaltation/debilitation,
     tight aspect) vs a weak/generic one
"""
from collections import defaultdict
from rulerships import (PLANET_SECTOR_RULES, EXALTATION, DEBILITATION,
                         RETROGRADE_VOLATILITY_BOOST)
from ephemeris import get_positions, get_aspects


def _planet_base_tone(planet: str, pos: dict) -> tuple:
    """Returns (tone, strength, reason) for a single planet's own condition."""
    sign = pos[planet]["sign"]
    retro = pos[planet]["is_retrograde"]
    if planet in EXALTATION and sign == EXALTATION[planet]:
        return ("bullish", 0.9, f"{planet} is exalted in {sign} (classically its strongest placement)")
    if planet in DEBILITATION and sign == DEBILITATION[planet]:
        return ("bearish", 0.9, f"{planet} is debilitated in {sign} (classically its weakest placement)")
    if retro:
        return ("volatile", 0.6 + RETROGRADE_VOLATILITY_BOOST,
                f"{planet} is retrograde in {sign} -- expect instability/reversal risk in its sectors")
    return ("neutral", 0.3, f"{planet} is in {sign}, no strong classical signal")


def generate_signals(date=None, rule_weights: dict = None) -> dict:
    """
    rule_weights: optional dict {planet: weight} to override the static priors
    in rulerships.py -- this is how weekly_review.py's learning feeds back in.
    Returns {sector: {direction, score, reasons: [...], contributing_planets: [...]}}
    """
    from datetime import datetime, timezone
    date = date or datetime.now(timezone.utc)
    pos = get_positions(date)
    aspects = get_aspects(pos)

    sector_scores = defaultdict(lambda: {"bullish": 0.0, "bearish": 0.0, "reasons": [], "planets": []})

    for planet, rule in PLANET_SECTOR_RULES.items():
        if planet not in pos:
            continue
        weight = (rule_weights or {}).get(planet, rule["weight"])
        tone, strength, reason = _planet_base_tone(planet, pos)
        contribution = weight * strength

        for sector in rule["sectors"]:
            if tone == "bullish":
                sector_scores[sector]["bullish"] += contribution
                sector_scores[sector]["reasons"].append(reason)
                sector_scores[sector]["planets"].append(planet)
            elif tone == "bearish":
                sector_scores[sector]["bearish"] += contribution
                sector_scores[sector]["reasons"].append(reason)
                sector_scores[sector]["planets"].append(planet)
            elif tone == "volatile":
                # volatility affects both tails slightly, mostly a caution flag
                sector_scores[sector]["bullish"] += contribution * 0.3
                sector_scores[sector]["bearish"] += contribution * 0.3
                sector_scores[sector]["reasons"].append(reason)
                sector_scores[sector]["planets"].append(planet)

    # Apply aspects (a tight trine/square between two rulers amplifies or fights the base signal)
    for asp in aspects:
        for planet in (asp["planet1"], asp["planet2"]):
            rule = PLANET_SECTOR_RULES.get(planet)
            if not rule:
                continue
            for sector in rule["sectors"]:
                if sector not in sector_scores:
                    continue
                bump = 0.15
                if asp["tone"] == "bullish":
                    sector_scores[sector]["bullish"] += bump
                    sector_scores[sector]["reasons"].append(
                        f"{asp['planet1']}-{asp['planet2']} {asp['aspect']} supports this sector")
                elif asp["tone"] == "bearish":
                    sector_scores[sector]["bearish"] += bump
                    sector_scores[sector]["reasons"].append(
                        f"{asp['planet1']}-{asp['planet2']} {asp['aspect']} pressures this sector")

    # Finalize: direction + 0-100 possibility indicator
    results = {}
    for sector, s in sector_scores.items():
        net = s["bullish"] - s["bearish"]
        total = s["bullish"] + s["bearish"]
        if total == 0:
            continue
        confidence = min(100, round((abs(net) / total) * 50 + min(total, 1) * 50))
        direction = "bullish" if net > 0.05 else ("bearish" if net < -0.05 else "neutral")
        results[sector] = {
            "direction": direction,
            "possibility_indicator": confidence,
            "bullish_score": round(s["bullish"], 3),
            "bearish_score": round(s["bearish"], 3),
            "reasons": list(dict.fromkeys(s["reasons"])),  # dedupe, keep order
            "contributing_planets": list(dict.fromkeys(s["planets"])),
        }
    return {"date": date.isoformat(), "positions": pos, "aspects": aspects, "sectors": results}


if __name__ == "__main__":
    import json
    out = generate_signals()
    print(json.dumps({k: v for k, v in out["sectors"].items()}, indent=2))
