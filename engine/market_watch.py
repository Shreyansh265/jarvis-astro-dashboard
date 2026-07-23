"""
Daily price scan of the curated stock watchlist (the same tickers as
SECTOR_TOP_STOCKS) -- powers "top gainers/losers" on the Overview tab and
the "current price" shown for Astro Stocks picks. Twelve Data's free tier
has no market-wide movers endpoint (confirmed: 403, paid-tier only), so
this is scoped to our own watchlist, not a real market-wide scan -- said
plainly here and in the UI copy so it isn't overclaimed.
"""
from datetime import date
import supabase_client as db
import data_fetch
from rulerships import SECTOR_TOP_STOCKS


def run_market_watch() -> list:
    today = date.today().isoformat()
    # A ticker only ever appears under one sector in our curated lists, so
    # flattening to ticker->sector is safe.
    ticker_sector = {}
    for sector, tickers in SECTOR_TOP_STOCKS.items():
        for ticker in tickers:
            ticker_sector.setdefault(ticker, sector)

    rows = []
    for ticker, sector in ticker_sector.items():
        try:
            quote = data_fetch.get_quote(ticker)
        except Exception as e:
            print(f"market_watch: quote failed for {ticker}: {e}")
            continue
        rows.append({
            "date": today, "ticker": ticker, "sector": sector,
            "price": quote["price"], "percent_change": quote["percent_change"],
        })

    if rows:
        db.upsert("market_snapshot", rows, on_conflict="date,ticker")
    return rows
