"""
Thin wrapper around the Twelve Data API (free tier: 800 requests/day, 8/min).
Handles both NYSE tickers (e.g. XLE) and TSX tickers (e.g. XIU.TO -> Twelve
Data format 'XIU:TSX').
"""
import os
import time
import requests

BASE_URL = "https://api.twelvedata.com"
API_KEY = os.environ.get("TWELVE_DATA_API_KEY")

_last_call = 0
_MIN_INTERVAL = 8.0  # seconds, to stay under 8 req/min free tier


def _rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call = time.time()


def _normalize_symbol(ticker: str) -> str:
    """Converts 'XIU.TO' style -> Twelve Data's 'XIU:TSX' style."""
    if ticker.endswith(".TO"):
        return ticker.replace(".TO", ":TSX")
    return ticker


def get_quote(ticker: str) -> dict:
    """Latest price + daily change for a ticker."""
    if not API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY not set in environment")
    _rate_limit()
    symbol = _normalize_symbol(ticker)
    resp = requests.get(f"{BASE_URL}/quote", params={"symbol": symbol, "apikey": API_KEY}, timeout=20)
    data = resp.json()
    if data.get("status") == "error" or "close" not in data:
        raise RuntimeError(f"Twelve Data error for {ticker}: {data}")
    return {
        "ticker": ticker,
        "price": float(data["close"]),
        "change": float(data.get("change", 0)),
        "percent_change": float(data.get("percent_change", 0)),
        "timestamp": data.get("datetime"),
    }


def get_time_series(ticker: str, interval: str = "1day", outputsize: int = 500) -> list:
    """Historical OHLC bars, most recent last."""
    if not API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY not set in environment")
    _rate_limit()
    symbol = _normalize_symbol(ticker)
    resp = requests.get(f"{BASE_URL}/time_series", params={
        "symbol": symbol, "interval": interval, "outputsize": outputsize,
        "apikey": API_KEY, "order": "ASC",
    }, timeout=20)
    data = resp.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(f"Twelve Data error for {ticker}: {data}")
    return [{"date": v["datetime"], "close": float(v["close"]),
              "open": float(v["open"]), "high": float(v["high"]), "low": float(v["low"])}
             for v in data["values"]]


if __name__ == "__main__":
    print(get_quote("XLE"))
