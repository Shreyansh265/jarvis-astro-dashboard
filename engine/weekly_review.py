"""
Weekly self-review: looks at every prediction made last week, checks what
actually happened to the price, scores accuracy, and ADJUSTS rule_weights
so the same mistake is less likely to be repeated. This is the "gets better
over time and explains what went wrong" piece the user asked for.
"""
from datetime import date, timedelta
import supabase_client as db
import data_fetch
from rulerships import SECTOR_TICKERS

LEARNING_RATE = 0.05  # how much one week's result nudges a planet's weight
MIN_WEIGHT, MAX_WEIGHT = 0.15, 0.9


def _week_bounds():
    today = date.today()
    week_start = today - timedelta(days=7)
    return week_start, today


def run_weekly_review():
    week_start, week_end = _week_bounds()
    predictions = db.select("predictions", {
        "date": f"gte.{week_start.isoformat()}",
        "reviewed": "eq.false",
    })

    if not predictions:
        return {"summary": "No unreviewed predictions found for this window.", "total": 0}

    weight_deltas = {}
    correct_count = 0
    evaluated_count = 0
    lessons = []

    for pred in predictions:
        ticker = pred["ticker"]
        try:
            bars = data_fetch.get_time_series(ticker, interval="1day", outputsize=10)
        except Exception as e:
            lessons.append({"ticker": ticker, "issue": f"Could not verify outcome: {e}"})
            continue

        relevant = [b for b in bars if b["date"][:10] >= pred["date"]]
        if len(relevant) < 2:
            # Not enough forward price history yet to judge this one (e.g. it
            # was made too recently) -- skip without counting it as a miss.
            continue
        evaluated_count += 1
        start_price = pred.get("price_at_prediction") or relevant[0]["close"]
        end_price = relevant[-1]["close"]
        actual_pct = round((end_price - start_price) / start_price * 100, 2)
        actual_direction = "bullish" if actual_pct > 0 else "bearish"
        was_correct = (actual_direction == pred["direction"])
        if was_correct:
            correct_count += 1

        db.update("predictions", {"id": f"eq.{pred['id']}"}, {
            "reviewed": True, "outcome_direction": actual_direction,
            "outcome_pct_change": actual_pct, "was_correct": was_correct,
        })

        for planet in pred.get("contributing_planets", []):
            weight_deltas.setdefault(planet, []).append(1 if was_correct else -1)

        if not was_correct:
            lessons.append({
                "sector": pred["sector"], "ticker": ticker,
                "predicted": pred["direction"],
                "possibility_indicator": pred["possibility_indicator"],
                "actual": actual_direction, "actual_pct_move": actual_pct,
                "contributing_planets": pred.get("contributing_planets", []),
                "reason_it_missed": (
                    f"Predicted {pred['direction']} at {pred['possibility_indicator']}% confidence "
                    f"from {', '.join(pred.get('contributing_planets', []))}, but price moved "
                    f"{actual_direction} ({actual_pct}%). The rule weight for the contributing "
                    f"planet(s) is being reduced so this exact signal carries less influence next time."
                ),
            })

    # Apply learning: nudge each contributing planet's weight up/down
    current_weights = {w["planet"]: w for w in db.select("rule_weights")}
    for planet, results in weight_deltas.items():
        net = sum(results) / len(results)  # -1..1
        existing = current_weights.get(planet, {"weight": 0.5, "correct_count": 0, "incorrect_count": 0})
        new_weight = existing["weight"] + LEARNING_RATE * net
        new_weight = round(min(MAX_WEIGHT, max(MIN_WEIGHT, new_weight)), 3)
        db.upsert("rule_weights", {
            "planet": planet, "weight": new_weight,
            "correct_count": existing["correct_count"] + sum(1 for r in results if r == 1),
            "incorrect_count": existing["incorrect_count"] + sum(1 for r in results if r == -1),
        }, on_conflict="planet")

    if evaluated_count == 0:
        # Every selected prediction was too recent to have forward price
        # history yet (or its price fetch failed) -- report that honestly
        # instead of fabricating a 0%-accuracy result from zero real checks.
        return {
            "summary": (f"{len(predictions)} predictions pending from {week_start} to {week_end}, "
                        f"but none are old enough to verify against real price moves yet. "
                        f"Check back after they've had at least a day to play out."),
            "total": 0,
        }

    total = evaluated_count
    accuracy = round(correct_count / total * 100, 1) if total else 0
    summary = (f"Reviewed {total} predictions from {week_start} to {week_end}. "
               f"{correct_count} correct ({accuracy}% accuracy). "
               f"{len(lessons)} misses analyzed and rule weights adjusted accordingly.")

    db.insert("weekly_reviews", {
        "week_start": week_start.isoformat(), "week_end": week_end.isoformat(),
        "total_predictions": total, "correct_predictions": correct_count,
        "accuracy_pct": accuracy, "summary": summary, "lessons": lessons,
    })

    return {"summary": summary, "total": total, "correct": correct_count,
            "accuracy_pct": accuracy, "lessons": lessons}


if __name__ == "__main__":
    result = run_weekly_review()
    print(result["summary"])
    for l in result.get("lessons", []):
        print(" -", l.get("reason_it_missed", l))
