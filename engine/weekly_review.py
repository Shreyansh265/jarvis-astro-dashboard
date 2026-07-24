"""
Weekly self-review: a narrative rollup of the past 7 days. Since
daily_review.py now reviews each prediction about a day after it's made,
by the time this runs (Sunday) nearly everything from the past week should
already be reviewed -- this mostly aggregates what daily_review already
scored into a human-readable weekly summary, rather than re-scoring
everything itself.

It keeps the original time-series-based scorer as a fallback ONLY for
stragglers that are somehow still unreviewed after 7 days (e.g. a daily
run failed) -- that path costs one get_time_series call per straggler, so
it should be rare in practice, not the common case.
"""
from datetime import date, timedelta
import supabase_client as db
import data_fetch
import review_common


def _week_bounds():
    today = date.today()
    week_start = today - timedelta(days=7)
    return week_start, today


def _catch_up_stragglers(week_start) -> None:
    stragglers = db.select("predictions", {
        "date": f"gte.{week_start.isoformat()}",
        "reviewed": "eq.false",
    })
    if not stragglers:
        return

    weight_deltas = {}
    for pred in stragglers:
        try:
            bars = data_fetch.get_time_series(pred["ticker"], interval="1day", outputsize=10)
        except Exception as e:
            print(f"weekly_review straggler: could not verify {pred['ticker']}: {e}")
            continue
        relevant = [b for b in bars if b["date"][:10] >= pred["date"]]
        if len(relevant) < 2:
            continue  # still too recent to judge -- leave unreviewed for next time

        outcome = review_common.score_prediction(pred, relevant[-1]["close"])
        if outcome is None:
            continue
        db.update("predictions", {"id": f"eq.{pred['id']}"}, {"reviewed": True, **outcome})
        for planet in pred.get("contributing_planets", []):
            weight_deltas.setdefault(planet, []).append(1 if outcome["was_correct"] else -1)

    review_common.apply_weight_deltas(weight_deltas, db)


def run_weekly_review():
    week_start, week_end = _week_bounds()

    _catch_up_stragglers(week_start)

    reviewed = db.select("predictions", {
        "date": f"gte.{week_start.isoformat()}",
        "reviewed": "eq.true",
        "was_correct": "not.is.null",  # excludes rows marked reviewed with no
                                        # real outcome (e.g. a ticker that
                                        # permanently can't be priced) -- those
                                        # were never actually evaluated, so
                                        # they shouldn't count toward accuracy
    })

    if not reviewed:
        return {"summary": "No predictions old enough to review yet this week.", "total": 0}

    correct_count = sum(1 for p in reviewed if p.get("was_correct"))
    total = len(reviewed)
    accuracy = round(correct_count / total * 100, 1)

    lessons = [{
        "sector": p["sector"], "ticker": p["ticker"], "predicted": p["direction"],
        "possibility_indicator": p["possibility_indicator"],
        "actual": p["outcome_direction"], "actual_pct_move": p["outcome_pct_change"],
        "contributing_planets": p.get("contributing_planets", []),
        "reason_it_missed": review_common.lesson_text(p, {
            "outcome_direction": p["outcome_direction"], "outcome_pct_change": p["outcome_pct_change"],
        }),
    } for p in reviewed if not p.get("was_correct")]

    summary = (f"Reviewed {total} predictions from {week_start} to {week_end}. "
               f"{correct_count} correct ({accuracy}% accuracy). "
               f"{len(lessons)} miss(es) this week.")

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
