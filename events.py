"""Upcoming events shown on the Signals tab.

The ECB and the Fed publish their meeting dates a year or more ahead, but not through an
API, so they are listed here by hand. The page shows a warning when a list is about to run
out; then copy the next dates from the sources below. Eurostat's release dates are fetched
automatically (see fetch_hicp_flash_dates in fetch_data.py).
"""

from datetime import date, timedelta

# Monetary policy decisions: day 2 of each meeting, followed by a press conference.
# Source: https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html (checked 2026-10-07)
ECB_DECISIONS = [
    "2026-10-29", "2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29",
    "2027-06-10", "2027-07-22", "2027-09-09", "2027-10-28", "2027-12-16",
]

# FOMC decisions: day 2 of each meeting.
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (checked 2026-10-07)
FED_DECISIONS = [
    "2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28",
    "2027-06-09", "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
]

# Warn on the page when fewer meetings than this are left in a list.
MIN_UPCOMING_MEETINGS = 2


def next_day(iso_date: str) -> str:
    return (date.fromisoformat(iso_date) + timedelta(days=1)).isoformat()


def upcoming_events(hicp_flash_dates: list[str], today: str) -> list[dict]:
    """All scheduled events from today on, sorted by date."""
    events = []
    for decision in ECB_DECISIONS:
        events.append({"date": decision, "institution": "ECB", "title": "Rentebeslutning"})
        # No meeting calendar was found for Danmarks Nationalbank. In 2019–2026 its rate
        # changes took effect the day after an ECB decision (apart from a few moves of its own).
        events.append({"date": next_day(decision), "institution": "Nationalbanken",
                       "title": "Forventet renteændring, følger typisk ECB"})
    for decision in FED_DECISIONS:
        events.append({"date": decision, "institution": "Fed", "title": "Rentebeslutning (FOMC)"})
    for release in hicp_flash_dates:
        events.append({"date": release, "institution": "Eurostat",
                       "title": "Inflation i eurozonen, foreløbigt tal"})
    return sorted((event for event in events if event["date"] >= today), key=lambda event: event["date"])


def calendar_warnings(today: str) -> list[str]:
    warnings = []
    for name, decisions in (("ECB", ECB_DECISIONS), ("Fed", FED_DECISIONS)):
        if sum(1 for decision in decisions if decision >= today) < MIN_UPCOMING_MEETINGS:
            warnings.append(f"Mødekalenderen for {name} løber snart tør – tilføj nye datoer i events.py.")
    return warnings
