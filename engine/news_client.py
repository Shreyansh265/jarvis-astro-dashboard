"""
Thin wrapper around Finnhub's free-tier company-news endpoint (60 calls/min
free, no credit card at signup). Separate throttle from Twelve Data's --
their limits are different and shouldn't be assumed to match; the default
below is a conservative placeholder, confirmed/adjusted live once a real
key is available (see portfolio_detail.py's smoke test).
"""
import os
import time
from datetime import date, timedelta
import requests

BASE_URL = "https://finnhub.io/api/v1"
API_KEY = os.environ.get("FINNHUB_API_KEY")

_last_call = 0
_MIN_INTERVAL = 1.1  # conservative default under Finnhub's 60/min free tier


def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call = time.time()


def get_company_news(ticker: str, days_back: int = 5, limit: int = 5) -> list:
    """Recent headlines for a ticker, most recent first."""
    if not API_KEY:
        raise RuntimeError("FINNHUB_API_KEY not set in environment")
    _rate_limit()
    today = date.today()
    from_date = (today - timedelta(days=days_back)).isoformat()
    resp = requests.get(f"{BASE_URL}/company-news", params={
        "symbol": ticker, "from": from_date, "to": today.isoformat(), "token": API_KEY,
    }, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"Finnhub error for {ticker}: {resp.status_code} {resp.text}")
    items = resp.json()
    if not isinstance(items, list):
        raise RuntimeError(f"Finnhub unexpected response for {ticker}: {items}")
    items.sort(key=lambda it: it.get("datetime", 0), reverse=True)
    return [{
        "headline": it.get("headline"),
        "url": it.get("url"),
        "source": it.get("source"),
        "published_at": it.get("datetime"),
        "summary": it.get("summary"),
    } for it in items[:limit]]


if __name__ == "__main__":
    print(get_company_news("AAPL"))
