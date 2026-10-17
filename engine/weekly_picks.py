"""
Graha's frozen weekly picks. Created on the weekend for the COMING trading
week from the already-computed sector_forecast (pure compute, zero API
credits) and never regenerated once the week starts -- picked_at is the
hindsight-proof receipt shown in the UI.

Rules (decided with the user):
  * Only strong signals, up to MAX_PICKS. A quiet week yields fewer picks
    (or none) -- weak picks are never padded in to look fuller.
  * A sector qualifies when, across that week's trading days, one direction
    is signalled on >= MIN_AGREEING_DAYS days and the mean strength of those
    days is >= STRENGTH_BAR (same bar as stock_picks.CONFIDENCE_BAR).
  * One lead stock per sector (first in SECTOR_TOP_STOCKS); sectors without a
    curated stock (US_Broad, Silver) can't be picked.
  * bullish = "expected up", bearish = "expected down" -- scored separately.
"""
from datetime import date, datetime, timedelta, timezone
import supabase_client as db
from rulerships import SECTOR_TICKERS, SECTOR_TOP_STOCKS
import trading_calendar as cal

MAX_PICKS = 5
STRENGTH_BAR = 65
MIN_AGREEING_DAYS = 3


def select_picks(forecast_rows: list, trading_days: list) -> list:
    """Pure: forecast rows for the week -> ordered pick dicts."""
    days = {d.isoformat() for d in trading_days}
    by_sector = {}
    for r in forecast_rows:
        if r["forecast_date"] in days:
            by_sector.setdefault(r["sector"], []).append(r)

    candidates = []
    for sector, rows in by_sector.items():
        if not SECTOR_TOP_STOCKS.get(sector) or sector not in SECTOR_TICKERS:
            continue
        for direction in ("bullish", "bearish"):
            agreeing = [r for r in rows if r.get("has_signal") and r["direction"] == direction]
            if len(agreeing) < MIN_AGREEING_DAYS:
                continue
            mean_strength = sum(float(r["strength"]) for r in agreeing) / len(agreeing)
            if mean_strength < STRENGTH_BAR:
                continue
            best = max(agreeing, key=lambda r: float(r["strength"]))
            candidates.append({
                "sector": sector, "direction": direction, "strength": round(mean_strength, 1),
                "agreeing": len(agreeing), "total": len(rows),
                "plain_reasons": best.get("plain_reasons") or [],
            })
    candidates.sort(key=lambda c: (-c["strength"], c["sector"]))
    picks, seen = [], set()
    for c in candidates:
        if c["sector"] in seen:
            continue  # a sector can't be both up and down in one week
        seen.add(c["sector"])
        picks.append(c)
        if len(picks) == MAX_PICKS:
            break
    return picks


def create_weekly_picks(today: date = None) -> list:
    today = today or datetime.now(timezone.utc).date()
    if today.weekday() < 5:
        print("weekly_picks: picks are only created on the weekend for the coming week "
              "(never mid-week -- that would be hindsight); skipping.")
        return []
    monday = cal.next_monday(today)
    first, last = cal.week_bounds(monday)
    if not first:
        print(f"weekly_picks: market closed all week of {monday}; no picks.")
        return []
    existing = db.select("weekly_picks", {"week_start": f"eq.{first.isoformat()}", "limit": "1"})
    if existing:
        print(f"weekly_picks: week of {first} already has frozen picks; leaving them untouched.")
        return []

    trading_days = [monday + timedelta(days=i) for i in range(5)
                    if cal.is_trading_day(monday + timedelta(days=i))]
    forecast = db.select("sector_forecast", {
        "forecast_date": f"gte.{first.isoformat()}", "limit": "1000"})
    forecast = [r for r in forecast if r["forecast_date"] <= last.isoformat()]
    picks = select_picks(forecast, trading_days)

    rows = []
    for rank, p in enumerate(picks, start=1):
        word = "up" if p["direction"] == "bullish" else "down"
        reasoning = (f"Sky leans {word} on {p['agreeing']} of {p['total']} trading days "
                     f"(average strength {p['strength']}/100)")
        rows.append({
            "week_start": first.isoformat(), "week_end": last.isoformat(),
            "ticker": SECTOR_TOP_STOCKS[p["sector"]][0], "sector": p["sector"],
            "etf_ticker": SECTOR_TICKERS[p["sector"]], "direction": p["direction"],
            "rank": rank, "strength": p["strength"], "reasoning": reasoning,
            "plain_reasons": p["plain_reasons"], "status": "pending",
        })
    if rows:
        db.insert("weekly_picks", rows)
    print(f"weekly_picks: froze {len(rows)} pick(s) for week of {first}")
    return rows


if __name__ == "__main__":
    create_weekly_picks()
