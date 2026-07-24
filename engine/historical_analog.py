"""
Builds the 4-5 line "why is this a good long-term buy" explanation for each
non-neutral sector, including a genuine historical planetary analog when one
can be found -- a real past date where the contributing planet was in the
same sign with the same retrograde state, with what the sector's ticker
actually did afterward, not generic astrological lore.

Per-planet lookback bound reflects how long each planet actually takes to
leave AND RETURN to a sign (not one global constant) -- Jupiter/Saturn/the
lunar nodes move far slower than the inner planets:
  Sun/Moon/Mercury/Venus/Mars: fast movers, a couple years is ample.
  Jupiter: ~12-year sign cycle, use ~15 years to be safe.
  Saturn: ~29.5-year sign cycle, use ~35 years.
  Rahu/Ketu: ~18.6-year node cycle, use ~20 years.
(Uranus/Neptune/Pluto aren't in PLANET_SECTOR_RULES, so this never needs to
handle them -- their cycles are 84-248 years, far beyond what any sector
ETF's price history could ever verify anyway.)

Correctness note that matters most here: naively walking backward until the
sign matches again would very often just land earlier in the SAME,
still-ongoing transit (e.g. Saturn spends ~2.5 continuous years in a sign --
"3 months ago" during that same visit is not a historical analog). This
walks backward day by day in two phases: (1) skip every day still in
TODAY's sign (the current transit), (2) from the first day the sign
differs, keep walking backward until sign+retrograde match today's again.
That result is a genuine prior visit.
"""
from datetime import timedelta
from ephemeris import get_positions
import data_fetch

LOOKBACK_YEARS = {
    "Sun": 3, "Moon": 2, "Mercury": 3, "Venus": 3, "Mars": 4,
    "Jupiter": 15, "Saturn": 35, "Rahu": 20, "Ketu": 20,
}


def find_historical_analog(planet: str, today_date, today_sign: str, today_retrograde: bool):
    """Returns the matching historical datetime, or None if the lookback
    (bounded per-planet above) is exhausted without a genuine prior visit."""
    years = LOOKBACK_YEARS.get(planet, 3)
    max_days = int(years * 365.25)
    cursor = today_date - timedelta(days=1)
    left_current_transit = False
    for _ in range(max_days):
        pos = get_positions(cursor)
        if planet not in pos:
            return None
        sign = pos[planet]["sign"]
        if not left_current_transit:
            if sign != today_sign:
                left_current_transit = True
            cursor -= timedelta(days=1)
            continue
        if sign == today_sign and pos[planet]["is_retrograde"] == today_retrograde:
            return cursor
        cursor -= timedelta(days=1)
    return None


# Long-run average degrees/day per sign transit (360 / typical days for a
# full zodiac cycle). Used as a fallback for the days-left-in-sign estimate
# below -- confirmed live this needed fixing: near a retrograde/direct
# station a slow planet's INSTANTANEOUS speed approaches zero, and dividing
# degrees-remaining by a near-zero speed produced an absurd "3317 days left"
# for Saturn in production. The average smooths right past that.
AVG_DEGREES_PER_DAY = {
    "Sun": 360 / 365.25, "Moon": 360 / 27.3, "Mercury": 360 / 88, "Venus": 360 / 225,
    "Mars": 360 / 687, "Jupiter": 360 / 4333, "Saturn": 360 / 10759,
    "Rahu": 360 / 6793, "Ketu": 360 / 6793,
}


def _days_left_in_sign(planet: str, planet_data: dict) -> int:
    speed = planet_data.get("speed") or 0
    avg_speed = AVG_DEGREES_PER_DAY.get(planet, 1.0)
    # If instantaneous speed is too small relative to this planet's average
    # to trust for a linear projection (i.e. near a station), fall back to
    # the average -- otherwise a near-zero denominator blows the estimate up.
    effective_speed = speed if abs(speed) > avg_speed * 0.15 else avg_speed
    degrees_left = 30 - planet_data["degree_in_sign"]
    return max(0, round(degrees_left / abs(effective_speed)))


def _historical_outcome_sentence(ticker: str, match_date, planet: str, sign: str, retro: bool) -> str:
    match_str = match_date.strftime("%Y-%m-%d")
    window_end = (match_date + timedelta(days=10)).strftime("%Y-%m-%d")
    try:
        bars = data_fetch.get_time_series(ticker, interval="1day", start_date=match_str, end_date=window_end)
    except Exception as e:
        print(f"historical_analog: could not verify outcome for {ticker} around {match_str}: {e}")
        return ""
    if len(bars) < 5:
        # Not enough bars in that window (e.g. the ticker didn't exist yet,
        # or it was a holiday-heavy stretch) -- don't claim an outcome we
        # didn't actually check.
        return ""
    start_price, end_price = bars[0]["close"], bars[min(5, len(bars) - 1)]["close"]
    pct_move = round((end_price - start_price) / start_price * 100, 2)
    outcome_word = "rose" if pct_move > 0 else "fell"
    return (f" The last genuinely comparable setup was around {match_str}, when {planet} was last in "
            f"{sign}{' (retrograde)' if retro else ''} after having actually left and come back -- not "
            f"just an earlier point in the same transit. In the week after that, {ticker} {outcome_word} "
            f"{abs(pct_move)}%.")


def build_long_term_note(sector: str, ticker: str, direction: str, reasons: list,
                          contributing_planets: list, today_positions: dict, today_date) -> str:
    """Returns a 4-5 sentence explanation, or None if there's nothing
    meaningful to say (neutral direction, or no contributing planet)."""
    if direction == "neutral" or not contributing_planets:
        return None

    planet = contributing_planets[0]  # fixed, documented tie-break -- keeps this deterministic day to day
    if planet not in today_positions:
        return None
    planet_data = today_positions[planet]
    today_sign, today_retro = planet_data["sign"], planet_data["is_retrograde"]
    days_left = _days_left_in_sign(planet, planet_data)

    note = (
        f"Graha's long-term read on {sector.replace('_', ' ')}: {reasons[0]}. "
        f"That placement holds for roughly the next {days_left} days (until {planet} changes sign), "
        f"so this is meant as a weeks-scale case, not a one-day call. "
        f"This is a rules-based read, not a promise -- it's exactly the kind of call the daily and "
        f"weekly review loops are watching, and the rule weight behind it adjusts if it keeps missing."
    )

    match_date = find_historical_analog(planet, today_date, today_sign, today_retro)
    if not match_date:
        print(f"historical_analog: no genuine past match for {planet} within lookback (sector={sector})")
        return note

    note += _historical_outcome_sentence(ticker, match_date, planet, today_sign, today_retro)
    return note
