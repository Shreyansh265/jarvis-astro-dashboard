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

# Twelve Data charges credits per symbol even inside one HTTP call, and a
# single daily run can legitimately ask for the same ticker's quote more
# than once (e.g. a sector ETF gets priced for its prediction stamp, then
# again when checking an open paper-trade position in that same sector).
# Cache per-process so repeat calls in one run are free instead of re-billed.
_quote_cache = {}


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
    """Latest price + daily change for a ticker. Cached per-process."""
    if ticker in _quote_cache:
        return _quote_cache[ticker]
    if not API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY not set in environment")
    _rate_limit()
    symbol = _normalize_symbol(ticker)
    resp = requests.get(f"{BASE_URL}/quote", params={"symbol": symbol, "apikey": API_KEY}, timeout=20)
    data = resp.json()
    if data.get("status") == "error" or "close" not in data:
        raise RuntimeError(f"Twelve Data error for {ticker}: {data}")
    result = {
        "ticker": ticker,
        "price": float(data["close"]),
        "change": float(data.get("change", 0)),
        "percent_change": float(data.get("percent_change", 0)),
        "timestamp": data.get("datetime"),
    }
    _quote_cache[ticker] = result
    return result


def get_time_series(ticker: str, interval: str = "1day", outputsize: int = 500,
                     start_date: str = None, end_date: str = None) -> list:
    """
    Historical OHLC bars, most recent last. Pass start_date/end_date
    ("YYYY-MM-DD") to fetch a specific historical window directly instead
    of the most recent `outputsize` bars -- needed for e.g. a decades-old
    historical analog, where pulling that far back via outputsize alone
    would need thousands of bars in one call. A window before the ticker's
    inception raises cleanly (Twelve Data returns a 400, not empty data),
    which callers should catch and treat as "can't verify this one."
    """
    if not API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY not set in environment")
    _rate_limit()
    symbol = _normalize_symbol(ticker)
    params = {"symbol": symbol, "interval": interval, "apikey": API_KEY, "order": "ASC"}
    if start_date:
        params["start_date"] = start_date
        params["end_date"] = end_date or start_date
    else:
        params["outputsize"] = outputsize
    resp = requests.get(f"{BASE_URL}/time_series", params=params, timeout=20)
    data = resp.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(f"Twelve Data error for {ticker}: {data}")
    return [{"date": v["datetime"], "close": float(v["close"]),
              "open": float(v["open"]), "high": float(v["high"]), "low": float(v["low"])}
             for v in data["values"]]


if __name__ == "__main__":
    print(get_quote("XLE"))
