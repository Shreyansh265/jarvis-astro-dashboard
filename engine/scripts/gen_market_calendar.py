"""
Writes web/market-calendar.json from trading_calendar.py so the page's
market-open badge reads the SAME holiday/early-close data as the engine
instead of a second hand-maintained list that could go stale.
Run after editing trading_calendar.py:  python engine/scripts/gen_market_calendar.py
A test (tests/test_market_calendar_json.py) fails if the committed file is out of date.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import trading_calendar as cal  # noqa: E402


def build() -> dict:
    return {
        "holidays": sorted(d.isoformat() for d in cal.NYSE_HOLIDAYS),
        "early_closes": sorted(d.isoformat() for d in cal.NYSE_EARLY_CLOSES),
        "hours_et": {"pre_open": "04:00", "open": "09:30", "close": "16:00", "early_close": "13:00", "after_close": "20:00"},
    }


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "..", "web", "market-calendar.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(), f, indent=2)
        f.write("\n")
    print("wrote", os.path.normpath(out))
