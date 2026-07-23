"""
Runs once per day, as the FIRST step in main_daily.py (before today's
signals are generated): reviews every still-unreviewed prediction from a
prior day against a fresh quote. Comparing yesterday's stamped
price_at_prediction to today's live price already gives a clean
open-to-open, ~1-trading-day return -- there's no need for a historical
time-series call here, which keeps this cheap (one cached get_quote per
ticker, most of which are already being fetched elsewhere this same run).

Only reviews predictions dated strictly before today, even if this job
happens to run more than once in a day (e.g. a manual re-run) -- a
same-day prediction hasn't had any time to play out yet, so scoring it a
few minutes later would be meaningless noise, not a real "did this call
hold up" check.
"""
from datetime import date
import supabase_client as db
import data_fetch
import review_common


def run_daily_review() -> dict:
    today = date.today().isoformat()
    predictions = db.select("predictions", {
        "reviewed": "eq.false",
        "date": f"lt.{today}",
    })
    if not predictions:
        return {"reviewed": 0, "lessons": []}

    weight_deltas = {}
    lessons = []
    reviewed_count = 0

    for pred in predictions:
        ticker = pred["ticker"]
        try:
            quote = data_fetch.get_quote(ticker)
        except Exception as e:
            print(f"daily_review: could not fetch quote for {ticker}: {e}")
            continue

        outcome = review_common.score_prediction(pred, quote["price"])
        if outcome is None:
            continue  # never had a price stamped -- nothing to score against

        db.update("predictions", {"id": f"eq.{pred['id']}"}, {
            "reviewed": True, **outcome,
        })
        reviewed_count += 1

        for planet in pred.get("contributing_planets", []):
            weight_deltas.setdefault(planet, []).append(1 if outcome["was_correct"] else -1)

        if not outcome["was_correct"]:
            lessons.append({
                "sector": pred["sector"], "ticker": ticker,
                "predicted": pred["direction"], "actual": outcome["outcome_direction"],
                "actual_pct_move": outcome["outcome_pct_change"],
                "contributing_planets": pred.get("contributing_planets", []),
                "reason_it_missed": review_common.lesson_text(pred, outcome),
            })

    review_common.apply_weight_deltas(weight_deltas, db)
    return {"reviewed": reviewed_count, "lessons": lessons}


if __name__ == "__main__":
    result = run_daily_review()
    print(f"Reviewed {result['reviewed']} prediction(s).")
    for l in result["lessons"]:
        print(" -", l["reason_it_missed"])
