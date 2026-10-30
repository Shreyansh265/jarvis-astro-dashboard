"""
Per-stock daily outlook: the sector signal for the stock's sector blended with
its own company-chart transits (company_chart.composite). Pure compute, zero
Twelve Data credits.

Written to stock_forecast for tracked tickers (stock_watch / sector_watch) and
for the Pick of the Week + candidates, covering the next 21 days so "this week"
and "next week" are both available. chart_basis says which inputs actually
produced a reading: 'company' (a confirmed IPO chart was used) or 'sector'
(sector signal only -- no chart, or the IPO date is still marked 'verify').
"""
from datetime import date, timedelta

import company_chart as cc
import trading_calendar as cal

DAYS = 21


def load_charts(path: str = cc.CSV_PATH) -> dict:
    return {r["ticker"]: r for r in cc.load_company_rows(path)}


def usable_chart(chart):
    return bool(chart) and chart["confidence"] == "known"


def sector_signed_map(sector_rows: list) -> dict:
    """{(sector, 'YYYY-MM-DD'): signed strength} -- bullish +, bearish -, no signal 0."""
    out = {}
    for r in sector_rows:
        s = float(r["strength"])
        if not r.get("has_signal") or r["direction"] == "neutral":
            val = 0.0
        else:
            val = s if r["direction"] == "bullish" else -s
        out[(r["sector"], r["forecast_date"])] = val
    return out


def plain_by_sector_date(sector_rows: list) -> dict:
    return {(r["sector"], r["forecast_date"]): r.get("plain_reasons") or [] for r in sector_rows}


def build_stock_rows(ticker: str, name: str, sector: str, chart, days: list,
                     signed: dict, plain: dict) -> list:
    """stock_forecast rows for `ticker` over the given trading days."""
    use_company = usable_chart(chart)
    natal = cc.natal_positions(date.fromisoformat(chart["first_trade_date"])) if use_company else None
    rows = []
    for d in days:
        ds = d.isoformat()
        sector_val = signed.get((sector, ds), 0.0)
        company = cc.daily_score(date.fromisoformat(chart["first_trade_date"]), d, natal) if use_company else None
        comp = cc.composite(sector_val, company["score"] if company else None, use_company)
        direction = comp["direction"] if comp["eligible"] else "neutral"
        score = comp["score"] if comp["eligible"] else 0.0
        factors = {
            "sector": {"name": sector, "signed": sector_val, "plain_reasons": plain.get((sector, ds), [])},
            "company": ({
                "score": company["score"],
                "plain": [cc.describe_aspect(a, name or ticker) for a in company["aspects"][:4]],
                "aspects": company["aspects"],
            } if company else None),
            "chart": {"first_trade_date": chart["first_trade_date"], "confidence": chart["confidence"]} if chart else None,
            "note": comp["reason"] or None,
        }
        rows.append({
            "ticker": ticker, "forecast_date": ds, "direction": direction,
            "score": score, "strength": abs(score), "chart_basis": comp["chart_basis"],
            "factors": factors, "rules_version": cc.RULES_VERSION,
        })
    return rows


def tracked_tickers(db) -> dict:
    """{ticker: sector} for every stock any user tracks."""
    out = {}
    for table in ("stock_watch", "sector_watch"):
        try:
            for r in db.select(table, {"select": "ticker,sector", "limit": "1000"}):
                if r.get("ticker"):
                    out.setdefault(r["ticker"], r["sector"])
        except Exception as e:
            print(f"stock_outlook: could not read {table}: {e}")
    return out


def trading_days_from(start: date, span: int = DAYS) -> list:
    return [start + timedelta(days=i) for i in range(span) if cal.is_trading_day(start + timedelta(days=i))]


def run_stock_outlook(extra: dict = None, today: date = None) -> int:
    """Writes stock_forecast for tracked tickers (+ `extra` {ticker: sector})."""
    import supabase_client as db
    from rulerships import SECTOR_STOCK_UNIVERSE
    if not db.schema_ready(2):
        return 0
    today = today or date.today()
    days = trading_days_from(today)
    if not days:
        return 0
    sector_rows = db.select("sector_forecast", {
        "forecast_date": f"gte.{today.isoformat()}", "limit": "1000"})
    signed, plain = sector_signed_map(sector_rows), plain_by_sector_date(sector_rows)
    charts = load_charts()
    names = {t: n for stocks in SECTOR_STOCK_UNIVERSE.values() for t, n in stocks}

    targets = tracked_tickers(db)
    targets.update(extra or {})
    rows = []
    for ticker, sector in sorted(targets.items()):
        chart = charts.get(ticker)
        nm = (chart or {}).get("name") or names.get(ticker, ticker).split(" · ")[0]
        rows.extend(build_stock_rows(ticker, nm, sector, chart, days, signed, plain))
    if rows:
        db.upsert("stock_forecast", rows, on_conflict="ticker,forecast_date")
    print(f"stock_outlook: wrote {len(rows)} rows for {len(targets)} ticker(s)")
    return len(rows)
