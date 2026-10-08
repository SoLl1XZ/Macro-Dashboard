"""Pure calculations on observation lists. No network or file access, so all of it is unit tested.

An observation list is a list of (ISO date, value) tuples sorted by date.
"""

import bisect
import calendar
import math
import statistics
from datetime import date, timedelta

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


def ratio(a: list[Observation], b: list[Observation]) -> list[Observation]:
    """a divided by b, on the dates where both series have a value, e.g. copper/gold."""
    b_by_date = dict(b)
    return [(d, value / b_by_date[d]) for d, value in a if b_by_date.get(d)]


def in_latest_prices(nominal: list[Observation], price_index: list[Observation]) -> list[Observation]:
    """Nominal values restated in the prices of the index's latest month ("today's dollars").

    A value from a month when the index was half today's level counts double.
    """
    if not price_index:
        return []
    latest = price_index[-1][1]
    index_by_date = dict(price_index)
    return [(d, value * latest / index_by_date[d]) for d, value in nominal if index_by_date.get(d)]


def drawdown(obs: list[Observation]) -> list[Observation]:
    """Percent below the highest value so far: 0 at a new top, -25 after a fall from 200 to 150.

    Only the fetched history counts, so a top from before the first observation is not seen.
    """
    result = []
    peak = None
    for d, value in obs:
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            result.append((d, (value / peak - 1) * 100))
    return result


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
MAX_WEEKLY_MOVE_AGE_DAYS = 7


def history_window(obs: list[Observation], years: int) -> list[Observation] | None:
    """The observations of the last `years` years, or None if they can't describe 'normal'.

    None if the series is younger than the window, or has too few points to compare with.
    """
    if not obs:
        return None
    window_start = shift_months(obs[-1][0], -12 * years)
    if obs[0][0] > shift_months(window_start, 1):
        return None
    window = [o for o in obs if o[0] >= window_start]
    return window if len(window) >= MIN_PERCENTILE_OBSERVATIONS else None


def percentile_rank(obs: list[Observation], years: int = PERCENTILE_YEARS) -> float | None:
    """Where the last value ranks (0–100) among the observations of the last `years` years.

    Equal values count half, so a rate that hasn't moved for years lands mid-range, not at 100.
    """
    window = history_window(obs, years)
    if window is None:
        return None
    last_value = obs[-1][1]
    below = sum(1 for _, value in window if value < last_value)
    equal = sum(1 for _, value in window if value == last_value)
    return (below + 0.5 * equal) / len(window) * 100


def z_score(obs: list[Observation], years: int = PERCENTILE_YEARS) -> float | None:
    """How many standard deviations the last value is from the mean of the last `years` years."""
    window = history_window(obs, years)
    if window is None:
        return None
    values = [value for _, value in window]
    deviation = statistics.pstdev(values)
    return (obs[-1][1] - statistics.fmean(values)) / deviation if deviation > 0 else None


def relative_change(earlier: float, later: float, kind: str) -> float | None:
    if kind == "pct":
        return (later / earlier - 1) * 100 if earlier != 0 else None
    return later - earlier


def weekly_move(obs: list[Observation], kind: str,
                years: int = PERCENTILE_YEARS) -> tuple[float, float] | None:
    """The change over the last 7 days, and that change measured in typical weekly changes.

    "Typical" is the root mean square of every 7-day change in the window, not the standard
    deviation: a series with a steady trend (a stock index) would otherwise look calm even
    when it moves a lot. Returns None for series without at least weekly data.
    """
    window = history_window(obs, years)
    if window is None or infer_frequency(obs) not in ("D", "W"):
        return None
    dates = [d for d, _ in obs]
    changes = []
    for d, value in window:
        week_before = (date.fromisoformat(d) - timedelta(days=7)).isoformat()
        index = bisect.bisect_right(dates, week_before) - 1
        if index >= 0:
            change = relative_change(obs[index][1], value, kind)
            if change is not None:
                changes.append(change)
    if len(changes) < MIN_PERCENTILE_OBSERVATIONS:
        return None
    typical = math.sqrt(statistics.fmean(change * change for change in changes))
    if typical == 0:
        return None
    return changes[-1], changes[-1] / typical


def summarize(obs: list[Observation], kind: str, today: str) -> dict | None:
    """Headline numbers for a series. Future-dated observations (IMF forecasts) are ignored."""
    known = [o for o in obs if o[0] <= today]
    if not known:
        return None
    last_date, last_value = known[-1]
    # "This week's move" only holds if the series has data from this week; otherwise a
    # lagging source (BIS policy rates) would show a rate change from weeks ago.
    age_days = (date.fromisoformat(today) - date.fromisoformat(last_date)).days
    move = weekly_move(known, kind) if age_days <= MAX_WEEKLY_MOVE_AGE_DAYS else None
    return {
        "lastDate": last_date,
        "last": last_value,
        "change1m": change_since(known, 1, kind),
        "change1y": change_since(known, 12, kind),
        "percentile10y": percentile_rank(known),
        "zscore10y": z_score(known),
        "weekChange": move[0] if move else None,
        "weekMoveZ": move[1] if move else None,  # the week's change in typical weekly changes
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


def is_stale(last_date: str, frequency: str | None, today: str, max_age_days: int | None = None) -> bool:
    """max_age_days replaces the limit for the frequency, for a source that is always slower."""
    if max_age_days is None:
        if frequency is None:
            return False
        max_age_days = MAX_AGE_DAYS[frequency]
    age_days = (date.fromisoformat(today) - date.fromisoformat(last_date)).days
    return age_days > max_age_days


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
