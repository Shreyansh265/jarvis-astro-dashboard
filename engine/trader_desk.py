"""
Trader's Desk: the checklist an experienced discretionary trader runs before taking
a trade, applied deterministically to daily bars. It NEVER changes the astrological
call -- it says whether price action agrees with it, where the trade is wrong, and
what the risk per share is. Pure Python (no ephemeris), so it runs in the light
post-close workflow.

Output is a checklist, not a letter grade or a probability:
  * five checks -> "aligned N of 5"
  * verdict: agree (>=4) / mixed (3) / disagree (<=2) / no-trade (R:R < 1, ATR > 6%
    of price, or too little history)
  * invalidation: the price that proves the call wrong, and why
  * stop / target / risk per share. "Shares per $X risk" is computed in the browser
    from an amount the user keeps locally; no account size is ever stored.
"""
from datetime import datetime, timezone

MIN_BARS = 60
ATR_STOP_MULT = 1.5
FALLBACK_TARGET_ATR = 3.0
MAX_ATR_PCT = 6.0
MIN_RR = 1.0
SWING_WINDOW = 3          # bars each side that must be lower/higher to count as a swing
LOOKBACK = 90
CHART_BARS = 60
BAR_CAP_TRACKED = 25


def sma(closes: list, n: int):
    return round(sum(closes[-n:]) / n, 4) if len(closes) >= n else None


def rsi(closes: list, n: int = 14):
    """Wilder's RSI."""
    if len(closes) < n + 1:
        return None
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(max(d, 0) for d in diffs[:n]) / n
    avg_loss = sum(max(-d, 0) for d in diffs[:n]) / n
    for d in diffs[n:]:
        avg_gain = (avg_gain * (n - 1) + max(d, 0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-d, 0)) / n
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 2)


def atr(bars: list, n: int = 14):
    """Wilder's average true range."""
    if len(bars) < n + 1:
        return None
    trs = [max(b["high"] - b["low"], abs(b["high"] - p["close"]), abs(b["low"] - p["close"]))
           for p, b in zip(bars, bars[1:])]
    val = sum(trs[:n]) / n
    for tr in trs[n:]:
        val = (val * (n - 1) + tr) / n
    return round(val, 4)


def swing_levels(bars: list, price: float):
    """(support, resistance): nearest confirmed swing low below price / swing high above."""
    window = bars[-LOOKBACK:]
    lows, highs = [], []
    for i in range(SWING_WINDOW, len(window) - SWING_WINDOW):
        seg = window[i - SWING_WINDOW:i + SWING_WINDOW + 1]
        if window[i]["low"] == min(b["low"] for b in seg):
            lows.append(window[i]["low"])
        if window[i]["high"] == max(b["high"] for b in seg):
            highs.append(window[i]["high"])
    below = [x for x in lows if x < price]
    above = [x for x in highs if x > price]
    return (round(max(below), 4) if below else None, round(min(above), 4) if above else None)


def _trend(close, s50, s200):
    if s50 is None:
        return "unknown"
    if s200 is not None:
        if close > s50 > s200:
            return "up"
        if close < s50 < s200:
            return "down"
    else:
        return "up" if close > s50 else "down"
    return "mixed"


def regime(spy_bars: list) -> str:
    """Market backdrop from SPY: risk-on / risk-off / mixed / unknown."""
    if not spy_bars:
        return "unknown"
    closes = [b["close"] for b in spy_bars]
    t = _trend(closes[-1], sma(closes, 50), sma(closes, 200))
    return {"up": "risk-on", "down": "risk-off", "mixed": "mixed"}.get(t, "unknown")


def build_desk(bars: list, direction: str, spy_bars: list = None) -> dict:
    """bars: oldest -> newest dicts with open/high/low/close. direction: bullish|bearish."""
    if len(bars) < MIN_BARS:
        return {"verdict": "no-trade", "reason": f"only {len(bars)} daily bars of history",
                "checks": [], "aligned": 0, "of": 0}
    closes = [b["close"] for b in bars]
    close = closes[-1]
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    r, a = rsi(closes), atr(bars)
    support, resistance = swing_levels(bars, close)
    trend = _trend(close, s50, s200)
    back = regime(spy_bars)
    bull = direction == "bullish"
    atr_pct = round(a / close * 100, 2) if a else None

    stop = round(close - ATR_STOP_MULT * a, 2) if bull else round(close + ATR_STOP_MULT * a, 2)
    risk = round(abs(close - stop), 2)
    opposing = resistance if bull else support
    target = opposing if opposing else (round(close + FALLBACK_TARGET_ATR * a, 2) if bull
                                        else round(close - FALLBACK_TARGET_ATR * a, 2))
    reward = abs(target - close)
    rr = round(reward / risk, 2) if risk else None

    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("Trend", trend == ("up" if bull else "down"),
          f"price is {'above' if close > (s50 or close) else 'below'} its 50-day average; trend reads {trend}")
    mom_ok = r is not None and ((45 <= r <= 72) if bull else (28 <= r <= 55))
    check("Momentum", mom_ok, f"RSI {r} ({'not stretched either way' if mom_ok else 'stretched or against the call'})")
    want = "risk-on" if bull else "risk-off"
    check("Market backdrop", back == want, f"SPY regime is {back}; this call wants {want}")
    room = abs((opposing or target) - close) / a if a else 0
    check("Room to move", room >= 2, f"{room:.1f} ATR to the next {'resistance' if bull else 'support'}"
          if opposing else f"no nearby {'resistance' if bull else 'support'}; open road")
    check("Not chasing", s20 is not None and a and abs(close - s20) <= 2 * a,
          f"price is {abs(close - s20) / a:.1f} ATR from its 20-day average" if s20 and a else "n/a")

    aligned = sum(1 for c in checks if c["ok"])
    if rr is not None and rr < MIN_RR:
        verdict, why = "no-trade", f"reward/risk only {rr}:1"
    elif atr_pct is not None and atr_pct > MAX_ATR_PCT:
        verdict, why = "no-trade", f"too volatile: daily range averages {atr_pct}% of price"
    else:
        verdict = "agree" if aligned >= 4 else ("mixed" if aligned == 3 else "disagree")
        why = f"price action {'supports' if verdict == 'agree' else 'is split on' if verdict == 'mixed' else 'does not support'} the call"

    if bull and support and support > stop:
        level, basis = support, "support"
    elif not bull and resistance and resistance < stop:
        level, basis = resistance, "resistance"
    else:
        level, basis = stop, "1.5 ATR stop"
    invalidation = (f"The call is wrong if it {'closes below' if bull else 'closes above'} "
                    f"${level:,.2f} ({basis}).")
    return {
        "verdict": verdict, "reason": why, "aligned": aligned, "of": len(checks), "checks": checks,
        "close": round(close, 2), "sma20": s20, "sma50": s50, "sma200": s200, "rsi14": r, "atr14": a,
        "atr_pct": atr_pct, "support": support, "resistance": resistance, "trend": trend, "regime": back,
        "stop": stop, "target": round(target, 2), "risk_per_share": risk, "reward_risk": rr,
        "invalidation": invalidation, "as_of": bars[-1]["date"][:10],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def technicals_row(ticker: str, bars: list, spy_bars: list = None) -> dict:
    closes = [b["close"] for b in bars]
    close = closes[-1]
    s50, s200 = sma(closes, 50), sma(closes, 200)
    support, resistance = swing_levels(bars, close)
    return {
        "ticker": ticker, "as_of": bars[-1]["date"][:10], "close": round(close, 4),
        "sma20": sma(closes, 20), "sma50": s50, "sma200": s200, "rsi14": rsi(closes), "atr14": atr(bars),
        "support": support, "resistance": resistance, "trend": _trend(close, s50, s200),
        "bars": [[b["date"][:10], b["open"], b["high"], b["low"], b["close"]] for b in bars[-CHART_BARS:]],
    }


def fetch_bars(ticker: str, outputsize: int = 220) -> list:
    import data_fetch
    return data_fetch.get_time_series(ticker, interval="1day", outputsize=outputsize)


def safe_desk(ticker: str, direction: str, spy_bars: list = None):
    """For freezing into a pick: never raises -- a missing desk must not block the pick."""
    try:
        bars = fetch_bars(ticker)
        if spy_bars is None:
            spy_bars = fetch_bars("SPY", 220)
        return build_desk(bars, direction, spy_bars)
    except Exception as e:
        print(f"trader_desk: could not build desk for {ticker}: {e}")
        return None


def run_trader_desk() -> int:
    """Post-close: refresh stock_technicals for tracked tickers + this week's picks."""
    import supabase_client as db
    if not db.schema_ready(2):
        return 0
    tickers = {}
    for table in ("stock_watch", "sector_watch"):
        try:
            for r in db.select(table, {"select": "ticker", "limit": "1000"}):
                if r.get("ticker"):
                    tickers[r["ticker"]] = True
        except Exception as e:
            print(f"trader_desk: could not read {table}: {e}")
    tracked = sorted(tickers)[:BAR_CAP_TRACKED]
    if len(tickers) > BAR_CAP_TRACKED:
        print(f"trader_desk: {len(tickers)} tracked tickers; capped at {BAR_CAP_TRACKED}")
    try:
        latest = db.select("weekly_picks", {"order": "week_start.desc", "limit": "8"})
    except Exception:
        latest = []
    wanted = list(dict.fromkeys(tracked + [p["ticker"] for p in latest if p.get("status") == "pending"]))
    if not wanted:
        print("trader_desk: nothing to refresh")
        return 0
    spy = fetch_bars("SPY", 220)
    written = 0
    for t in wanted:
        try:
            bars = fetch_bars(t)
            if len(bars) < 20:
                print(f"trader_desk: {t}: too little history ({len(bars)} bars)")
                continue
            db.upsert("stock_technicals", [technicals_row(t, bars, spy)], on_conflict="ticker,as_of")
            written += 1
        except Exception as e:
            print(f"trader_desk: {t} failed: {e}")
    print(f"trader_desk: refreshed {written}/{len(wanted)} ticker(s)")
    return written


if __name__ == "__main__":
    run_trader_desk()
