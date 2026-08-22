"""
QQQ's once-daily morning call: combines today's Technology-sector astro
bias (read from the prediction main_daily.py already computed earlier in
THIS SAME run -- no pyswisseph needed here) with a technical read from
recent daily bars, into ONE row that's always fully informative -- never
a bare gate-failed HOLD. Replaces the old qqq_monitor.py continuous-loop
mechanism entirely (retired, not reused): that design's astro-gated
BUY/SHORT-or-HOLD rule was diagnosed live as producing exactly one real
signal in 12 days of production data, because Technology-sector
confidence almost never cleared its 65% gate -- switching cadence alone
wouldn't have fixed that, so the OUTPUT is redesigned here to be
graduated instead of gated.

Levels: classic floor-trader pivot/R1/R2/S1/S2 from the most recent
completed daily bar, EMA9/EMA20 from recent daily closes. There's no live
intraday session yet at pre-market time, so this reads recent daily
closes rather than same-day 5-min bars (the old design's approach).

combined_lean is 'call' when astro and technical agree bullish (or only
one has a real opinion and it's bullish), 'put' for the bearish mirror,
'neutral' when they disagree or both are flat -- the row ALWAYS gets a
lean and ALWAYS gets three risk-tier notes, reframed around conviction/
confirmation-strictness rather than options moneyness (there's no real
options-chain data on any plan tier to back strike-relative language):
  aggressive   = act on the lean now, no additional confirmation required
  moderate     = wait for price to confirm against the pivot before acting
  conservative = wait for the bias to persist another day, or sit out

Self-correction: reviews YESTERDAY's combined_lean against today's live
QQQ price relative to yesterday's pivot (a smoothed stand-in for
"yesterday's price level", deliberately used instead of a single raw
close since it's the average of yesterday's H/L/C) -- graded on the
lean's direction only, risk tiers are descriptive metadata, not
separately graded -- and nudges qqq_strategy_weights['astro_component']
the same bounded way the old design did.
"""
from datetime import date, datetime, timezone, timedelta
import supabase_client as db
import data_fetch

LEARNING_RATE = 0.05
MIN_WEIGHT, MAX_WEIGHT = 0.2, 1.0
CONFIDENCE_THRESHOLD = 65


def _pivot_levels(prior_bar: dict):
    h, l, c = prior_bar["high"], prior_bar["low"], prior_bar["close"]
    pivot = round((h + l + c) / 3, 4)
    r1, s1 = round(2 * pivot - l, 4), round(2 * pivot - h, 4)
    r2, s2 = round(pivot + (h - l), 4), round(pivot - (h - l), 4)
    return pivot, r1, r2, s1, s2


def _ema(closes: list, period: int):
    if len(closes) < period:
        return round(closes[-1], 4) if closes else None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)


def _get_astro_bias():
    today = date.today().isoformat()
    rows = db.select("predictions", {"date": f"eq.{today}", "sector": "eq.Technology"})
    if not rows:
        return None, None
    return rows[0]["direction"], rows[0]["possibility_indicator"]


def _get_weight():
    rows = db.select("qqq_strategy_weights", {"key": "eq.astro_component"})
    return rows[0] if rows else {"weight": 1.0, "correct_count": 0, "incorrect_count": 0}


def _combined_lean(astro_bias, astro_conf, technical_bias):
    confident_astro = (astro_bias in ("bullish", "bearish")
                        and astro_conf is not None and astro_conf >= CONFIDENCE_THRESHOLD)
    astro_lean = {"bullish": "call", "bearish": "put"}.get(astro_bias) if confident_astro else None
    tech_lean = {"bullish": "call", "bearish": "put"}.get(technical_bias)

    if astro_lean and tech_lean:
        return astro_lean if astro_lean == tech_lean else "neutral"
    return astro_lean or tech_lean or "neutral"


def _risk_tier_notes(combined_lean: str, pivot: float):
    if combined_lean == "neutral":
        return (
            "No clear lean today -- astrology and price action disagree or are both weak. "
            "Sitting out is the honest aggressive read too.",
            "Wait for either the astro bias or price action to firm up before considering a position.",
            "No action today.",
        )
    verb = "calls" if combined_lean == "call" else "puts"
    return (
        f"Lean is {combined_lean} ({verb}) -- act on it now, no additional confirmation required.",
        f"Lean is {combined_lean}, but wait for price to actually confirm against the pivot (${pivot}) before acting.",
        f"Lean is {combined_lean}, but treat it as tentative -- wait to see if this bias persists into "
        f"tomorrow before treating it as tradeable, or sit out.",
    )


def _review_yesterday():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    pending = db.select("qqq_daily_call", {"call_date": f"eq.{yesterday}", "reviewed_at": "is.null"})
    if not pending:
        return
    call = pending[0]
    now_iso = datetime.now(timezone.utc).isoformat()

    if call["combined_lean"] == "neutral":
        db.update("qqq_daily_call", {"id": f"eq.{call['id']}"}, {"reviewed_at": now_iso})
        return  # nothing to grade -- no directional position was implied

    try:
        current_price = data_fetch.get_quote("QQQ")["price"]
    except Exception as e:
        print(f"qqq_daily_call: could not review yesterday's call: {e}")
        return

    was_correct = (current_price > call["pivot"]) if call["combined_lean"] == "call" else (current_price < call["pivot"])

    weight_row = _get_weight()
    weight = weight_row["weight"] + (LEARNING_RATE if was_correct else -LEARNING_RATE)
    weight = round(min(MAX_WEIGHT, max(MIN_WEIGHT, weight)), 3)
    db.upsert("qqq_strategy_weights", {
        "key": "astro_component", "weight": weight,
        "correct_count": weight_row["correct_count"] + (1 if was_correct else 0),
        "incorrect_count": weight_row["incorrect_count"] + (0 if was_correct else 1),
    }, on_conflict="key")

    db.update("qqq_daily_call", {"id": f"eq.{call['id']}"}, {
        "reviewed_at": now_iso, "actual_close": current_price,
        "was_correct": was_correct, "weight_after": weight,
    })
    print(f"qqq_daily_call: reviewed yesterday's {call['combined_lean']} call -- "
          f"{'correct' if was_correct else 'incorrect'}, weight now {weight}")


def run_qqq_daily_call():
    _review_yesterday()

    try:
        daily_bars = data_fetch.get_time_series("QQQ", interval="1day", outputsize=60)
    except Exception as e:
        print(f"qqq_daily_call: could not fetch QQQ history, skipping today's call: {e}")
        return None

    prior_bar = daily_bars[-1]
    closes = [b["close"] for b in daily_bars]
    pivot, r1, r2, s1, s2 = _pivot_levels(prior_bar)
    ema9, ema20 = _ema(closes, 9), _ema(closes, 20)
    technical_bias = "bullish" if (ema9 and ema20 and ema9 > ema20) else ("bearish" if (ema9 and ema20) else "neutral")

    astro_bias, astro_conf = _get_astro_bias()
    combined_lean = _combined_lean(astro_bias, astro_conf, technical_bias)
    aggressive, moderate, conservative = _risk_tier_notes(combined_lean, pivot)

    db.upsert("qqq_daily_call", {
        "call_date": date.today().isoformat(), "astro_bias": astro_bias, "astro_confidence": astro_conf,
        "technical_bias": technical_bias, "pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2,
        "combined_lean": combined_lean,
        "aggressive_note": aggressive, "moderate_note": moderate, "conservative_note": conservative,
    }, on_conflict="call_date")

    print(f"qqq_daily_call: {combined_lean} (astro={astro_bias}/{astro_conf}%, technical={technical_bias})")
    return combined_lean


if __name__ == "__main__":
    run_qqq_daily_call()
