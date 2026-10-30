from datetime import date

import company_chart as cc
import pick_of_week as pw
import stock_outlook as so
import weekly_picks as wp

DAYS = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]
UNIVERSE = {
    "Technology": [("AAA", "Alpha Corp"), ("BBB", "Beta Inc"), ("CCC", "Gamma Co"), ("QQQX", "Tech Fund · ETF")],
    "Energy": [("EEE", "Energy One"), ("FFF", "Energy Two")],
}
QUAL = [{"sector": "Technology", "direction": "bullish", "strength": 80.0, "agreeing": 4, "total": 5,
         "plain_reasons": ["▲ Jupiter is strong"]}]


def _signed(val):
    return {("Technology", d.isoformat()): val for d in DAYS}


def _stub_week(monkeypatch, scores):
    """week_score(first_trade_date, days) -> fixed score by IPO year."""
    def fake(first_trade, days):
        return {"score": scores[first_trade.year], "days": [
            {"date": d.isoformat(), "score": scores[first_trade.year],
             "aspects": [{"transit": "Jupiter", "natal": "Sun", "aspect": "trine", "orb": 1.0,
                          "nature": "benefic", "points": 0.8 * (1 if scores[first_trade.year] > 0 else -1)}]}
            for d in days], "rules_version": cc.RULES_VERSION}
    monkeypatch.setattr(cc, "week_score", fake)


def _charts():
    return {"AAA": {"ticker": "AAA", "first_trade_date": "2000-01-03", "confidence": "known"},
            "BBB": {"ticker": "BBB", "first_trade_date": "2001-01-03", "confidence": "known"},
            "CCC": {"ticker": "CCC", "first_trade_date": "2002-01-02", "confidence": "verify"}}


def test_etfs_are_never_candidates(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    cands = pw.week_candidates(QUAL, UNIVERSE, _charts(), _signed(80), DAYS)
    assert "QQQX" not in {c["ticker"] for c in cands}


def test_verify_chart_stocks_are_not_pick_eligible(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    cands = pw.week_candidates(QUAL, UNIVERSE, _charts(), _signed(80), DAYS)
    assert "CCC" not in {c["ticker"] for c in cands}


def test_best_composite_wins_and_ranks_assigned(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    cands = pw.week_candidates(QUAL, UNIVERSE, _charts(), _signed(80), DAYS)
    assert [c["ticker"] for c in cands] == ["AAA", "BBB"]
    assert [c["rank"] for c in cands] == [1, 2]
    assert cands[0]["chart_basis"] == "company"
    assert cands[0]["composite"] == round(0.6 * 80 + 0.4 * 30, 1)


def test_strongly_contradicting_company_chart_is_ineligible(monkeypatch):
    _stub_week(monkeypatch, {2000: -60, 2001: 10})
    cands = pw.week_candidates(QUAL, UNIVERSE, _charts(), _signed(80), DAYS)
    assert [c["ticker"] for c in cands] == ["BBB"]


def test_sector_only_stock_gets_penalty_and_label(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    cands = pw.week_candidates(QUAL, UNIVERSE, {}, _signed(80), DAYS)   # no charts at all
    assert {c["chart_basis"] for c in cands} == {"sector"}
    assert cands[0]["composite"] == round(80 * cc.SECTOR_ONLY_FACTOR, 1)
    assert [c["ticker"] for c in cands] == ["AAA", "BBB", "CCC"]       # universe order breaks ties


def test_no_qualifying_sector_means_no_candidates(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    assert pw.week_candidates([], UNIVERSE, _charts(), _signed(80), DAYS) == []


def test_random_control_is_same_sector_deterministic_and_not_the_pick(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    cands = pw.week_candidates(QUAL, UNIVERSE, _charts(), _signed(80), DAYS)
    a = pw.random_control(cands[0], UNIVERSE, _charts(), _signed(80), DAYS, "2026-11-02")
    b = pw.random_control(cands[0], UNIVERSE, _charts(), _signed(80), DAYS, "2026-11-02")
    assert a == b and a["ticker"] != "AAA" and a["sector"] == "Technology" and a["direction"] == "bullish"
    assert a["ticker"] != "QQQX"


def test_factors_carry_the_whole_why(monkeypatch):
    _stub_week(monkeypatch, {2000: 30, 2001: 10})
    pick = pw.week_candidates(QUAL, UNIVERSE, _charts(), _signed(80), DAYS)[0]
    f = pw.build_factors(pick, ["▲ Jupiter is strong"])
    assert f["sector"]["plain_reasons"] == ["▲ Jupiter is strong"]
    assert f["company"]["first_trade_date"] == "2000-01-03" and len(f["company"]["days"]) == 5
    assert f["composite"]["weights"]["sector"] == 0.6 and f["counter_case"]
    assert f["rules_version"] == cc.RULES_VERSION


def test_record_snapshot_counts_flat_separately():
    rows = [{"status": "complete", "was_correct": True}, {"status": "complete", "was_correct": False},
            {"status": "complete", "was_correct": None}, {"status": "pending", "was_correct": None}]
    assert pw.record_snapshot(rows) == {"n": 3, "right": 1, "wrong": 1, "flat": 1}


def test_sector_candidates_one_entry_per_sector_and_radar_still_capped():
    rows = []
    for d in DAYS:
        for sector in ("Technology", "Energy", "Healthcare", "Financials", "Utilities", "Gold", "Materials_Mining"):
            rows.append({"forecast_date": d.isoformat(), "sector": sector, "direction": "bullish",
                         "strength": 70, "has_signal": True, "plain_reasons": []})
    assert len(wp.sector_candidates(rows, DAYS)) >= 6
    assert len(wp.select_picks(rows, DAYS)) == wp.MAX_PICKS


def test_stock_rows_label_sector_only_without_confirmed_chart():
    signed = {("Technology", d.isoformat()): 70.0 for d in DAYS}
    plain = {("Technology", d.isoformat()): ["▲ x"] for d in DAYS}
    rows = so.build_stock_rows("ZZZ", "Zed", "Technology", None, DAYS, signed, plain)
    assert {r["chart_basis"] for r in rows} == {"sector"} and all(r["direction"] == "bullish" for r in rows)
    verify = {"ticker": "ZZZ", "first_trade_date": "2001-01-03", "confidence": "verify"}
    rows = so.build_stock_rows("ZZZ", "Zed", "Technology", verify, DAYS, signed, plain)
    assert {r["chart_basis"] for r in rows} == {"sector"}
    assert rows[0]["factors"]["chart"]["confidence"] == "verify"


def test_score_candidate_matches_pick_rules():
    import weekly_backtest as wb
    bars = [{"date": "2026-11-02", "open": 100, "close": 101}, {"date": "2026-11-06", "open": 101, "close": 104}]
    cand = {"week_start": "2026-11-02", "week_end": "2026-11-06", "direction": "bullish"}
    out = wb.score_candidate(cand, bars)
    assert out == {"entry_price": 100, "stock_return_pct": 4.0, "was_correct": True, "status": "complete"}
    assert wb.score_candidate(cand, bars[:1]) is None          # week_end bar missing -> pending
    flat = [{"date": "2026-11-02", "open": 100, "close": 100.1}, {"date": "2026-11-06", "open": 100, "close": 100.1}]
    assert wb.score_candidate(cand, flat)["was_correct"] is None  # inside the flat band
