"""
Computes and stores a daily technical + financial + macro-astro + news
snapshot for every ticker currently in the real Portfolio. Runs POST-
MARKET-CLOSE as its own workflow, not folded into main_daily.py's pre-
market run -- two reasons: (1) "why did this move today" is only
answerable after today happened, and news breaks during the session, so
a pre-market batch would always be a day stale on exactly the question
being asked; (2) main_daily.py already has a hard external deadline
(market open) and has shown real 429s under concurrent-workflow credit
pressure -- this doesn't belong on that time-sensitive path.

"Geopolitical analysis" is deliberately reframed here as macro/sector
astro context (the ticker's sector signal + long_term_note) rather than
a real geopolitical event feed, which doesn't exist for this project.
"""
from datetime import date, datetime, timezone
import supabase_client as db
import data_fetch
import news_client
from rulerships import SECTOR_TOP_STOCKS

NEWS_LOOKBACK_DAYS = 5
NEWS_LIMIT = 5


def _sma(closes: list, period: int):
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 4)


def _rsi(closes: list, period: int = 14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(len(closes) - period, len(closes)):
        change = closes[i] - closes[i - 1]
        (gains if change > 0 else losses).append(abs(change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _reverse_sector_lookup(ticker: str):
    for sector, tickers in SECTOR_TOP_STOCKS.items():
        if ticker in tickers:
            return sector
    return None


def _get_portfolio_tickers() -> list:
    rows = db.select("portfolio", {"select": "ticker"})
    return sorted({r["ticker"] for r in rows})


def run_portfolio_detail() -> list:
    today = date.today().isoformat()
    now = datetime.now(timezone.utc)
    tickers = _get_portfolio_tickers()
    updated = []

    for ticker in tickers:
        row = {"ticker": ticker, "detail_date": today}

        try:
            stats = data_fetch.get_statistics(ticker)
            row["pe_ratio"] = stats["pe_ratio"]
            row["market_cap"] = stats["market_cap"]
            row["profit_margin"] = stats["profit_margin"]
        except Exception as e:
            print(f"portfolio_detail: statistics failed for {ticker}: {e}")

        try:
            bars = data_fetch.get_time_series(ticker, interval="1day", outputsize=60)
            closes = [b["close"] for b in bars]
            row["sma_20"] = _sma(closes, 20)
            row["sma_50"] = _sma(closes, 50)
            row["rsi_14"] = _rsi(closes, 14)
        except Exception as e:
            print(f"portfolio_detail: time_series failed for {ticker}: {e}")

        try:
            quote = data_fetch.get_quote(ticker)
            row["week52_high"] = quote.get("week52_high")
            row["week52_low"] = quote.get("week52_low")
        except Exception as e:
            print(f"portfolio_detail: quote failed for {ticker}: {e}")

        sector = _reverse_sector_lookup(ticker)
        if sector:
            try:
                preds = db.select("predictions", {"date": f"eq.{today}", "sector": f"eq.{sector}"})
                if preds:
                    row["sector"] = sector
                    row["sector_direction"] = preds[0]["direction"]
                    row["sector_possibility_indicator"] = preds[0]["possibility_indicator"]
                    row["sector_reasons"] = preds[0]["reasons"]
                    row["long_term_note"] = preds[0].get("long_term_note")
            except Exception as e:
                print(f"portfolio_detail: sector context failed for {ticker}: {e}")

        try:
            row["news"] = news_client.get_company_news(ticker, days_back=NEWS_LOOKBACK_DAYS, limit=NEWS_LIMIT)
            row["news_as_of"] = now.isoformat()
        except Exception as e:
            print(f"portfolio_detail: news failed for {ticker}: {e}")

        db.upsert("stock_detail", row, on_conflict="ticker,detail_date")
        updated.append(ticker)
        print(f"portfolio_detail: updated {ticker}")

    return updated


if __name__ == "__main__":
    print(run_portfolio_detail())
