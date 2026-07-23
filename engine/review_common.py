"""
Shared prediction-scoring core used by both daily_review.py (the primary
path -- reviews a prediction about a day after it's made, using a fresh
quote) and weekly_review.py's fallback path (a rarer straggler-catch-up
using a historical time series). Single source of truth so a scoring bug
only has to be fixed once, not twice.
"""

LEARNING_RATE = 0.05  # how much one review's result nudges a planet's weight
MIN_WEIGHT, MAX_WEIGHT = 0.15, 0.9


def score_prediction(prediction: dict, comparison_price: float):
    """
    Compares a logged prediction's stamped price against a later price.
    Returns None if the prediction never had a price stamped in the first
    place (price_at_prediction was null -- e.g. the fetch failed that day),
    since there's nothing to score it against.
    """
    start_price = prediction.get("price_at_prediction")
    if not start_price:
        return None
    actual_pct = round((comparison_price - start_price) / start_price * 100, 2)
    actual_direction = "bullish" if actual_pct > 0 else "bearish"
    was_correct = (actual_direction == prediction["direction"])
    return {
        "outcome_direction": actual_direction,
        "outcome_pct_change": actual_pct,
        "was_correct": was_correct,
    }


def apply_weight_deltas(weight_deltas: dict, db) -> None:
    """weight_deltas: {planet: [1 or -1, ...]}. Nudges rule_weights, bounded."""
    if not weight_deltas:
        return
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


def lesson_text(prediction: dict, outcome: dict) -> str:
    return (
        f"Predicted {prediction['direction']} at {prediction['possibility_indicator']}% confidence "
        f"from {', '.join(prediction.get('contributing_planets', []))}, but price moved "
        f"{outcome['outcome_direction']} ({outcome['outcome_pct_change']}%). The rule weight for "
        f"the contributing planet(s) is being adjusted so this exact signal carries less "
        f"influence next time."
    )
