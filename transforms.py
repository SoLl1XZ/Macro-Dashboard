"""Pure calculations on observation lists. No network or file access, so all of it is unit tested.

An observation list is a list of (ISO date, value) tuples sorted by date.
"""

import bisect
import calendar
from datetime import date

Observation = tuple[str, float]


def shift_months(iso_date: str, months: int) -> str:
    """Move a date by whole months, clamping the day: 2026-03-31 minus 1 month -> 2026-02-28."""
    d = date.fromisoformat(iso_date)
    year, month_zero_based = divmod(d.year * 12 + d.month - 1 + months, 12)
    month = month_zero_based + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def year_over_year(obs: list[Observation]) -> list[Observation]:
    """Percent change versus the observation exactly one year earlier.

    Meant for monthly and quarterly series, whose dates are always the first of the period.
    """
    value_by_date = dict(obs)
    result = []
    for d, value in obs:
        previous = value_by_date.get(shift_months(d, -12))
        if previous is not None and previous != 0:
            result.append((d, (value / previous - 1) * 100))
    return result


def difference(obs: list[Observation]) -> list[Observation]:
    """Change versus the previous observation, e.g. monthly job gains from total employment."""
    return [(d, value - previous) for (_, previous), (d, value) in zip(obs, obs[1:])]


def spread(a: list[Observation], b: list[Observation]) -> list[Observation]:
    """a minus b, on the dates where both series have a value."""
    b_by_date = dict(b)
    return [(d, value - b_by_date[d]) for d, value in a if d in b_by_date]


def observation_at_or_before(obs: list[Observation], target: str) -> Observation | None:
    dates = [d for d, _ in obs]
    index = bisect.bisect_right(dates, target)
    return obs[index - 1] if index else None


def change_since(obs: list[Observation], months: int, kind: str) -> float | None:
    """Change from `months` before the last observation to the last one.

    kind "diff" gives the difference (%-points for rates), "pct" the percent change (prices).
    Returns None when the series is too sparse, e.g. quarterly data has no 1-month change.
    """
    last_date, last_value = obs[-1]
    target = shift_months(last_date, -months)
    reference = observation_at_or_before(obs, target)
    # A reference far older than the target would silently turn "1 month" into "1 quarter".
    if reference is None or reference[0] < shift_months(target, -1):
        return None
    reference_value = reference[1]
    if kind == "pct":
        return (last_value / reference_value - 1) * 100 if reference_value != 0 else None
    return last_value - reference_value


PERCENTILE_YEARS = 10
MIN_PERCENTILE_OBSERVATIONS = 24


def percentile_rank(obs: list[Observation], years: int = PERCENTILE_YEARS) -> float | None:
    """Where the last value ranks (0–100) among the observations of the last `years` years.

    Equal values count half, so a rate that hasn't moved for years lands mid-range, not at 100.
    None if the series is younger than the window or has too few points to rank against.
    """
    if not obs:
        return None
    last_date, last_value = obs[-1]
    window_start = shift_months(last_date, -12 * years)
    if obs[0][0] > shift_months(window_start, 1):
        return None
    window = [value for d, value in obs if d >= window_start]
    if len(window) < MIN_PERCENTILE_OBSERVATIONS:
        return None
    below = sum(1 for value in window if value < last_value)
    equal = sum(1 for value in window if value == last_value)
    return (below + 0.5 * equal) / len(window) * 100


def summarize(obs: list[Observation], kind: str, today: str) -> dict | None:
    """Headline numbers for a series. Future-dated observations (IMF forecasts) are ignored."""
    known = [o for o in obs if o[0] <= today]
    if not known:
        return None
    last_date, last_value = known[-1]
    return {
        "lastDate": last_date,
        "last": last_value,
        "change1m": change_since(known, 1, kind),
        "change1y": change_since(known, 12, kind),
        "percentile10y": percentile_rank(known),
    }


def infer_frequency(obs: list[Observation]) -> str | None:
    """Guess D, W, M, Q or A (annual) from the typical gap between the latest observations."""
    recent_dates = [date.fromisoformat(d) for d, _ in obs[-13:]]
    if len(recent_dates) < 2:
        return None
    gaps = sorted((later - earlier).days for earlier, later in zip(recent_dates, recent_dates[1:]))
    median_gap = gaps[len(gaps) // 2]  # median, so a weekend or a holiday doesn't decide it
    for max_gap_days, frequency in ((4, "D"), (10, "W"), (45, "M"), (120, "Q")):
        if median_gap <= max_gap_days:
            return frequency
    return "A"


def recession_periods(indicator: list[Observation]) -> list[tuple[str, str]]:
    """Turn a monthly 0/1 recession indicator (FRED's USREC) into (start, end) periods.

    The end is the first day after the last recession month.
    """
    periods = []
    start = None
    for d, value in indicator:
        if value >= 0.5 and start is None:
            start = d
        elif value < 0.5 and start is not None:
            periods.append((start, d))
            start = None
    if start is not None:  # still in a recession at the end of the data
        periods.append((start, shift_months(indicator[-1][0], 1)))
    return periods


def quarter_start(quarter: str) -> str:
    """'2008-Q1' -> '2008-01-01'."""
    year, number = quarter.split("-Q")
    return f"{year}-{3 * int(number) - 2:02d}-01"


def peak_trough_periods(peaks_and_troughs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """CEPR's convention: a recession runs from the quarter after the peak through the trough quarter."""
    return [(shift_months(quarter_start(peak), 3), shift_months(quarter_start(trough), 3))
            for peak, trough in peaks_and_troughs]


# How many days after the start of its period the latest observation may be before the
# series counts as stale. Generous because data is published with a lag: monthly CPI
# arrives weeks after month-end, quarterly GDP one to two months after quarter-end.
MAX_AGE_DAYS = {"D": 10, "W": 21, "M": 120, "Q": 220, "A": 550}


def is_stale(last_date: str, frequency: str | None, today: str) -> bool:
    if frequency is None:
        return False
    age_days = (date.fromisoformat(today) - date.fromisoformat(last_date)).days
    return age_days > MAX_AGE_DAYS[frequency]


def iso_week(iso_date: str) -> tuple[int, int]:
    year, week, _ = date.fromisoformat(iso_date).isocalendar()
    return year, week


def thin_before(obs: list[Observation], cutoff: str) -> list[Observation]:
    """Keep only the last observation of each week before `cutoff`; keep everything after.

    Decades of daily data are far denser than a chart can show and would make data.js
    several megabytes. Monthly and weekly series pass through unchanged.
    """
    result = []
    for i, (d, value) in enumerate(obs):
        next_date = obs[i + 1][0] if i + 1 < len(obs) else None
        is_last_of_week = next_date is None or iso_week(next_date) != iso_week(d)
        if d >= cutoff or is_last_of_week:
            result.append((d, value))
    return result
