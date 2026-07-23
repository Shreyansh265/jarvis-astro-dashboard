"""
Generates a short "explain it like I'm 5" summary of today's market, in
Graha's voice -- built entirely from OUR OWN signal + price data, not a
third-party news feed and not an LLM (Twelve Data's free tier has no news
endpoint anyway; confirmed 404).
"""
from datetime import date
import supabase_client as db


def _describe_sector_tone(sectors: dict) -> str:
    bullish = sorted(
        [(s, v) for s, v in sectors.items() if v["direction"] == "bullish"],
        key=lambda x: -x[1]["possibility_indicator"],
    )
    bearish = sorted(
        [(s, v) for s, v in sectors.items() if v["direction"] == "bearish"],
        key=lambda x: -x[1]["possibility_indicator"],
    )

    if len(bullish) > len(bearish):
        tone = (f"Today feels more sunny than stormy: {len(bullish)} sector(s) look good "
                f"(bullish) against {len(bearish)} that look rough (bearish), according to the planets.")
    elif len(bearish) > len(bullish):
        tone = (f"Today feels more stormy than sunny: {len(bearish)} sector(s) look rough "
                f"(bearish) against {len(bullish)} that look good (bullish), according to the planets.")
    else:
        tone = "Today's a mixed bag -- about as many sunny sectors as stormy ones."

    parts = [tone]
    if bullish:
        top = bullish[0]
        parts.append(f"The sunniest spot is {top[0].replace('_', ' ')} -- {top[1]['reasons'][0]}")
    if bearish:
        worst = bearish[0]
        parts.append(f"The stormiest is {worst[0].replace('_', ' ')} -- {worst[1]['reasons'][0]}")
    return " ".join(parts)


def _describe_market_move(snapshot_rows: list) -> str:
    movers = [r for r in snapshot_rows if r.get("percent_change") is not None]
    if not movers:
        return ""
    biggest = max(movers, key=lambda r: abs(r["percent_change"]))
    direction = "jumped up" if biggest["percent_change"] > 0 else "dropped down"
    return (f"The biggest single mover on Graha's watchlist today was {biggest['ticker']}, "
            f"which {direction} {abs(biggest['percent_change'])}%.")


def run_eli5(sectors: dict, snapshot_rows: list) -> str:
    today = date.today().isoformat()
    brief = (_describe_sector_tone(sectors) + " " + _describe_market_move(snapshot_rows)).strip()
    db.upsert("daily_briefs", {"date": today, "brief_text": brief}, on_conflict="date")
    return brief
