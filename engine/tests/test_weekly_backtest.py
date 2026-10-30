"""
Regression tests for the weekly scoring job -- including the live bug where
Twelve Data's daily `end_date` is EXCLUSIVE, so the Friday bar was never
returned and every pick stayed pending forever while the job reported success.
"""
from datetime import date, timedelta

import pytest

import data_fetch
import supabase_client as db
import weekly_backtest as wb


def bar(d, o, c):
    return {"date": d, "open": o, "close": c, "high": max(o, c), "low": min(o, c)}


WEEK = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
STOCK = [bar("2026-10-16", 99, 100), bar("2026-10-19", 100, 101), bar("2026-10-20", 101, 102),
         bar("2026-10-21", 102, 103), bar("2026-10-22", 103, 104), bar("2026-10-23", 104, 106),
         bar("2026-10-26", 106, 107)]


def fake_series(store):
    """Mimics the REAL API: end_date is exclusive."""
    calls = []

    def get_time_series(ticker, interval="1day", outputsize=500, start_date=None, end_date=None):
        calls.append((ticker, start_date, end_date))
        if ticker not in store:
            raise RuntimeError("no data")
        return [b for b in store[ticker] if (not start_date or b["date"] >= start_date) and (not end_date or b["date"] < end_date)]

    get_time_series.calls = calls
    return get_time_series


def pick(**kw):
    base = {"id": 1, "ticker": "UNH", "etf_ticker": "XLV", "direction": "bearish",
            "week_start": "2026-10-19", "week_end": "2026-10-23", "status": "pending"}
    base.update(kw)
    return base


def test_fetch_window_requests_day_after_week_end(monkeypatch):
    fs = fake_series({"UNH": STOCK})
    monkeypatch.setattr(data_fetch, "get_time_series", fs)
    bars = wb.fetch_window("UNH", "2026-10-19", "2026-10-23")
    assert fs.calls == [("UNH", "2026-10-19", "2026-10-24")]          # exclusive end -> +1 day
    assert bars[-1]["date"] == "2026-10-23"                            # Friday bar present
    assert all(b["date"] >= "2026-10-19" for b in bars)


def test_naive_inclusive_end_would_miss_friday(monkeypatch):
    """Documents the original bug: with end_date == week_end the Friday bar is absent."""
    fs = fake_series({"UNH": STOCK})
    naive = fs("UNH", start_date="2026-10-19", end_date="2026-10-23")
    assert naive[-1]["date"] == "2026-10-22"
    assert wb.score_pick(pick(), naive, [], []) is None


def test_score_bearish_pick_that_rose_is_wrong():
    out = wb.score_pick(pick(), STOCK, [], [])
    assert out["status"] == "complete" and out["entry_price"] == 100
    assert out["stock_return_pct"] == 6.0 and out["was_correct"] is False
    assert [d["date"] for d in out["daily_closes"]] == WEEK              # prior/next week bars excluded


def test_bullish_pick_right_and_etf_spy_returns():
    etf = [bar("2026-10-19", 50, 50.5), bar("2026-10-23", 51, 52)]
    spy = [bar("2026-10-19", 400, 401), bar("2026-10-23", 404, 408)]
    out = wb.score_pick(pick(direction="bullish"), STOCK, etf, spy)
    assert out["was_correct"] is True and out["etf_return_pct"] == 4.0 and out["spy_return_pct"] == 2.0


def test_flat_week_is_no_call_not_a_miss():
    flat = [bar("2026-10-19", 100, 100.1), bar("2026-10-23", 100.1, 100.2)]
    assert wb.score_pick(pick(direction="bullish"), flat, [], [])["was_correct"] is None
    assert wb.score_pick(pick(direction="bearish"), flat, [], [])["was_correct"] is None


def test_missing_week_end_bar_stays_pending():
    assert wb.score_pick(pick(), STOCK[:-2], [], []) is None


def test_holiday_week_uses_first_real_bar():
    p = pick(week_start="2026-09-07", week_end="2026-09-11")            # Labor Day Monday
    hb = [bar("2026-09-08", 200, 201), bar("2026-09-11", 205, 210)]
    out = wb.score_pick(p, hb, [], [])
    assert out["entry_price"] == 200 and out["stock_return_pct"] == 5.0 and len(out["daily_closes"]) == 2


def test_run_scores_once_per_window_and_skips_future(monkeypatch):
    fs = fake_series({"UNH": STOCK, "XLV": [bar("2026-10-19", 50, 51), bar("2026-10-23", 51, 50)],
                      "SPY": [bar("2026-10-19", 700, 701), bar("2026-10-23", 702, 705)]})
    monkeypatch.setattr(data_fetch, "get_time_series", fs)
    rows = [pick(), pick(id=2, ticker="GS", etf_ticker="XLF", week_start="2026-10-26", week_end="2026-10-30")]
    updates = []
    monkeypatch.setattr(db, "schema_ready", lambda v=2: False)   # candidates path covered elsewhere
    monkeypatch.setattr(db, "select", lambda t, params=None: rows)
    monkeypatch.setattr(db, "update", lambda t, params, patch: updates.append((params, patch)))
    n = wb.run_weekly_backtest(date(2026, 10, 24))
    assert n == 1 and updates[0][0] == {"id": "eq.1"} and updates[0][1]["status"] == "complete"
    assert not any(c[0] == "GS" for c in fs.calls)                       # future week untouched
    assert len([c for c in fs.calls if c[0] == "SPY"]) == 1


def test_stale_detection_uses_trading_calendar():
    p = pick()
    assert not wb.is_stale(p, date(2026, 10, 26))      # Monday is the first trading day after Friday
    assert wb.is_stale(p, date(2026, 10, 27))
    assert not wb.is_stale(pick(status="complete"), date(2026, 12, 1))


def test_run_fails_loudly_when_a_pick_stays_unscored(monkeypatch):
    monkeypatch.setattr(data_fetch, "get_time_series", fake_series({"UNH": STOCK[:-2], "XLV": [], "SPY": []}))
    monkeypatch.setattr(db, "schema_ready", lambda v=2: False)
    monkeypatch.setattr(db, "select", lambda t, params=None: [pick()])
    monkeypatch.setattr(db, "update", lambda *a, **k: None)
    with pytest.raises(SystemExit) as e:
        wb.run_weekly_backtest(date(2026, 10, 28))
    assert e.value.code == 1
    # ...but not yet on the weekend right after the week ends
    wb.run_weekly_backtest(date(2026, 10, 24))
