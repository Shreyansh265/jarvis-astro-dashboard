"""
One-time offline evidence run: replay the FROZEN rules (sector priors, company-chart
transit weights, composite and Pick-of-the-Week selection, all unchanged) over ~10+
years of real daily bars for the stocks with confirmed IPO dates, and publish what
it shows -- whatever it shows. Nothing here is tuned; if the numbers are poor, the
site says so.

Cost: ~1 Twelve Data credit per stock (one long daily window) + SPY, 8 s apart
(~10 minutes). Needs the real ephemeris, so it runs on GitHub Actions only.
Result is stored in analog_cache under key 'evidence_<RULES_VERSION>'.

Known simplifications (stated in the published payload): rule weights are the static
priors (no learning-loop adjustments), because the learned history is itself a fit
to the same period. A week is Monday-Friday windows built from SPY's trading days,
so historical holidays are handled correctly.
"""
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import company_chart as cc
import stock_outlook as so
import pick_of_week as pw
import weekly_picks as wp

START = os.environ.get("EVIDENCE_START", "2010-01-04")
FLAT_BAND_PCT = 0.3
COMPANY_CALL_BAR = 10        # |company week score| to count as a company-chart-only call (pre-registered)


def wilson(k: int, n: int, z: float = 1.96):
    """95% Wilson interval for a proportion; (None, None) when n == 0."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(centre - half, 4), round(centre + half, 4)


def week_groups(ref_days: list) -> list:
    """[[date,...], ...] one list of trading days per Monday-based week, from a reference calendar."""
    by = defaultdict(list)
    for d in sorted(ref_days):
        by[d - timedelta(days=d.weekday())].append(d)
    return [days for _, days in sorted(by.items())]


def week_return(bars_by_date: dict, days: list):
    """(open of first day, close of last day) % change, or None if either bar is missing."""
    first, last = bars_by_date.get(days[0]), bars_by_date.get(days[-1])
    if not first or not last or not first["open"]:
        return None
    return round((last["close"] - first["open"]) / first["open"] * 100, 3)


def verdict(direction: str, ret):
    if ret is None or abs(ret) < FLAT_BAND_PCT:
        return None
    return ret > 0 if direction == "bullish" else ret < 0


def summarize(records: list) -> dict:
    """records: [{'direction','ret','correct'(bool|None)}] -> counts + accuracy + interval."""
    scored = [r for r in records if r["correct"] is not None]
    k = sum(1 for r in scored if r["correct"])
    lo, hi = wilson(k, len(scored))
    return {"calls": len(records), "scored": len(scored), "hits": k,
            "accuracy": round(k / len(scored), 4) if scored else None, "ci95": [lo, hi],
            "flat": len(records) - len(scored),
            "bullish_share": round(sum(1 for r in records if r["direction"] == "bullish") / len(records), 3)
            if records else None}


def baselines(returns: list) -> dict:
    """Always-up / always-down hit rates over the same scored stock-weeks."""
    scored = [r for r in returns if r is not None and abs(r) >= FLAT_BAND_PCT]
    if not scored:
        return {"weeks": 0}
    up = sum(1 for r in scored if r > 0)
    return {"weeks": len(scored), "always_up": round(up / len(scored), 4),
            "always_down": round((len(scored) - up) / len(scored), 4)}


def _fetch_bars(ticker: str, start: str, end: str) -> dict:
    import data_fetch
    rows = data_fetch.get_time_series(ticker, interval="1day", start_date=start, end_date=end)
    return {date.fromisoformat(b["date"][:10]): b for b in rows}


def run_evidence():
    import supabase_client as db
    import forecast
    from rulerships import SECTOR_STOCK_UNIVERSE

    charts = {t: c for t, c in so.load_charts().items() if c["confidence"] == "known"}
    ticker_sector = {}
    for sector, stocks in SECTOR_STOCK_UNIVERSE.items():
        for t, n in stocks:
            if pw.is_stock(n) and t in charts:
                ticker_sector.setdefault(t, (sector, n.split(" · ")[0]))
    end = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    spy = _fetch_bars("SPY", START, end)
    weeks = week_groups(list(spy))
    print(f"evidence: {len(weeks)} weeks from {START}; {len(ticker_sector)} stocks with confirmed charts")
    bars = {}
    for t in ticker_sector:
        try:
            bars[t] = _fetch_bars(t, START, end)
        except Exception as e:
            print(f"evidence: skipping {t}: {e}")

    universe_all = {}
    for t, (sector, name) in ticker_sector.items():
        if t in bars:
            universe_all.setdefault(sector, []).append((t, name))

    methods = defaultdict(list)
    all_returns, by_year = [], defaultdict(list)
    for days in weeks:
        if len(days) < 4:
            continue
        sector_rows, _ = forecast.build_forecast(None, days[0], (days[-1] - days[0]).days + 1)
        sector_rows = [r for r in sector_rows if r["forecast_date"] in {d.isoformat() for d in days}]
        signed = so.sector_signed_map(sector_rows)
        qualifying = wp.sector_candidates(sector_rows, days)
        universe = {s: [(t, n) for t, n in lst if days[0] in bars[t] and days[-1] in bars[t]]
                    for s, lst in universe_all.items()}
        for t in bars:
            all_returns.append(week_return(bars[t], days))
        cands = pw.week_candidates(qualifying, universe, charts, signed, days)
        for c in cands:
            ret = week_return(bars[c["ticker"]], days)
            rec = {"direction": c["direction"], "ret": ret, "correct": verdict(c["direction"], ret)}
            methods["composite_all_candidates"].append(rec)
        if cands:
            top = cands[0]
            ret = week_return(bars[top["ticker"]], days)
            rec = {"direction": top["direction"], "ret": ret, "correct": verdict(top["direction"], ret)}
            methods["pick_of_week_replay"].append(rec)
            by_year[days[0].year].append(rec)
            for c in cands[:pw.TOP_N]:
                r2 = week_return(bars[c["ticker"]], days)
                methods["top10_replay"].append({"direction": c["direction"], "ret": r2,
                                                "correct": verdict(c["direction"], r2)})
        for t, (sector, _) in ticker_sector.items():
            if t not in bars or days[0] not in bars[t] or days[-1] not in bars[t]:
                continue
            ret = week_return(bars[t], days)
            wk = cc.week_score(date.fromisoformat(charts[t]["first_trade_date"]), days)
            if abs(wk["score"]) >= COMPANY_CALL_BAR:
                d = "bullish" if wk["score"] > 0 else "bearish"
                methods["company_chart_only"].append({"direction": d, "ret": ret, "correct": verdict(d, ret)})

    payload = {
        "rules_version": cc.RULES_VERSION, "start": START, "weeks": len(weeks),
        "stocks": len(bars), "computed_at": datetime.now(timezone.utc).isoformat(),
        "methods": {k: summarize(v) for k, v in methods.items()},
        "by_year_pick_replay": {str(y): summarize(v) for y, v in sorted(by_year.items())},
        "baselines": baselines(all_returns),
        "notes": ["Static rule priors (no learning-loop adjustments).",
                  "Stocks with unconfirmed IPO dates excluded; survivorship bias: only stocks that exist today.",
                  "Flat weeks (|return| < 0.3%) are 'no call' and excluded from accuracy.",
                  "Nothing here was tuned after seeing results."],
    }
    for k, v in payload["methods"].items():
        print(f"evidence: {k}: {v}")
    print(f"evidence: baselines {payload['baselines']}")
    db.upsert("analog_cache", {"key": f"evidence_{cc.RULES_VERSION}", "payload": payload,
                               "computed_at": datetime.now(timezone.utc).isoformat()}, on_conflict="key")
    return payload


if __name__ == "__main__":
    run_evidence()
