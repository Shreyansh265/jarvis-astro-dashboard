from datetime import date

import evidence_run as ev


def test_wilson_basic():
    lo, hi = ev.wilson(50, 100)
    assert lo < 0.5 < hi and 0.40 < lo < 0.42 and 0.58 < hi < 0.60
    assert ev.wilson(0, 0) == (None, None)
    lo, hi = ev.wilson(10, 10)
    assert hi == 1.0 or hi > 0.99


def test_week_groups_handles_holiday_weeks():
    # Mon Jan 18 2021 was MLK day: that week has only Tue-Fri.
    ref = [date(2021, 1, 15), date(2021, 1, 19), date(2021, 1, 20), date(2021, 1, 21), date(2021, 1, 22),
           date(2021, 1, 25)]
    g = ev.week_groups(ref)
    assert [len(w) for w in g] == [1, 4, 1]
    assert g[1][0] == date(2021, 1, 19)


def test_week_return_and_verdict_flat_band():
    bars = {date(2021, 1, 19): {"open": 100.0, "close": 100.0}, date(2021, 1, 22): {"open": 1, "close": 103.0}}
    days = [date(2021, 1, 19), date(2021, 1, 22)]
    assert ev.week_return(bars, days) == 3.0
    assert ev.verdict("bullish", 3.0) is True and ev.verdict("bearish", 3.0) is False
    assert ev.verdict("bullish", 0.1) is None and ev.verdict("bullish", None) is None
    assert ev.week_return({}, days) is None


def test_summarize_excludes_flat_and_reports_mix():
    recs = [{"direction": "bullish", "ret": 2, "correct": True}, {"direction": "bearish", "ret": 2, "correct": False},
            {"direction": "bearish", "ret": 0.1, "correct": None}]
    s = ev.summarize(recs)
    assert s["scored"] == 2 and s["hits"] == 1 and s["accuracy"] == 0.5 and s["flat"] == 1
    assert s["bullish_share"] == round(1 / 3, 3)
    assert ev.summarize([])["accuracy"] is None


def test_baselines_complement():
    b = ev.baselines([1.0, -1.0, 2.0, 0.1, None])
    assert b["weeks"] == 3 and b["always_up"] == round(2 / 3, 4) and b["always_down"] == round(1 / 3, 4)
