"""
A company's own astrological chart, cast for its first day of public trading
(the standard financial-astrology "birth" of a listed company), plus daily
transits against it.

Honesty notes (also shown in the UI):
  * The first-trade date is known; the exact moment is not. The chart is cast
    for the regular market open, so the Moon (13 deg/day) is dropped and there
    is no ascendant or house system -- only planet-to-planet transit aspects.
  * Rows marked confidence='verify' in data/company_charts.csv are displayed
    but are NOT used for pick eligibility until the date is confirmed.
  * The weights below are pre-registered: fixed in advance, versioned by
    RULES_VERSION, and never touched by the learning loop. Changing them means
    bumping RULES_VERSION so old forecasts stay attributable to the old rules.
"""
import csv
import math
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import ephemeris

RULES_VERSION = "cc-1"
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "company_charts.csv")
NY = ZoneInfo("America/New_York")
OPEN_CHANGE = date(1985, 9, 30)      # NYSE opened at 10:00 ET before this date

ORB = 3.0                            # degrees; tight on purpose
SCORE_SCALE = 1.5                    # raw -> tanh squash -> -100..100

# Transiting planet: (weight, nature). Moon excluded (too fast); nodes only natal.
TRANSITERS = {
    "Jupiter": (1.0, "benefic"), "Saturn": (1.0, "malefic"), "Mars": (0.7, "malefic"),
    "Venus": (0.6, "benefic"), "Sun": (0.4, "neutral"), "Mercury": (0.4, "neutral"),
}
# Natal point weights. The Sun is the company's core; Moon deliberately absent.
NATAL_POINTS = {
    "Sun": 1.0, "Jupiter": 0.6, "Saturn": 0.6, "Mars": 0.6, "Venus": 0.6,
    "Mercury": 0.6, "Rahu": 0.5, "Ketu": 0.5,
}
# nature -> aspect angle -> signed tone
TONE = {
    "benefic": {0: 1.0, 120: 0.8, 90: -0.4, 180: -0.3},
    "malefic": {0: -1.0, 90: -0.9, 180: -0.9, 120: -0.2},
    "neutral": {0: 0.2, 120: 0.4, 90: -0.3, 180: -0.3},
}
ASPECT_NAME = {0: "conjunct", 90: "square", 120: "trine", 180: "opposite"}

SECTOR_WEIGHT = 0.6                  # composite = 0.6 sector + 0.4 company
COMPANY_WEIGHT = 0.4
SECTOR_ONLY_FACTOR = 0.9             # small penalty when there is no usable company chart
CONTRADICTION_BAR = 40               # company this strongly opposite the sector => ineligible


def natal_moment_utc(first_trade: date) -> datetime:
    """Naive UTC datetime of the regular market open on the first trade date."""
    hh, mm = (10, 0) if first_trade < OPEN_CHANGE else (9, 30)
    local = datetime(first_trade.year, first_trade.month, first_trade.day, hh, mm, tzinfo=NY)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def natal_positions(first_trade: date) -> dict:
    pos = ephemeris.get_positions(natal_moment_utc(first_trade))
    return {k: v for k, v in pos.items() if k in NATAL_POINTS}


def _separation(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def transit_aspects(natal: dict, on_date: date) -> list:
    """Transiting planets (positions at noon UTC) aspecting natal points."""
    trans = ephemeris.get_positions(datetime(on_date.year, on_date.month, on_date.day, 12, 0))
    out = []
    for tp, (tw, nature) in TRANSITERS.items():
        for np_, nw in NATAL_POINTS.items():
            sep = _separation(trans[tp]["longitude"], natal[np_]["longitude"])
            for angle, tone in TONE[nature].items():
                diff = abs(sep - angle)
                if diff <= ORB:
                    closeness = 1 - diff / ORB
                    out.append({
                        "transit": tp, "natal": np_, "aspect": ASPECT_NAME[angle],
                        "orb": round(diff, 2), "nature": nature,
                        "points": round(tw * nw * tone * closeness, 4),
                    })
    out.sort(key=lambda a: -abs(a["points"]))
    return out


def squash(raw: float) -> float:
    return round(math.tanh(raw / SCORE_SCALE) * 100, 1)


def daily_score(first_trade: date, on_date: date, natal: dict = None) -> dict:
    natal = natal or natal_positions(first_trade)
    aspects = transit_aspects(natal, on_date)
    return {"date": on_date.isoformat(), "score": squash(sum(a["points"] for a in aspects)),
            "aspects": aspects[:6]}


def week_score(first_trade: date, trading_days: list) -> dict:
    """Mean company-transit score over the given trading days."""
    natal = natal_positions(first_trade)
    days = [daily_score(first_trade, d, natal) for d in trading_days]
    mean = round(sum(d["score"] for d in days) / len(days), 1) if days else 0.0
    return {"score": mean, "days": days, "rules_version": RULES_VERSION}


def composite(sector_signed: float, company_signed, usable_company: bool) -> dict:
    """Pure. sector_signed / company_signed are -100..100 (bullish positive).

    Returns {score, direction, chart_basis, eligible, reason}. A company chart that
    strongly contradicts the sector direction makes the stock ineligible rather
    than averaging the two into mush."""
    if not usable_company or company_signed is None:
        score = sector_signed * SECTOR_ONLY_FACTOR
        basis = "sector"
    else:
        if sector_signed * company_signed < 0 and abs(company_signed) >= CONTRADICTION_BAR:
            return {"score": 0.0, "direction": None, "chart_basis": "company", "eligible": False,
                    "reason": "company chart strongly contradicts the sector direction"}
        score = SECTOR_WEIGHT * sector_signed + COMPANY_WEIGHT * company_signed
        basis = "company"
    if score == 0:
        return {"score": 0.0, "direction": None, "chart_basis": basis, "eligible": False,
                "reason": "no net lean"}
    return {"score": round(score, 1), "direction": "bullish" if score > 0 else "bearish",
            "chart_basis": basis, "eligible": True, "reason": ""}


# ---------- IPO dates: CSV <-> table ----------
def load_company_rows(path: str = CSV_PATH) -> list:
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ticker = r["ticker"].strip().upper()
            if ticker in seen:
                raise ValueError(f"duplicate ticker in company_charts.csv: {ticker}")
            seen.add(ticker)
            d = date.fromisoformat(r["first_trade_date"].strip())
            if d.weekday() >= 5:
                raise ValueError(f"{ticker}: first trade date {d} is a weekend")
            if d > date.today():
                raise ValueError(f"{ticker}: first trade date {d} is in the future")
            conf = r["confidence"].strip()
            if conf not in ("known", "verify"):
                raise ValueError(f"{ticker}: confidence must be known|verify, got {conf!r}")
            rows.append({"ticker": ticker, "name": r["name"].strip(), "first_trade_date": d.isoformat(),
                         "confidence": conf, "note": r.get("note", "").strip() or None})
    return rows


def sync_company_charts() -> int:
    import supabase_client as db
    if not db.schema_ready(2):
        return 0
    rows = load_company_rows()
    for r in rows:
        r["updated_at"] = datetime.now(timezone.utc).isoformat()
    db.upsert("company_charts", rows, on_conflict="ticker")
    print(f"company_charts: synced {len(rows)} rows "
          f"({sum(1 for r in rows if r['confidence'] == 'verify')} marked verify)")
    return len(rows)


if __name__ == "__main__":
    sync_company_charts()
