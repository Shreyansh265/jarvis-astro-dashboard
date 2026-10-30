"""
Graha's frozen weekly picks. Created on the weekend for the COMING trading
week from the already-computed sector_forecast (pure compute, zero API
credits) and never regenerated once the week starts -- picked_at is the
hindsight-proof receipt shown in the UI.

Rules (decided with the user):
  * Only strong signals, up to MAX_PICKS. A quiet week yields fewer picks
    (or none) -- weak picks are never padded in to look fuller.
  * A sector qualifies when, across that week's trading days, one direction
    is signalled on >= MIN_AGREEING_DAYS days and the mean strength of those
    days is >= STRENGTH_BAR (same bar as stock_picks.CONFIDENCE_BAR).
  * One lead stock per sector (first in SECTOR_TOP_STOCKS); sectors without a
    curated stock (US_Broad, Silver) can't be picked.
  * bullish = "expected up", bearish = "expected down" -- scored separately.
"""
from datetime import date, datetime, timedelta, timezone
import supabase_client as db
from rulerships import SECTOR_TICKERS, SECTOR_TOP_STOCKS
import trading_calendar as cal
import os
import pick_of_week as pow_
import stock_outlook as so
import trader_desk
from rulerships import SECTOR_STOCK_UNIVERSE

MAX_PICKS = 5
STRENGTH_BAR = 65
MIN_AGREEING_DAYS = 3


def sector_candidates(forecast_rows: list, trading_days: list) -> list:
    """Pure: forecast rows for the week -> every qualifying (sector, direction),
    strongest first, one entry per sector (a sector can't be up and down)."""
    days = {d.isoformat() for d in trading_days}
    by_sector = {}
    for r in forecast_rows:
        if r["forecast_date"] in days:
            by_sector.setdefault(r["sector"], []).append(r)

    candidates = []
    for sector, rows in by_sector.items():
        if not SECTOR_TOP_STOCKS.get(sector) or sector not in SECTOR_TICKERS:
            continue
        for direction in ("bullish", "bearish"):
            agreeing = [r for r in rows if r.get("has_signal") and r["direction"] == direction]
            if len(agreeing) < MIN_AGREEING_DAYS:
                continue
            mean_strength = sum(float(r["strength"]) for r in agreeing) / len(agreeing)
            if mean_strength < STRENGTH_BAR:
                continue
            best = max(agreeing, key=lambda r: float(r["strength"]))
            candidates.append({
                "sector": sector, "direction": direction, "strength": round(mean_strength, 1),
                "agreeing": len(agreeing), "total": len(rows),
                "plain_reasons": best.get("plain_reasons") or [],
            })
    candidates.sort(key=lambda c: (-c["strength"], c["sector"]))
    out, seen = [], set()
    for c in candidates:
        if c["sector"] in seen:
            continue  # a sector can't be both up and down in one week
        seen.add(c["sector"])
        out.append(c)
    return out


def select_picks(forecast_rows: list, trading_days: list) -> list:
    """Pure: the up-to-MAX_PICKS 'on the radar' sectors."""
    return sector_candidates(forecast_rows, trading_days)[:MAX_PICKS]


def _candidate_row(c, first, last, is_pick=False, is_control=False):
    return {
        "week_start": first.isoformat(), "week_end": last.isoformat(), "ticker": c["ticker"],
        "sector": c["sector"], "direction": c["direction"], "composite": c["composite"],
        "sector_strength": c["sector_strength"], "company_score": c["company_score"],
        "chart_basis": c["chart_basis"], "rank": c.get("rank"), "is_pick": is_pick,
        "is_random_control": is_control, "rules_version": pow_.cc.RULES_VERSION, "status": "pending",
    }


def _build_pick_of_week(forecast, trading_days, first, last):
    """Returns (pick_row | None, candidate_rows, pick_dict | None). Pure apart from
    the history read and the ephemeris."""
    qualifying = sector_candidates(forecast, trading_days)
    if not qualifying:
        return None, [], None
    signed = so.sector_signed_map(forecast)
    charts = so.load_charts()
    cands = pow_.week_candidates(qualifying, SECTOR_STOCK_UNIVERSE, charts, signed, trading_days)
    if not cands:
        return None, [], None
    pick = cands[0]
    plain = pick["sector_info"].get("plain_reasons") or []
    history = db.select("weekly_picks", {"pick_of_week": "eq.true", "limit": "500"})
    row = {
        "week_start": first.isoformat(), "week_end": last.isoformat(),
        "ticker": pick["ticker"], "sector": pick["sector"], "etf_ticker": SECTOR_TICKERS.get(pick["sector"]),
        "direction": pick["direction"], "rank": 0, "strength": abs(pick["composite"]),
        "reasoning": pow_.build_reasoning(pick), "plain_reasons": plain, "status": "pending",
        "pick_of_week": True, "factors": pow_.build_factors(pick, plain),
        "trader_desk": trader_desk.safe_desk(pick["ticker"], pick["direction"]),   # None if fetch fails; never blocks the pick
        "record_snapshot": pow_.record_snapshot(history), "rules_version": pow_.cc.RULES_VERSION,
    }
    cand_rows = [_candidate_row(c, first, last, is_pick=c["rank"] == 1) for c in cands[:pow_.TOP_N]]
    control = pow_.random_control(pick, SECTOR_STOCK_UNIVERSE, charts, signed, trading_days, first.isoformat())
    if control and control["ticker"] not in {c["ticker"] for c in cands[:pow_.TOP_N]}:
        cand_rows.append(_candidate_row(control, first, last, is_control=True))
    return row, cand_rows, pick


def create_weekly_picks(today: date = None) -> list:
    dry_run = os.environ.get("DRY_RUN") == "1"
    today = today or datetime.now(timezone.utc).date()
    if today.weekday() < 5 and not dry_run:
        print("weekly_picks: picks are only created on the weekend for the coming week "
              "(never mid-week -- that would be hindsight); skipping.")
        return []
    monday = cal.next_monday(today)
    first, last = cal.week_bounds(monday)
    if not first:
        print(f"weekly_picks: market closed all week of {monday}; no picks.")
        return []
    existing = db.select("weekly_picks", {"week_start": f"eq.{first.isoformat()}", "limit": "1"})
    if existing and not dry_run:
        print(f"weekly_picks: week of {first} already has frozen picks; leaving them untouched.")
        return []

    trading_days = [monday + timedelta(days=i) for i in range(5)
                    if cal.is_trading_day(monday + timedelta(days=i))]
    forecast = db.select("sector_forecast", {
        "forecast_date": f"gte.{first.isoformat()}", "limit": "1000"})
    forecast = [r for r in forecast if r["forecast_date"] <= last.isoformat()]
    picks = select_picks(forecast, trading_days)

    schema_ok = db.schema_ready(2)
    pick_row, cand_rows, pick = None, [], None
    if schema_ok:
        pick_row, cand_rows, pick = _build_pick_of_week(forecast, trading_days, first, last)
        if pick_row:
            print(f"weekly_picks: PICK OF THE WEEK -> {pick_row['ticker']} {pick_row['direction']} "
                  f"(composite {pick['composite']}, {pick['chart_basis']} chart)")
            print("  " + pick_row["reasoning"])
        else:
            print("weekly_picks: no stock clears the bar this week -- no Pick of the Week (not padded).")

    rows, rank = [], 0
    for p in picks:
        ticker = SECTOR_TOP_STOCKS[p["sector"]][0]
        if pick_row and ticker == pick_row["ticker"]:
            continue  # already the Pick of the Week
        rank += 1
        word = "up" if p["direction"] == "bullish" else "down"
        reasoning = (f"Sky leans {word} on {p['agreeing']} of {p['total']} trading days "
                     f"(average strength {p['strength']}/100)")
        row = {
            "week_start": first.isoformat(), "week_end": last.isoformat(),
            "ticker": ticker, "sector": p["sector"],
            "etf_ticker": SECTOR_TICKERS[p["sector"]], "direction": p["direction"],
            "rank": rank, "strength": p["strength"], "reasoning": reasoning,
            "plain_reasons": p["plain_reasons"], "status": "pending",
        }
        if schema_ok:
            row["rules_version"] = "sector-1"
        rows.append(row)

    if dry_run:
        print(f"weekly_picks: DRY RUN -- would freeze {len(rows)} radar pick(s), "
              f"{'1 pick of the week' if pick_row else 'no pick of the week'}, "
              f"{len(cand_rows)} candidate log row(s). Nothing written.")
        for c in cand_rows:
            tag = "PICK" if c["is_pick"] else ("control" if c["is_random_control"] else "")
            print(f"   #{c['rank']} {c['ticker']:6s} {c['direction']:8s} composite {c['composite']:>6} "
                  f"[{c['chart_basis']}] {tag}")
        return rows

    all_rows = ([pick_row] if pick_row else []) + rows
    if all_rows:
        db.insert("weekly_picks", all_rows)
    if cand_rows:
        db.upsert("pick_candidates", cand_rows, on_conflict="week_start,ticker")
    if pick_row:
        # Zero-credit: seed the pick's own day-by-day outlook so the Dashboard has a daily reading.
        try:
            so.run_stock_outlook(extra={pick_row["ticker"]: pick_row["sector"]})
        except Exception as e:
            print(f"weekly_picks: stock outlook for the pick failed: {e}")
    print(f"weekly_picks: froze {len(all_rows)} pick(s) for week of {first}")
    return all_rows


if __name__ == "__main__":
    create_weekly_picks()
