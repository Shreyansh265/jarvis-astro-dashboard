"""
Forward-looking day-by-day sector forecast (default 14 days ahead).

signals.generate_signals() is pure compute (planetary positions only, no
network or DB), so a forecast is just that function run for each future day
at 12:00 UTC (about the US open) with the current learned rule_weights.

Honesty notes baked into the data:
  * ALL 15 sectors get a row every day. A sector generate_signals() doesn't
    return (no exalted/debilitated/retrograde ruler) is stored has_signal=
    false -- "no astrological signal", never a fake flat forecast. Silver has
    no planetary rule at all and is always has_signal=false.
  * Most sector conditions last weeks; only the Moon and aspects change day
    to day, so many days will look identical. sky_events() captures what
    actually changes so the UI can lead with that instead of five copies.
  * Only forecast_date >= today is written; past rows are never rewritten.
"""
from datetime import date, datetime, timedelta, timezone
import supabase_client as db
from rulerships import SECTOR_TICKERS, SECTOR_STOCK_UNIVERSE
from signals import generate_signals
from ephemeris import get_positions, get_aspects
import plain_reasons as pr
import trading_calendar as cal

DEFAULT_DAYS = 14


def _noon_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)


def build_forecast(rule_weights: dict, start: date, days: int = DEFAULT_DAYS,
                   signals_fn=generate_signals, positions_fn=get_positions,
                   aspects_fn=get_aspects):
    """Returns (sector_rows, day_rows). Pure -- no DB access."""
    sector_rows, day_rows = [], []
    prev_pos = positions_fn(_noon_utc(start - timedelta(days=1)))
    prev_aspects = aspects_fn(prev_pos)

    for i in range(days):
        d = start + timedelta(days=i)
        out = signals_fn(date=_noon_utc(d), rule_weights=rule_weights)
        pos, aspects = out["positions"], out["aspects"]
        trading = cal.is_trading_day(d)

        for sector in SECTOR_TICKERS:
            sig = out["sectors"].get(sector)
            if not sig:
                sector_rows.append({
                    "forecast_date": d.isoformat(), "sector": sector,
                    "direction": "neutral", "strength": 0, "signed_score": 0,
                    "has_signal": False, "reasons": [], "plain_reasons": [],
                    "analog_key": None, "is_trading_day": trading,
                })
                continue

            planets = sig["contributing_planets"]
            real = [p for p in planets
                    if pr.planet_condition(p, pos) != "neutral"
                    and not (p in pr.NODES and pr.planet_condition(p, pos) == "retrograde")]
            lead = pr.lead_condition(planets, pos)
            sector_rows.append({
                "forecast_date": d.isoformat(), "sector": sector,
                "direction": sig["direction"],
                "strength": sig["possibility_indicator"],
                "signed_score": round(sig["bullish_score"] - sig["bearish_score"], 3),
                "has_signal": bool(real) or sig["direction"] != "neutral",
                "reasons": sig["reasons"],
                "plain_reasons": pr.sector_plain_reasons(sector, planets, pos, aspects),
                "analog_key": pr.analog_key(sector, *lead[:3]) if lead else None,
                "is_trading_day": trading,
            })

        day_rows.append({
            "forecast_date": d.isoformat(), "is_trading_day": trading,
            "events": pr.sky_events(prev_pos, pos, aspects, prev_aspects),
        })
        prev_pos, prev_aspects = pos, aspects

    return sector_rows, day_rows


def mirror_sector_universe() -> int:
    """Writes rulerships.SECTOR_STOCK_UNIVERSE to the sector_universe table
    so the frontend's stock picker has a single source of truth."""
    rows = [{"sector": sector, "ticker": ticker, "name": name}
            for sector, stocks in SECTOR_STOCK_UNIVERSE.items() for ticker, name in stocks]
    db.upsert("sector_universe", rows, on_conflict="sector,ticker")
    return len(rows)


def run_forecast(rule_weights: dict = None, days: int = DEFAULT_DAYS) -> dict:
    today = date.today()
    try:
        mirror_sector_universe()
    except Exception as e:
        print(f"forecast: sector_universe mirror failed: {e}")
    if rule_weights is None:
        weights_rows = db.select("rule_weights")
        rule_weights = {w["planet"]: w["weight"] for w in weights_rows} or None

    sector_rows, day_rows = build_forecast(rule_weights, today, days)
    db.upsert("sector_forecast", sector_rows, on_conflict="forecast_date,sector")
    db.upsert("forecast_days", day_rows, on_conflict="forecast_date")

    # Consistency check: today's forecast should match what main_daily stamps
    # into predictions (same function, ~12:00 UTC vs run-time positions, so
    # tiny drift is possible but a direction flip would be worth a look).
    try:
        preds = {p["sector"]: p for p in db.select("predictions", {"date": f"eq.{today.isoformat()}"})}
        for row in sector_rows[:len(SECTOR_TICKERS)]:
            p = preds.get(row["sector"])
            if p and p["direction"] != row["direction"]:
                print(f"forecast: today's {row['sector']} forecast ({row['direction']}) differs "
                      f"from predictions row ({p['direction']}) -- intraday sky drift, check if frequent")
    except Exception as e:
        print(f"forecast: consistency check skipped: {e}")

    print(f"forecast: wrote {len(sector_rows)} sector rows over {len(day_rows)} days")
    return {"sector_rows": len(sector_rows), "days": len(day_rows)}


if __name__ == "__main__":
    run_forecast()
