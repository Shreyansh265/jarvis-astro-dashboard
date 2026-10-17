"""
Weekly refresh of the "it happened before" examples shown on the Dashboard's
"Sectors Poised to Rise" section. Run Sunday from main_weekly.py (NOT inside
the tight pre-market daily job): an analog only changes when a planet's
condition changes, so each (sector, planet, condition, sign) is cached in
analog_cache and reused.

Honesty rules (the UI repeats them):
  * One planet, one past occurrence is an ILLUSTRATION, not evidence. It is
    shown next to the rule's aggregate record (hit rate over independent
    weeks) when one exists, and labelled "most recent occurrence".
  * The example is shown even if it went the wrong way -- never filtered
    to winners.
  * A ticker that didn't exist then (XLRE 2015, XLC 2018) or any price-data
    failure yields unverifiable_reason, never a fallback to another ticker.
  * Lunar-node "retrograde" is permanent (always true by convention), so it
    is not an event and gets no analog.
"""
from datetime import datetime, timedelta, timezone
import supabase_client as db
import historical_analog
import backtest
from rulerships import SECTOR_TICKERS
import trading_calendar as cal

CACHE_FRESH_DAYS = 6
NODES = ("Rahu", "Ketu")


def _parse_key(key: str):
    sector, planet, condition, sign = key.split("|")
    return sector, planet, condition, sign


def keys_needed(forecast_rows: list, today, days: int = 5) -> list:
    """Distinct analog keys behind bullish forecast rows in the next `days`
    trading days (what the 'poised to rise' section can show)."""
    window = {d.isoformat() for d in cal.next_trading_days(today, days)}
    keys = []
    for r in forecast_rows:
        if r["forecast_date"] in window and r.get("has_signal") and r["direction"] == "bullish" and r.get("analog_key"):
            _, planet, condition, _ = _parse_key(r["analog_key"])
            if condition == "retrograde" and planet in NODES:
                continue
            if r["analog_key"] not in keys:
                keys.append(r["analog_key"])
    return keys


def build_payload(key: str, today_dt: datetime) -> dict:
    sector, planet, condition, sign = _parse_key(key)
    ticker = SECTOR_TICKERS[sector]
    payload = historical_analog.analog_for(
        sector, ticker, planet, condition, sign, condition == "retrograde", today_dt)
    payload.update({"rule_hit_rate": None, "rule_n": None, "rule_days": None})
    # Directional aggregate only exists for exalted/debilitated (the backtest
    # scores clear bullish/bearish tones, not retrograde volatility).
    if condition in ("exalted", "debilitated"):
        try:
            res = backtest.backtest_planet_sector_multi_horizon(planet, sector, ticker)
            h = res.get("horizons", {}).get(5)
            if h:
                payload.update({"rule_hit_rate": h["hit_rate"], "rule_n": h["sample_size"],
                                "rule_days": h["days_checked"]})
        except Exception as e:
            print(f"analogs: rule aggregate failed for {key}: {e}")
    return payload


def refresh_analogs(today=None) -> int:
    today = today or datetime.now(timezone.utc).date()
    rows = db.select("sector_forecast", {"forecast_date": f"gte.{today.isoformat()}", "limit": "1000"})
    keys = keys_needed(rows, today)
    cached = {c["key"]: c for c in db.select("analog_cache", {"limit": "500"})}
    fresh_after = (datetime.now(timezone.utc) - timedelta(days=CACHE_FRESH_DAYS)).isoformat()
    done = 0
    for key in keys:
        c = cached.get(key)
        if c and c["computed_at"] >= fresh_after:
            continue
        try:
            payload = build_payload(key, datetime.now(timezone.utc))
            db.upsert("analog_cache", {"key": key, "payload": payload,
                                       "computed_at": datetime.now(timezone.utc).isoformat()}, on_conflict="key")
            done += 1
            print(f"analogs: cached {key}")
        except Exception as e:
            print(f"analogs: failed for {key}: {e}")
    return done


if __name__ == "__main__":
    print(refresh_analogs())
