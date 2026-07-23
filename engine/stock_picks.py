"""
Suggests individual stocks within sectors that currently have a strong
enough astro signal (same confidence bar the paper trading bot uses), for
the Astro Stocks tab. Skips a ticker if it already has an active
suggestion so re-running the same day doesn't spam duplicates.

Doesn't compute a "current price" column here -- market_watch.py prices
this exact same curated watchlist every run, and the frontend joins
against its latest market_snapshot row for that. This module only stamps
price_at_suggestion once, at the moment a NEW pick is made.
"""
from datetime import date
import supabase_client as db
import data_fetch
from rulerships import SECTOR_TOP_STOCKS

CONFIDENCE_BAR = 65


def _active_tickers() -> set:
    rows = db.select("suggested_stocks", {"is_active": "eq.true", "select": "ticker"})
    return {r["ticker"] for r in rows}


def run_stock_picks(sector_signals: dict) -> list:
    """sector_signals = output of signals.generate_signals()['sectors']"""
    today = date.today().isoformat()
    already_active = _active_tickers()
    suggested = []

    for sector, sig in sector_signals.items():
        if sig["direction"] not in ("bullish", "bearish"):
            continue
        if sig["possibility_indicator"] < CONFIDENCE_BAR:
            continue
        for ticker in SECTOR_TOP_STOCKS.get(sector, []):
            if ticker in already_active:
                continue
            try:
                price = data_fetch.get_quote(ticker)["price"]
            except Exception as e:
                print(f"stock_picks: price fetch failed for {ticker}: {e}")
                price = None

            reasoning = (f"{sector.replace('_', ' ')} is {sig['direction']} today "
                         f"(possibility {sig['possibility_indicator']}%): "
                         + "; ".join(sig["reasons"][:2]))
            db.insert("suggested_stocks", {
                "date_suggested": today, "sector": sector, "ticker": ticker,
                "direction": sig["direction"], "reasoning": reasoning,
                "price_at_suggestion": price,
            })
            suggested.append(ticker)
            already_active.add(ticker)

    return suggested
