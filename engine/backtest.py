"""
Backtests each planet's rule set against REAL historical sector ETF prices.
This is what the user explicitly asked for: don't throw out signals without
first proving (or disproving) them against history.

Method: for each trading day in the lookback window, reconstruct what the
planetary position/tone was on that day, compute what the engine WOULD have
signaled, then check the sector ETF's actual forward return over the next
N trading days. Hit rate = how often the predicted direction matched the
actual direction. This produces the "possibility indicator" calibration
data that signals.py and weekly_review.py rely on.
"""
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from ephemeris import get_positions
from rulerships import PLANET_SECTOR_RULES, EXALTATION, DEBILITATION
from signals import _planet_base_tone
import data_fetch


def backtest_planet_sector(planet: str, sector: str, ticker: str,
                            lookback_days: int = 365, forward_window: int = 5) -> dict:
    """
    Returns hit-rate stats for one planet->sector rule over the lookback window.
    forward_window = how many trading days ahead we check the outcome (5 = ~1 week).
    """
    bars = data_fetch.get_time_series(ticker, interval="1day", outputsize=lookback_days + forward_window + 10)
    if len(bars) < forward_window + 10:
        return {"planet": planet, "sector": sector, "ticker": ticker,
                "error": "insufficient historical data"}

    hits, misses, total_checked = 0, 0, 0
    examples = []

    for i in range(len(bars) - forward_window):
        bar_date = datetime.strptime(bars[i]["date"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        pos = get_positions(bar_date)
        if planet not in pos:
            continue
        tone, strength, reason = _planet_base_tone(planet, pos)
        if tone not in ("bullish", "bearish"):
            continue  # only score days with a clear classical signal

        start_price = bars[i]["close"]
        end_price = bars[i + forward_window]["close"]
        actual_direction = "bullish" if end_price > start_price else "bearish"
        actual_pct = round((end_price - start_price) / start_price * 100, 2)

        total_checked += 1
        correct = (tone == actual_direction)
        if correct:
            hits += 1
        else:
            misses += 1
        if len(examples) < 5:
            examples.append({
                "date": bars[i]["date"][:10], "predicted": tone,
                "actual": actual_direction, "actual_pct_move": actual_pct, "correct": correct,
            })

    hit_rate = round(hits / total_checked, 3) if total_checked else None
    return {
        "planet": planet, "sector": sector, "ticker": ticker,
        "days_checked": total_checked, "hits": hits, "misses": misses,
        "hit_rate": hit_rate, "sample_events": examples,
    }


def backtest_all_rules(lookback_days: int = 365, forward_window: int = 5) -> list:
    from rulerships import SECTOR_TICKERS
    results = []
    for planet, rule in PLANET_SECTOR_RULES.items():
        for sector in rule["sectors"]:
            ticker = SECTOR_TICKERS.get(sector)
            if not ticker:
                continue
            try:
                res = backtest_planet_sector(planet, sector, ticker, lookback_days, forward_window)
                results.append(res)
                print(f"{planet:8s} -> {sector:24s} hit_rate={res.get('hit_rate')}  "
                      f"({res.get('days_checked')} days checked)")
            except Exception as e:
                print(f"  skipped {planet}->{sector}: {e}")
    return results


def suggest_updated_weights(backtest_results: list) -> dict:
    """
    Aggregates hit-rate across all sectors a planet governs into one weight
    per planet (bounded 0.15-0.9 so no rule ever fully dominates or is fully zeroed).
    """
    by_planet = defaultdict(list)
    for r in backtest_results:
        if r.get("hit_rate") is not None:
            by_planet[r["planet"]].append(r["hit_rate"])
    weights = {}
    for planet, rates in by_planet.items():
        avg = sum(rates) / len(rates)
        weights[planet] = round(min(0.9, max(0.15, avg)), 3)
    return weights


if __name__ == "__main__":
    results = backtest_all_rules(lookback_days=250, forward_window=5)
    print("\nSuggested starting weights based on 1yr backtest:")
    print(suggest_updated_weights(results))
