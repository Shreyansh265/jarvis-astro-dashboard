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

    # Also price whatever arbitrary tickers the user has manually added to
    # their real Portfolio (e.g. a holding like ORCL that isn't in our
    # curated watchlist at all) -- reuses this same table/module instead of
    # a parallel one, tagged with a sentinel sector so it's distinguishable
    # from a real astro-signaled sector.
    try:
        portfolio_rows = db.select("portfolio", {"select": "ticker"})
        for row in portfolio_rows:
            ticker_sector.setdefault(row["ticker"], "Portfolio")
    except Exception as e:
        print(f"market_watch: could not load portfolio tickers: {e}")

    # Same idea for every user's "Track a Stock" pick (stock_watch, one row
    # per user) -- setdefault() means an earlier block's sector wins if a
    # tracked ticker happens to already be curated or in someone's
    # portfolio, which is harmless here (this loop only ever needs the
    # ticker to fetch a price, not the sector) but worth noting so it's
    # not mistaken for a bug later.
    try:
        watch_rows = db.select("stock_watch", {"select": "ticker"})
        for row in watch_rows:
            ticker_sector.setdefault(row["ticker"], "Watchlist")
    except Exception as e:
        print(f"market_watch: could not load stock_watch tickers: {e}")

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
