import trader_desk as td


def make_bars(closes, spread=1.0):
    return [{"date": f"2026-01-{(i % 28) + 1:02d}", "open": c - 0.2, "high": c + spread, "low": c - spread, "close": c}
            for i, c in enumerate(closes)]


def uptrend(n=220, start=50.0, step=0.3):
    return make_bars([start + i * step for i in range(n)])


def downtrend(n=220, start=150.0, step=0.3):
    return make_bars([start - i * step for i in range(n)])


def test_sma_and_rsi_known_values():
    assert td.sma([1, 2, 3, 4, 5], 5) == 3.0 and td.sma([1, 2], 5) is None
    rising = [float(i) for i in range(1, 40)]
    assert td.rsi(rising) == 100.0
    falling = [float(i) for i in range(40, 1, -1)]
    assert td.rsi(falling) == 0.0
    assert td.rsi([1.0, 2.0]) is None


def test_atr_on_constant_range():
    bars = make_bars([100.0] * 40, spread=1.0)       # high-low = 2 every bar
    assert abs(td.atr(bars) - 2.0) < 1e-6


def test_swing_levels_finds_nearest_pivots():
    closes = [100, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100, 102, 104, 106, 108, 107, 106, 107, 108]
    bars = make_bars([float(c) for c in closes] * 5, spread=0.5)
    s, r = td.swing_levels(bars, 105.0)
    assert s is not None and s < 105 and r is not None and r > 105


def test_too_little_history_is_no_trade():
    out = td.build_desk(uptrend(30), "bullish")
    assert out["verdict"] == "no-trade" and "30" in out["reason"]


def test_bullish_call_in_uptrend_has_more_checks_than_bearish_call():
    bars, spy = uptrend(), uptrend()
    bull = td.build_desk(bars, "bullish", spy)
    bear = td.build_desk(bars, "bearish", spy)
    assert bull["trend"] == "up" and bull["regime"] == "risk-on"
    assert bull["aligned"] > bear["aligned"]
    assert bear["verdict"] in ("disagree", "no-trade")


def test_bearish_call_in_downtrend_agrees_on_trend_and_backdrop():
    bars, spy = downtrend(), downtrend()
    d = td.build_desk(bars, "bearish", spy)
    names = {c["name"]: c["ok"] for c in d["checks"]}
    assert names["Trend"] and names["Market backdrop"]
    assert d["stop"] > d["close"] > d["target"]
    assert d["invalidation"].startswith("The call is wrong if it closes above")


def test_stop_and_risk_per_share_are_atr_based():
    d = td.build_desk(uptrend(), "bullish", uptrend())
    assert abs(d["risk_per_share"] - round(1.5 * d["atr14"], 2)) < 0.02
    assert d["stop"] < d["close"]


def test_volatile_stock_is_no_trade():
    bars = make_bars([100.0 + (i % 2) * 2 for i in range(220)], spread=12.0)
    assert td.build_desk(bars, "bullish", uptrend())["verdict"] == "no-trade"


def test_technicals_row_has_compact_bars_for_chart():
    row = td.technicals_row("ZZZ", uptrend())
    assert len(row["bars"]) == td.CHART_BARS and len(row["bars"][0]) == 5
    assert row["ticker"] == "ZZZ" and row["trend"] == "up"


def test_regime_unknown_without_spy():
    assert td.regime([]) == "unknown"
