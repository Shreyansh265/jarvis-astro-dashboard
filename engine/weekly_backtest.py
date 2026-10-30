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
  * was_correct = sign matches the pick's direction. A move inside the
    pre-registered FLAT_BAND (|return| < 0.3%) is "no call" (NULL), not a
    hit and not a miss -- decided in advance, never tuned.
A pick only becomes 'complete' when the bar for week_end exists; otherwise it
stays pending and later runs retry. ~1 credit per distinct ticker per week.

BUG THIS FILE USED TO HAVE (found live, Oct 2026): the Twelve Data
time_series `end_date` is EXCLUSIVE for daily bars (asking Oct 19..Oct 23
returns Oct 19..Oct 22), so the week_end bar was never returned and every
pick stayed pending forever while the job still reported success. Requests
now ask for end_date = week_end + 1 day, and the run exits non-zero when a
pick is still pending after the first trading day following its week_end, so
GitHub's failure email is the alert instead of a silent green job.
"""
import sys
from datetime import date, datetime, timedelta, timezone
import supabase_client as db
import data_fetch
import trading_calendar as cal

FLAT_BAND_PCT = 0.3  # |week return| under this is "no call" (pre-registered)


def _window(bars: list, week_start: str, week_end: str) -> list:
    out = [b for b in bars if week_start <= b["date"][:10] <= week_end]
    return sorted(out, key=lambda b: b["date"])


def _ret(bars: list):
    if not bars:
        return None
    entry = bars[0]["open"]
    return round((bars[-1]["close"] - entry) / entry * 100, 2) if entry else None


def _verdict(direction: str, stock_ret):
    """True/False, or None for a flat week (no call)."""
    if stock_ret is None or abs(stock_ret) < FLAT_BAND_PCT:
        return None
    return stock_ret > 0 if direction == "bullish" else stock_ret < 0


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
        "was_correct": _verdict(pick["direction"], stock_ret),
        "status": "complete",
    }


def fetch_window(ticker: str, week_start: str, week_end: str) -> list:
    """Daily bars for the week INCLUDING week_end (end_date is exclusive)."""
    end_exclusive = (date.fromisoformat(week_end) + timedelta(days=1)).isoformat()
    return data_fetch.get_time_series(ticker, interval="1day", start_date=week_start, end_date=end_exclusive)


def is_stale(pick: dict, today: date) -> bool:
    """Still pending after the first trading day following its week_end."""
    week_end = date.fromisoformat(pick["week_end"])
    first_after = cal.next_trading_days(week_end, 1, include_start=False)[0]
    return pick["status"] == "pending" and today > first_after


def run_weekly_backtest(today=None) -> int:
    today_d = today or datetime.now(timezone.utc).date()
    today_s = today_d.isoformat()
    picks = db.select("weekly_picks", {"status": "eq.pending", "limit": "200"})
    pending = [p for p in picks if p["week_end"] <= today_s]
    if not pending:
        print("weekly_backtest: nothing to score.")
        return 0

    cache = {}

    def bars_for(ticker, ws, we):
        key = (ticker, ws, we)
        if key not in cache:
            try:
                cache[key] = fetch_window(ticker, ws, we)
            except Exception as e:
                print(f"weekly_backtest: bars failed for {ticker} {ws}..{we}: {e}")
                cache[key] = []
        return cache[key]

    scored = 0
    still_pending = []
    for p in pending:
        ws, we = p["week_start"], p["week_end"]
        update = score_pick(p, bars_for(p["ticker"], ws, we),
                            bars_for(p["etf_ticker"], ws, we) if p.get("etf_ticker") else [],
                            bars_for("SPY", ws, we))
        if not update:
            print(f"weekly_backtest: {p['ticker']} week {ws}: week_end bar not available yet; staying pending")
            still_pending.append(p)
            continue
        db.update("weekly_picks", {"id": f"eq.{p['id']}"}, update)
        scored += 1
        word = {True: "RIGHT", False: "WRONG", None: "FLAT (no call)"}[update["was_correct"]]
        print(f"weekly_backtest: {p['ticker']} ({p['direction']}) week {ws}: {update['stock_return_pct']}% -> {word}")

    stale = [p for p in still_pending if is_stale(p, today_d)]
    if stale:
        names = ", ".join(f"{p['ticker']} (week of {p['week_start']})" for p in stale)
        print(f"weekly_backtest: ERROR -- still unscored after the next trading day: {names}")
        sys.exit(1)  # fail the job so GitHub's failure notification is the alert
    return scored


if __name__ == "__main__":
    run_weekly_backtest()
