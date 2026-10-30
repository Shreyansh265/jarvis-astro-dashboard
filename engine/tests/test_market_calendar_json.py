import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_market_calendar  # noqa: E402


def test_committed_market_calendar_matches_engine_calendar():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "web", "market-calendar.json")
    with open(path, encoding="utf-8") as f:
        committed = json.load(f)
    assert committed == gen_market_calendar.build(), (
        "web/market-calendar.json is stale -- run: python engine/scripts/gen_market_calendar.py")
