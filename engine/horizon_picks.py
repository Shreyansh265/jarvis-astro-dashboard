"""
Weekly/monthly/yearly sector+stock picks, backtested per horizon via
backtest.backtest_planet_sector_multi_horizon (one fetch per ticker,
evaluated at all three horizons -- not three separate fetches). Ranks
sectors per horizon by combining REAL historical hit-rate at that horizon
with TODAY's live planetary tone/strength, dedupes to the best-scoring
planet per sector, takes the top few per horizon, and attaches 2-3 stock
picks from the curated watchlist.

Cadence: weekly and monthly horizons run weekly (piggybacking on the
Sunday weekly.yml schedule, via run_horizon_picks(include_yearly=False)
most weeks). The yearly horizon runs MONTHLY, not weekly -- Jupiter/
Saturn/the lunar nodes barely change tone week to week, so weekly yearly-
recomputation would just write near-identical rows and waste API credits;
main_weekly.py decides whether to pass include_yearly=True based on
whether today is the first Sunday-or-later of the month that hasn't run
yet (see main_weekly.py). period_start is quantized per horizon (Monday-
of-week / 1st-of-month / Jan-1) so re-runs upsert cleanly via the
unique(horizon, sector, period_start) constraint instead of creating
near-duplicate rows.
"""
from datetime import date, datetime, timezone, timedelta
import supabase_client as db
from ephemeris import get_positions
from signals import _planet_base_tone
from rulerships import PLANET_SECTOR_RULES, SECTOR_TICKERS, SECTOR_TOP_STOCKS
import backtest
import data_fetch

# How many days must elapse before a horizon's pick is old enough to
# honestly check against realized outcome -- matches each horizon's own
# forward_window (a "weekly" pick needs a week to actually play out).
REVIEW_AFTER_DAYS = {"weekly": 7, "monthly": 30, "yearly": 365}

HORIZON_FORWARD_WINDOWS = {"weekly": 5, "monthly": 21, "yearly": 252}
PICKS_PER_HORIZON = 3
MIN_SAMPLE_SIZE = 2  # hard-skip only below this -- otherwise keep and label via sample_quality


def _period_start(horizon: str, today: date) -> date:
    if horizon == "weekly":
        return today - timedelta(days=today.weekday())  # Monday of this ISO week
    if horizon == "monthly":
        return today.replace(day=1)
    return today.replace(month=1, day=1)  # yearly


def run_horizon_picks(include_yearly: bool = False) -> dict:
    today = date.today()
    now_positions = get_positions(datetime.now(timezone.utc))

    horizons_to_run = ["weekly", "monthly"] + (["yearly"] if include_yearly else [])
    candidates = {h: [] for h in horizons_to_run}

    for planet, rule in PLANET_SECTOR_RULES.items():
        tone, strength, reason = _planet_base_tone(planet, now_positions)
        if tone not in ("bullish", "bearish"):
            continue  # no live signal today for this planet -- nothing to rank

        for sector in rule["sectors"]:
            ticker = SECTOR_TICKERS.get(sector)
            if not ticker:
                continue
            try:
                result = backtest.backtest_planet_sector_multi_horizon(
                    planet, sector, ticker,
                    forward_windows=tuple(HORIZON_FORWARD_WINDOWS[h] for h in horizons_to_run),
                )
            except Exception as e:
                print(f"horizon_picks: backtest failed for {planet}->{sector}: {e}")
                continue

            for horizon in horizons_to_run:
                fw = HORIZON_FORWARD_WINDOWS[horizon]
                h_result = result.get("horizons", {}).get(fw)
                if not h_result or h_result["hit_rate"] is None or h_result["sample_size"] < MIN_SAMPLE_SIZE:
                    continue  # truly no meaningful backtest -- hard skip only here
                candidates[horizon].append({
                    "sector": sector, "planet": planet, "tone": tone, "strength": strength,
                    "reason": reason, "hit_rate": h_result["hit_rate"],
                    "sample_size": h_result["sample_size"], "sample_quality": h_result["sample_quality"],
                    "score": h_result["hit_rate"] * strength,
                })

    picks_logged = {h: 0 for h in horizons_to_run}
    for horizon, cands in candidates.items():
        best_per_sector = {}
        for c in cands:
            if c["sector"] not in best_per_sector or c["score"] > best_per_sector[c["sector"]]["score"]:
                best_per_sector[c["sector"]] = c
        ranked = sorted(best_per_sector.values(), key=lambda c: -c["score"])[:PICKS_PER_HORIZON]

        period_start = _period_start(horizon, today)
        for rank, c in enumerate(ranked, start=1):
            tickers = SECTOR_TOP_STOCKS.get(c["sector"], [])[:3]
            db.upsert("horizon_picks", {
                "horizon": horizon, "period_start": period_start.isoformat(),
                "sector": c["sector"], "planet": c["planet"],
                "hit_rate": c["hit_rate"], "sample_size": c["sample_size"],
                "sample_quality": c["sample_quality"],
                "today_tone": c["tone"], "today_strength": c["strength"],
                "rank": rank, "tickers": tickers, "reasons": [c["reason"]],
            }, on_conflict="horizon,sector,period_start")
            picks_logged[horizon] += 1

    return picks_logged


def review_horizon_picks() -> dict:
    """
    Checks realized outcome for picks old enough for their horizon to have
    actually elapsed (reviewed_at is null AND period_start + REVIEW_AFTER_DAYS
    has passed), via a real price lookup -- reuses SECTOR_TICKERS the same
    way the pick itself did.
    """
    today = date.today()
    reviewed_counts = {"weekly": 0, "monthly": 0, "yearly": 0}

    for horizon, review_after in REVIEW_AFTER_DAYS.items():
        cutoff = (today - timedelta(days=review_after)).isoformat()
        pending = db.select("horizon_picks", {
            "horizon": f"eq.{horizon}", "reviewed_at": "is.null",
            "period_start": f"lte.{cutoff}",
        })
        for pick in pending:
            ticker = SECTOR_TICKERS.get(pick["sector"])
            if not ticker:
                continue
            try:
                bars = data_fetch.get_time_series(ticker, interval="1day",
                                                    start_date=pick["period_start"],
                                                    end_date=today.isoformat())
            except Exception as e:
                print(f"horizon_picks review: could not verify {pick['sector']} ({horizon}): {e}")
                continue
            if len(bars) < 2:
                continue
            start_price, end_price = bars[0]["close"], bars[-1]["close"]
            actual_pct = round((end_price - start_price) / start_price * 100, 2)
            actual_direction = "bullish" if actual_pct > 0 else "bearish"
            was_correct = (actual_direction == pick["today_tone"])
            db.update("horizon_picks", {"id": f"eq.{pick['id']}"}, {
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "was_correct": was_correct, "outcome_pct_change": actual_pct,
            })
            reviewed_counts[horizon] += 1

    return reviewed_counts


if __name__ == "__main__":
    result = run_horizon_picks(include_yearly=True)
    print(result)
    print(review_horizon_picks())
