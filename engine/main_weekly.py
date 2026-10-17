"""Runs once per week (Sunday) via GitHub Actions: the self-review/learning cycle."""
from datetime import date
import weekly_review
import horizon_picks
import forecast
import weekly_picks
import analogs


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

    # Forward-looking pieces: each guarded so one failure can't block the rest.
    # Forecast first (zero credits) -- weekly picks and analogs both read it.
    for name, step in (("forecast", forecast.run_forecast),
                       ("weekly picks", weekly_picks.create_weekly_picks),
                       ("analogs", analogs.refresh_analogs)):
        try:
            step()
        except Exception as e:
            print(f"{name} failed: {e}")


if __name__ == "__main__":
    main()
