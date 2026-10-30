from datetime import date

import pytest
import swisseph as swe

import company_chart as cc

REAL_EPHEMERIS = hasattr(swe, "version")   # the conftest stand-in has no .version


def test_open_time_changes_in_1985():
    # 9:30 ET on a December day (EST, UTC-5) -> 14:30 UTC; 10:00 ET before the change.
    assert cc.natal_moment_utc(date(1980, 12, 12)).hour == 15
    assert cc.natal_moment_utc(date(1980, 12, 12)).minute == 0
    assert (cc.natal_moment_utc(date(1990, 12, 12)).hour,
            cc.natal_moment_utc(date(1990, 12, 12)).minute) == (14, 30)


def test_dst_handled_for_summer_dates():
    # 9:30 EDT (UTC-4) -> 13:30 UTC
    m = cc.natal_moment_utc(date(2010, 6, 29))
    assert (m.hour, m.minute) == (13, 30)


def test_csv_is_valid_and_has_no_weekend_dates():
    rows = cc.load_company_rows()
    assert len(rows) >= 60
    assert all(r["confidence"] in ("known", "verify") for r in rows)


def test_composite_sector_only_gets_penalty_and_label():
    out = cc.composite(70, None, usable_company=False)
    assert out["chart_basis"] == "sector" and out["score"] == 63.0 and out["direction"] == "bullish"


def test_composite_blends_when_company_agrees():
    out = cc.composite(70, 30, usable_company=True)
    assert out["score"] == round(0.6 * 70 + 0.4 * 30, 1)
    assert out["chart_basis"] == "company" and out["eligible"]


def test_composite_strong_contradiction_is_ineligible():
    out = cc.composite(70, -60, usable_company=True)
    assert out["eligible"] is False


def test_composite_mild_contradiction_still_eligible():
    out = cc.composite(70, -20, usable_company=True)
    assert out["eligible"] and out["direction"] == "bullish"


def test_squash_bounds():
    assert -100 < cc.squash(-2) < 0 < cc.squash(2) < 100
    assert cc.squash(0) == 0
    assert cc.squash(50) == 100.0   # saturates rather than overflowing


@pytest.mark.skipif(not REAL_EPHEMERIS, reason="needs real pyswisseph (runs on Actions)")
def test_apple_natal_sun_is_sagittarius_20():
    natal = cc.natal_positions(date(1980, 12, 12))
    assert 258 <= natal["Sun"]["longitude"] <= 262   # tropical Sun ~260 deg on 1980-12-12
