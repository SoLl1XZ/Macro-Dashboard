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
    }


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
