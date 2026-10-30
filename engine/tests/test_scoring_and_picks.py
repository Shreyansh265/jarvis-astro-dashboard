from datetime import date, timedelta

import review_common
import supabase_client as db
import trading_calendar as cal
import weekly_picks as wp


# ---------- prediction scoring: neutral/flat are "no call" ----------
def pred(direction, price=100.0):
    return {"direction": direction, "price_at_prediction": price}


def test_neutral_prediction_is_never_marked_wrong():
    # live bug: 75 of 75 neutral predictions were scored wrong
    assert review_common.score_prediction(pred("neutral"), 103.0)["was_correct"] is None
    assert review_common.score_prediction(pred("neutral"), 97.0)["was_correct"] is None


def test_flat_move_is_no_call():
    out = review_common.score_prediction(pred("bullish"), 100.0)
    assert out["outcome_direction"] == "flat" and out["was_correct"] is None


def test_directional_scoring_unchanged():
    assert review_common.score_prediction(pred("bullish"), 101.0)["was_correct"] is True
    assert review_common.score_prediction(pred("bullish"), 99.0)["was_correct"] is False
    assert review_common.score_prediction(pred("bearish"), 99.0)["was_correct"] is True
    assert review_common.score_prediction({"direction": "bullish", "price_at_prediction": None}, 5) is None


# ---------- trading calendar ----------
def test_calendar_holidays_and_short_weeks():
    assert cal.is_trading_day(date(2026, 10, 16)) and not cal.is_trading_day(date(2026, 10, 17))
    assert not cal.is_trading_day(date(2026, 11, 26))                       # Thanksgiving
    assert cal.week_bounds(date(2026, 9, 7)) == (date(2026, 9, 8), date(2026, 9, 11))   # Labor Day
    assert cal.next_monday(date(2026, 10, 18)) == date(2026, 10, 19)
    assert [d.isoformat() for d in cal.next_trading_days(date(2026, 10, 16), 3)] == ["2026-10-16", "2026-10-19", "2026-10-20"]


# ---------- weekly pick selection ----------
WEEK = [date(2026, 10, 19) + timedelta(days=i) for i in range(5)]


def fr(sector, d, direction, strength, has=True):
    return {"forecast_date": d.isoformat(), "sector": sector, "direction": direction, "strength": strength,
            "has_signal": has, "plain_reasons": [f"{sector} reason"]}


def test_selection_thresholds_and_direction_consistency():
    rows = []
    for d in WEEK:
        rows += [fr("Gold", d, "bullish", 72), fr("Energy", d, "bearish", 70), fr("Technology", d, "bullish", 60),
                 fr("Healthcare", d, "bullish", 80), fr("Silver", d, "bullish", 95)]
    rows += [fr("Utilities", WEEK[0], "bullish", 90), fr("Utilities", WEEK[1], "bullish", 90)]   # only 2 days
    for d in WEEK[:2]: rows.append(fr("Financials", d, "bullish", 75))
    for d in WEEK[2:]: rows.append(fr("Financials", d, "bearish", 75))                          # 2 up / 3 down
    got = [(p["sector"], p["direction"]) for p in wp.select_picks(rows, WEEK)]
    assert got == [("Healthcare", "bullish"), ("Financials", "bearish"), ("Gold", "bullish"), ("Energy", "bearish")]


def test_max_five_distinct_sectors_and_quiet_week():
    many = [fr(s, d, "bullish", 70 + len(s)) for s in
            ["Gold", "Energy", "Healthcare", "Financials", "Industrials", "Materials_Mining", "Consumer_Staples"] for d in WEEK]
    picks = wp.select_picks(many, WEEK)
    assert len(picks) == 5 and len({p["sector"] for p in picks}) == 5
    assert wp.select_picks([fr("Gold", d, "bullish", 40) for d in WEEK], WEEK) == []


def test_picks_are_frozen_and_weekend_only(monkeypatch):
    store = {"weekly_picks": [], "sector_forecast": [fr("Healthcare", d, "bearish", 80) for d in WEEK]}
    monkeypatch.setattr(db, "select", lambda t, params=None: [r for r in store[t] if all(
        not str(v).startswith("eq.") or str(r.get(k)) == v[3:] for k, v in (params or {}).items() if k != "limit")])
    monkeypatch.setattr(db, "insert", lambda t, rows: store[t].extend(rows) or rows)
    made = wp.create_weekly_picks(date(2026, 10, 17))                  # Saturday
    assert len(made) == 1 and made[0]["week_start"] == "2026-10-19" and made[0]["ticker"] == "UNH"
    assert wp.create_weekly_picks(date(2026, 10, 17)) == []             # already frozen
    assert wp.create_weekly_picks(date(2026, 10, 21)) == []             # mid-week: refuse (hindsight)
