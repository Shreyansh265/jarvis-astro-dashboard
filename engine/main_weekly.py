"""Runs once per week (Sunday) via GitHub Actions: the self-review/learning cycle."""
from datetime import date
import weekly_review
import horizon_picks


def main():
    result = weekly_review.run_weekly_review()
    print(result["summary"])
    for lesson in result.get("lessons", []):
        print(" -", lesson.get("reason_it_missed", lesson))

    # Yearly horizon picks recompute monthly, not weekly -- Jupiter/Saturn/
    # the nodes barely change tone week to week, so recomputing every
    # Sunday would just write near-identical rows and waste API credits.
    # Running it only in the first week of the calendar month gives
    # roughly monthly cadence off the same Sunday schedule.
    include_yearly = date.today().day <= 7
    picks_logged = horizon_picks.run_horizon_picks(include_yearly=include_yearly)
    print(f"Horizon picks logged: {picks_logged}")

    reviewed = horizon_picks.review_horizon_picks()
    print(f"Horizon picks reviewed: {reviewed}")


if __name__ == "__main__":
    main()
