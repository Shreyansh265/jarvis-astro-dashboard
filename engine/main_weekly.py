"""Runs once per week (Sunday) via GitHub Actions: the self-review/learning cycle."""
import weekly_review


def main():
    result = weekly_review.run_weekly_review()
    print(result["summary"])
    for lesson in result.get("lessons", []):
        print(" -", lesson.get("reason_it_missed", lesson))


if __name__ == "__main__":
    main()
