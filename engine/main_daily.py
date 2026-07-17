"""
Runs once per day via GitHub Actions (see .github/workflows/daily.yml):
  1. Compute today's planetary positions + sector signals
  2. Log the planetary snapshot and every prediction to Supabase
  3. Fetch current prices for predicted sectors and stamp them on the prediction
  4. Run the paper trading bot against today's signals
"""
from datetime import date
import json
import signals as sig_mod
import supabase_client as db
import data_fetch
from rulerships import SECTOR_TICKERS
import paper_trader


def main():
    out = sig_mod.generate_signals()
    today = date.today().isoformat()

    # Pull learned weights if we have any yet
    weights_rows = db.select("rule_weights")
    rule_weights = {w["planet"]: w["weight"] for w in weights_rows}
    if rule_weights:
        out = sig_mod.generate_signals(rule_weights=rule_weights)

    # Log planetary snapshot (idempotent per day)
    try:
        db.upsert("planetary_log", {
            "date": today,
            "positions": out["positions"],
            "aspects": out["aspects"],
        }, on_conflict="date")
    except Exception as e:
        print(f"planetary_log upsert warning: {e}")

    # Log each sector prediction with a live price stamp
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

        db.insert("predictions", {
            "date": today, "sector": sector, "ticker": ticker,
            "direction": sig["direction"],
            "possibility_indicator": sig["possibility_indicator"],
            "reasons": sig["reasons"], "contributing_planets": sig["contributing_planets"],
            "price_at_prediction": price,
        })
        predictions_logged += 1

    print(f"Logged {predictions_logged} predictions for {today}")

    # Run paper trading bot
    trade_log = paper_trader.run_daily_paper_trading(out["sectors"])
    for line in trade_log:
        print(line)

    print(json.dumps({"date": today, "predictions_logged": predictions_logged,
                       "trades": trade_log}, indent=2))


if __name__ == "__main__":
    main()
