"""
Runs once per day via GitHub Actions (see .github/workflows/daily.yml):
  1. Review yesterday's (or any still-unreviewed) predictions against
     today's fresh prices, and let that nudge rule_weights BEFORE today's
     signals are generated -- otherwise "don't repeat the mistake" would
     always run a day behind.
  2. Re-read rule_weights (now post-adjustment) and compute today's
     planetary positions + sector signals.
  3. Log the planetary snapshot and every prediction to Supabase, including
     a long-term explanation (with a real historical planetary analog when
     one can be found -- see historical_analog.py) for each non-neutral sector.
  4. Suggest individual stocks within strongly-signaled sectors (Astro
     Stocks tab) and scan the curated watchlist for gainers/losers.
  5. Generate today's plain-language brief.
  6. Run the paper trading bot against today's signals.
"""
from datetime import date, datetime, timezone
import json
import signals as sig_mod
import supabase_client as db
import data_fetch
from rulerships import SECTOR_TICKERS
import daily_review
import stock_picks
import market_watch
import eli5
import paper_trader
import historical_analog


def main():
    review_result = daily_review.run_daily_review()
    if review_result["reviewed"]:
        print(f"Daily review: scored {review_result['reviewed']} prior prediction(s).")
        for lesson in review_result["lessons"]:
            print(" -", lesson["reason_it_missed"])

    # Read rule_weights AFTER daily_review's adjustments above, not a copy
    # from before it ran -- otherwise today's signals would use yesterday's
    # weights and the learning loop gets a spurious one-day lag.
    weights_rows = db.select("rule_weights")
    rule_weights = {w["planet"]: w["weight"] for w in weights_rows}
    now = datetime.now(timezone.utc)
    out = sig_mod.generate_signals(date=now, rule_weights=rule_weights) if rule_weights else sig_mod.generate_signals(date=now)

    today = date.today().isoformat()

    try:
        db.upsert("planetary_log", {
            "date": today,
            "positions": out["positions"],
            "aspects": out["aspects"],
        }, on_conflict="date")
    except Exception as e:
        print(f"planetary_log upsert warning: {e}")

    predictions_logged = 0
    for sector, sig in out["sectors"].items():
        ticker = SECTOR_TICKERS.get(sector)
        if not ticker:
            continue
        try:
            quote = data_fetch.get_quote(ticker)
            price = quote["price"]
        except Exception as e:
            print(f"price fetch failed for {ticker}: {e}")
            price = None

        try:
            long_term_note = historical_analog.build_long_term_note(
                sector, ticker, sig["direction"], sig["reasons"],
                sig["contributing_planets"], out["positions"], now,
            )
        except Exception as e:
            print(f"historical_analog failed for {sector}: {e}")
            long_term_note = None

        db.upsert("predictions", {
            "date": today, "sector": sector, "ticker": ticker,
            "direction": sig["direction"],
            "possibility_indicator": sig["possibility_indicator"],
            "reasons": sig["reasons"], "contributing_planets": sig["contributing_planets"],
            "price_at_prediction": price, "long_term_note": long_term_note,
        }, on_conflict="date,sector")
        predictions_logged += 1

    print(f"Logged {predictions_logged} predictions for {today}")

    suggested = stock_picks.run_stock_picks(out["sectors"])
    if suggested:
        print(f"Suggested {len(suggested)} new stock pick(s): {', '.join(suggested)}")

    snapshot_rows = market_watch.run_market_watch()
    print(f"Market watch: priced {len(snapshot_rows)} watchlist ticker(s)")

    brief = eli5.run_eli5(out["sectors"], snapshot_rows)
    print(f"Today's brief: {brief}")

    trade_log = paper_trader.run_daily_paper_trading(out["sectors"])
    for line in trade_log:
        print(line)

    print(json.dumps({"date": today, "predictions_logged": predictions_logged,
                       "trades": trade_log}, indent=2))


if __name__ == "__main__":
    main()
