"""
Minimal NYSE trading calendar (no dependency). Weeks are NOT assumed to be
Mon-Fri: holidays make 4-day weeks, so every "week" computation here works
off real trading days. Holiday list is hardcoded; extend it each year.
"""
from datetime import date, timedelta

# NYSE full-day closures (observed dates).
NYSE_HOLIDAYS = {
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def next_trading_days(start: date, n: int, include_start: bool = True) -> list:
    out = []
    d = start if include_start else start + timedelta(days=1)
    while len(out) < n:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def next_monday(d: date) -> date:
    """The Monday strictly after d (d on a Monday returns the following one)."""
    return monday_of(d) + timedelta(days=7)


def week_bounds(monday: date) -> tuple:
    """(first_trading_day, last_trading_day) of the Mon-Sun week starting at
    `monday`, or (None, None) if the whole week is closed."""
    days = [monday + timedelta(days=i) for i in range(5)]
    trading = [d for d in days if is_trading_day(d)]
    if not trading:
        return None, None
    return trading[0], trading[-1]
