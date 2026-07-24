"""
Intraday QQQ analysis: one long-running looped job, not repeated per-tick
cron. GitHub Actions' scheduler flakiness is about whether a scheduled
trigger fires, not about reliability once a job is already running -- so
one job that loops internally (fetch -> evaluate -> sleep 5 min -> repeat)
for the session delivers genuinely reliable 5-minute ticks, instead of
~78 separate cron-triggered cold starts. No pyswisseph needed here -- the
astrology input is read from the Technology-sector prediction
main_daily.py already wrote to Supabase this morning, not recomputed.

Levels (all computed from bars already in memory each tick, zero extra
API cost beyond the one 5-min-bar refetch per tick):
  - Classic floor-trader pivot/R1/R2/S1/S2 from the PRIOR trading day's
    daily OHLC (fetched once at session start).
  - Session VWAP from today's 5-min bars (today's ET calendar date is
    read off the bars' own timestamps -- Twelve Data returns intraday
    bars in the exchange's local time already -- rather than computed
    from a UTC->ET conversion, which sidesteps DST bugs entirely).
  - EMA9/EMA20 on today's 5-min closes.
  - Opening-range high/low (first ~30 min of today's session).

Signal rule (stated plainly, auditable):
  qqq_strategy_weights['astro_component'] >= 0.5  -> ASTRO-GATED MODE:
    BUY only if astro bias is bullish AND confident (>=65) AND price is
    above both VWAP and the pivot; SHORT only if bearish AND confident
    AND price is below both; else HOLD.
  weight < 0.5  -> TECHNICAL-ONLY MODE (the actual "corrects itself"
    behavior change, not just a cosmetic number): astro bias is ignored
    entirely; BUY if price is above both VWAP and pivot, SHORT if below
    both, else HOLD. The bot switches into this mode on its own once
    astro-gated calls have been wrong often enough to drag the weight
    below 0.5.
  Debounce: a new row is only written when the signal actually changes
  from the previous one -- avoids a noisy flip right at a level boundary.

Self-correction: before generating a new signal each tick, re-checks any
BUY/SHORT signal >=45 minutes old that's still 'pending' against the
price just fetched -- correct if price moved favorably by >=0.1% in the
signalled direction, incorrect otherwise -- and nudges the weight
(bounded [0.2, 1.0]). Simplification, stated plainly: the nudge applies
to every evaluated signal regardless of which mode produced it; a more
precise version would only credit/blame the astro component specifically
when its gate was the actual deciding factor. HOLD rows are logged (so
the feed shows when a setup stopped holding) but never evaluated -- there
was no position to have been right or wrong about.
"""
import time
from datetime import datetime, timezone, timedelta
import supabase_client as db
import data_fetch

TICKER = "QQQ"
TICK_SECONDS = 300  # 5 minutes
MAX_RUNTIME = timedelta(hours=5, minutes=45)  # safety margin under the 6-hour Actions hard cap
MARKET_CLOSE_UTC = (20, 5)  # ~4:05pm ET close + buffer (EDT; drifts across DST like this project's other fixed-UTC schedules)
EVAL_DELAY_MINUTES = 45
EVAL_MOVE_THRESHOLD_PCT = 0.1
CONFIDENCE_THRESHOLD = 65
LEARNING_RATE = 0.05
MIN_WEIGHT, MAX_WEIGHT = 0.2, 1.0


def _get_weight():
    rows = db.select("qqq_strategy_weights", {"key": "eq.astro_component"})
    return rows[0] if rows else {"weight": 1.0, "correct_count": 0, "incorrect_count": 0}


def _set_weight(new_weight, correct_delta, incorrect_delta, existing):
    db.upsert("qqq_strategy_weights", {
        "key": "astro_component", "weight": round(min(MAX_WEIGHT, max(MIN_WEIGHT, new_weight)), 3),
        "correct_count": existing["correct_count"] + correct_delta,
        "incorrect_count": existing["incorrect_count"] + incorrect_delta,
    }, on_conflict="key")


def _get_astro_bias():
    today = datetime.now(timezone.utc).date().isoformat()
    rows = db.select("predictions", {"date": f"eq.{today}", "sector": "eq.Technology"})
    if not rows:
        return None, None
    return rows[0]["direction"], rows[0]["possibility_indicator"]


def _pivot_levels(prior_bar):
    h, l, c = prior_bar["high"], prior_bar["low"], prior_bar["close"]
    pivot = round((h + l + c) / 3, 4)
    r1, s1 = round(2 * pivot - l, 4), round(2 * pivot - h, 4)
    r2, s2 = round(pivot + (h - l), 4), round(pivot - (h - l), 4)
    return pivot, r1, r2, s1, s2


def _vwap(bars):
    total_pv, total_v = 0.0, 0.0
    for b in bars:
        typical = (b["high"] + b["low"] + b["close"]) / 3
        vol = b.get("volume") or 0
        total_pv += typical * vol
        total_v += vol
    return round(total_pv / total_v, 4) if total_v else round(bars[-1]["close"], 4)


def _ema(closes, period):
    if len(closes) < period:
        return round(closes[-1], 4) if closes else None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)


def _evaluate_pending_signals(current_price):
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=EVAL_DELAY_MINUTES)).isoformat()
    pending = db.select("qqq_signals", {
        "outcome": "eq.pending", "signal": "in.(BUY,SHORT)", "ts": f"lte.{cutoff}",
    })
    if not pending:
        return
    weight_row = _get_weight()
    weight = weight_row["weight"]
    correct_delta, incorrect_delta = 0, 0
    for sig in pending:
        pct_move = (current_price - sig["price"]) / sig["price"] * 100
        was_correct = (pct_move >= EVAL_MOVE_THRESHOLD_PCT) if sig["signal"] == "BUY" else (pct_move <= -EVAL_MOVE_THRESHOLD_PCT)
        db.update("qqq_signals", {"id": f"eq.{sig['id']}"}, {
            "outcome": "correct" if was_correct else "incorrect",
            "outcome_checked_at": now.isoformat(),
        })
        if was_correct:
            correct_delta += 1
            weight += LEARNING_RATE
        else:
            incorrect_delta += 1
            weight -= LEARNING_RATE
    if correct_delta or incorrect_delta:
        _set_weight(weight, correct_delta, incorrect_delta, weight_row)
        print(f"qqq_monitor: evaluated {len(pending)} pending signal(s), weight now {weight_row['weight']}")


def _run_tick(prior_bar, last_signal):
    bars = data_fetch.get_time_series(TICKER, interval="5min", outputsize=200)
    if not bars:
        return last_signal
    current_price = bars[-1]["close"]

    # Bars come back with timestamps in the exchange's own local time
    # (Twelve Data's meta.exchange_timezone is America/New_York for QQQ),
    # so "today" per the latest bar's own date string is already the
    # correct ET trading day -- no UTC->ET conversion needed.
    today_str = bars[-1]["date"][:10]
    todays_bars = [b for b in bars if b["date"][:10] == today_str]

    _evaluate_pending_signals(current_price)

    pivot, r1, r2, s1, s2 = _pivot_levels(prior_bar)
    vwap = _vwap(todays_bars)
    closes = [b["close"] for b in todays_bars]
    ema9, ema20 = _ema(closes, 9), _ema(closes, 20)
    opening_bars = todays_bars[:6]  # first ~30 min of today's session
    opening_high = max(b["high"] for b in opening_bars) if opening_bars else None
    opening_low = min(b["low"] for b in opening_bars) if opening_bars else None

    astro_bias, astro_conf = _get_astro_bias()
    weight_row = _get_weight()
    astro_gated = weight_row["weight"] >= 0.5
    price_above_both = current_price > vwap and current_price > pivot
    price_below_both = current_price < vwap and current_price < pivot

    if astro_gated:
        confident = astro_conf is not None and astro_conf >= CONFIDENCE_THRESHOLD
        if astro_bias == "bullish" and confident and price_above_both:
            signal = "BUY"
        elif astro_bias == "bearish" and confident and price_below_both:
            signal = "SHORT"
        else:
            signal = "HOLD"
        mode = "astro-gated"
    else:
        signal = "BUY" if price_above_both else ("SHORT" if price_below_both else "HOLD")
        mode = "technical-only (astro weight dropped below 0.5)"

    if signal == last_signal:
        return last_signal  # debounce -- no new row unless the signal actually changed

    reasoning = (f"[{mode}] price ${current_price} vs VWAP ${vwap} / pivot ${pivot} "
                 f"(R1 {r1}/S1 {s1}); astro bias {astro_bias} at {astro_conf}%.")
    db.insert("qqq_signals", {
        "price": current_price, "vwap": vwap, "pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2,
        "ema9": ema9, "ema20": ema20, "opening_range_high": opening_high, "opening_range_low": opening_low,
        "astro_bias": astro_bias, "astro_possibility_indicator": astro_conf,
        "signal": signal, "reasoning": reasoning,
    })
    print(f"qqq_monitor: {signal} @ ${current_price} ({mode})")
    return signal


def run_session():
    try:
        prior = data_fetch.get_time_series(TICKER, interval="1day", outputsize=2)
        prior_bar = prior[0]  # ASC order -- the older of the last 2 daily bars is "prior day" even if today's own daily bar already exists intraday
    except Exception as e:
        print(f"qqq_monitor: could not fetch prior day bar, aborting session: {e}")
        return

    start_time = datetime.now(timezone.utc)
    last_signal = None

    while True:
        now = datetime.now(timezone.utc)
        if now - start_time >= MAX_RUNTIME:
            print("qqq_monitor: hit max runtime safety margin, ending session.")
            break
        if (now.hour, now.minute) >= MARKET_CLOSE_UTC:
            print("qqq_monitor: past market close, ending session.")
            break

        try:
            last_signal = _run_tick(prior_bar, last_signal)
        except Exception as e:
            print(f"qqq_monitor: tick failed, will retry next tick: {e}")

        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    run_session()
