"""
Pick of the Week: ONE stock for the coming week, called up or down strictly from
astrology, frozen on the weekend, scored against the real week afterward.

Method (fixed in advance -- see company_chart.RULES_VERSION):
  * Only sectors that clear the weekly bar (weekly_picks.sector_candidates)
    contribute candidates; only their non-ETF stocks are considered.
  * composite = 0.6 x sector signal (mean signed strength over the week's
    trading days) + 0.4 x the stock's company-chart transit score. A stock with
    no confirmed IPO date is "sector-only" and takes a small penalty. A company
    chart that strongly contradicts the sector makes the stock ineligible.
  * Stocks whose IPO date is still marked 'verify' are not eligible (the pick
    must rest on dates we trust). They remain visible elsewhere as sector-only.
  * Ties break toward a real company chart, then universe order (roughly size).
  * The top 10 candidates and a random same-sector control stock are ALL
    logged to pick_candidates and scored later: picking the best of ~100 noisy
    composites selects noise, so the pick only means something next to the
    candidates it beat and a coin-flip stock from the same sector.
  * If nothing qualifies there is no pick -- never padded.
"""
import random
from datetime import date

import company_chart as cc
import stock_outlook as so

TOP_N = 10
_NON_STOCK_MARKERS = (" · ETF", " · Spot")


def is_stock(name: str) -> bool:
    return not any(m in name for m in _NON_STOCK_MARKERS)


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def week_candidates(qualifying: list, universe: dict, charts: dict,
                    signed: dict, trading_days: list) -> list:
    """Pure-ish (ephemeris for company charts). `qualifying` = weekly_picks.sector_candidates
    output. Returns candidate dicts sorted best-first, with rank assigned."""
    ds = [d.isoformat() for d in trading_days]
    out = []
    for q in qualifying:
        sector, direction = q["sector"], q["direction"]
        sector_week = _mean([signed.get((sector, d), 0.0) for d in ds])
        for order, (ticker, name) in enumerate(universe.get(sector, [])):
            if not is_stock(name):
                continue
            chart = charts.get(ticker)
            if chart and chart["confidence"] == "verify":
                continue   # date unconfirmed -> not pick-eligible
            usable = so.usable_chart(chart)
            wk = cc.week_score(date.fromisoformat(chart["first_trade_date"]), trading_days) if usable else None
            comp = cc.composite(sector_week, wk["score"] if wk else None, usable)
            if not comp["eligible"] or comp["direction"] != direction:
                continue
            out.append({
                "ticker": ticker, "name": name.split(" · ")[0], "sector": sector, "direction": direction,
                "composite": comp["score"], "sector_strength": round(sector_week, 1),
                "company_score": wk["score"] if wk else None, "chart_basis": comp["chart_basis"],
                "week_company": wk, "chart": chart, "order": order, "sector_info": q,
            })
    out.sort(key=lambda c: (-abs(c["composite"]), 0 if c["chart_basis"] == "company" else 1, c["order"]))
    for i, c in enumerate(out, start=1):
        c["rank"] = i
    return out


def random_control(pick: dict, universe: dict, charts: dict, signed: dict,
                   trading_days: list, week_start: str):
    """A random other non-ETF stock from the pick's sector, scored the same way and
    assigned the pick's direction. Seeded by week so reruns reproduce it."""
    pool = [(t, n) for t, n in universe.get(pick["sector"], []) if is_stock(n) and t != pick["ticker"]]
    if not pool:
        return None
    ticker, name = random.Random(f"control-{week_start}").choice(sorted(pool))
    chart = charts.get(ticker)
    usable = so.usable_chart(chart)
    ds = [d.isoformat() for d in trading_days]
    sector_week = _mean([signed.get((pick["sector"], d), 0.0) for d in ds])
    wk = cc.week_score(date.fromisoformat(chart["first_trade_date"]), trading_days) if usable else None
    comp = cc.composite(sector_week, wk["score"] if wk else None, usable)
    return {"ticker": ticker, "sector": pick["sector"], "direction": pick["direction"],
            "composite": comp["score"], "sector_strength": round(sector_week, 1),
            "company_score": wk["score"] if wk else None, "chart_basis": comp["chart_basis"]}


def build_factors(pick: dict, plain_reasons: list) -> dict:
    """The frozen 'why' stored with the pick: sector, company-chart transits, composite, counter-case."""
    name = pick["name"]
    wk = pick.get("week_company")
    days, supportive, against = [], [], []
    sign = 1 if pick["direction"] == "bullish" else -1
    if wk:
        for d in wk["days"]:
            plain = [cc.describe_aspect(a, name) for a in d["aspects"][:3]]
            days.append({"date": d["date"], "score": d["score"], "plain": plain})
            for a in d["aspects"][:3]:
                line = f"{d['date']}: {cc.describe_aspect(a, name)}"
                (supportive if a["points"] * sign > 0 else against).append((abs(a["points"]), line))
    supportive = [l for _, l in sorted(supportive, reverse=True)[:4]]
    against = [l for _, l in sorted(against, reverse=True)[:3]]
    chart = pick.get("chart")
    return {
        "rules_version": cc.RULES_VERSION,
        "sector": {"name": pick["sector"], "direction": pick["direction"],
                   "week_signed_strength": pick["sector_strength"],
                   "agreeing_days": pick["sector_info"]["agreeing"], "total_days": pick["sector_info"]["total"],
                   "plain_reasons": plain_reasons},
        "company": ({
            "name": name, "first_trade_date": chart["first_trade_date"], "confidence": chart["confidence"],
            "week_score": wk["score"], "days": days, "supporting": supportive, "against": against,
        } if wk else None),
        "composite": {"score": pick["composite"], "chart_basis": pick["chart_basis"],
                      "weights": {"sector": cc.SECTOR_WEIGHT, "company": cc.COMPANY_WEIGHT,
                                  "sector_only_factor": cc.SECTOR_ONLY_FACTOR}},
        "counter_case": against if against else
            (["No strong company-chart aspect leans the other way this week."] if wk
             else ["No company chart is used for this stock, so the call rests on the sector signal alone."]),
    }


def build_reasoning(pick: dict) -> str:
    word = "up" if pick["direction"] == "bullish" else "down"
    info = pick["sector_info"]
    base = (f"{pick['name']}: sector sky leans {word} on {info['agreeing']} of {info['total']} trading days "
            f"(average strength {info['strength']}/100)")
    if pick["chart_basis"] == "company":
        return base + f"; its own first-trade chart adds a {pick['company_score']:+.0f} transit reading."
    return base + "; no confirmed company chart, so this is the sector signal alone."


def record_snapshot(rows: list) -> dict:
    """Running record of past Pick-of-the-Week results, frozen with each new pick."""
    done = [r for r in rows if r.get("status") == "complete"]
    return {"n": len(done),
            "right": sum(1 for r in done if r.get("was_correct") is True),
            "wrong": sum(1 for r in done if r.get("was_correct") is False),
            "flat": sum(1 for r in done if r.get("was_correct") is None)}
