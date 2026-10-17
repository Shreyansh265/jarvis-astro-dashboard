"""
Scores Graha's weekly picks against what actually happened, using real daily
bars (get_time_series) -- NOT market_snapshot, whose prices are pre-market
(effectively the previous close).

For each pending pick whose week has ended:
  * entry = OPEN of the first bar on/after week_start (taken from the
    returned bars, not assumed to be a Monday -- holiday weeks start later)
  * daily_closes = [{date, close}] for the week (4-day weeks happen)
  * return = close on week_end vs entry; the sector ETF and SPY get the same
    treatment so results can be judged against the base rate (a 55% hit rate
    in a rising market is just the base rate)
  * was_correct = sign matches the pick's direction (an exactly flat week is
    not a hit)
A pick only becomes 'complete' when the bar for week_end exists; otherwise it
stays pending and the Saturday catch-up run retries. ~1 credit per distinct
ticker per week (stock + ETF + SPY).
"""
from datetime import datetime, timezone
import supabase_client as db
import data_fetch


def _window(bars: list, week_start: str, week_end: str) -> list:
    out = [b for b in bars if week_start <= b["date"][:10] <= week_end]
    return sorted(out, key=lambda b: b["date"])


def _ret(bars: list):
    if not bars:
        return None
    entry = bars[0]["open"]
    return round((bars[-1]["close"] - entry) / entry * 100, 2) if entry else None


def score_pick(pick: dict, stock_bars: list, etf_bars: list, spy_bars: list):
    """Pure. Returns the update dict, or None if the week isn't complete yet."""
    ws, we = pick["week_start"], pick["week_end"]
    sb = _window(stock_bars, ws, we)
    if not sb or sb[-1]["date"][:10] != we:
        return None  # week_end bar missing -> stay pending
    stock_ret = _ret(sb)
    return {
        "entry_price": sb[0]["open"],
        "daily_closes": [{"date": b["date"][:10], "close": b["close"]} for b in sb],
        "stock_return_pct": stock_ret,
        "etf_return_pct": _ret(_window(etf_bars, ws, we)),
        "spy_return_pct": _ret(_window(spy_bars, ws, we)),
        "was_correct": (stock_ret > 0) if pick["direction"] == "bullish" else (stock_ret < 0),
        "status": "complete",
    }


def run_weekly_backtest(today=None) -> int:
    today = (today or datetime.now(timezone.utc).date()).isoformat()
    pending = [p for p in db.select("weekly_picks", {"status": "eq.pending", "limit": "200"})
               if p["week_end"] <= today]
    if not pending:
        print("weekly_backtest: nothing to score.")
        return 0

    cache = {}

    def bars_for(ticker, ws, we):
        key = (ticker, ws, we)
        if key not in cache:
            try:
                cache[key] = data_fetch.get_time_series(ticker, interval="1day", start_date=ws, end_date=we)
            except Exception as e:
                print(f"weekly_backtest: bars failed for {ticker} {ws}..{we}: {e}")
                cache[key] = []
        return cache[key]

    scored = 0
    for p in pending:
        ws, we = p["week_start"], p["week_end"]
        update = score_pick(p, bars_for(p["ticker"], ws, we),
                            bars_for(p["etf_ticker"], ws, we) if p.get("etf_ticker") else [],
                            bars_for("SPY", ws, we))
        if not update:
            print(f"weekly_backtest: {p['ticker']} week {ws}: week_end bar not available yet; staying pending")
            continue
        db.update("weekly_picks", {"id": f"eq.{p['id']}"}, update)
        scored += 1
        print(f"weekly_backtest: {p['ticker']} ({p['direction']}) week {ws}: "
              f"{update['stock_return_pct']}% -> {'RIGHT' if update['was_correct'] else 'WRONG'}")
    return scored


if __name__ == "__main__":
    run_weekly_backtest()
