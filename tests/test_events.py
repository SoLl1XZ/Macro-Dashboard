import contextlib
import io
import json
import unittest
from unittest import mock

import fetch_data
from events import ECB_DECISIONS, FED_DECISIONS, calendar_warnings, upcoming_events


class UpcomingEventsTest(unittest.TestCase):
    def test_only_future_events_sorted_by_date(self):
        events = upcoming_events(["2026-11-04"], today="2026-10-29")
        dates = [event["date"] for event in events]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[0], "2026-10-29")  # an ECB decision today still counts
        self.assertNotIn("2026-10-28", dates)  # yesterday's Fed meeting is gone
        self.assertIn({"date": "2026-11-04", "institution": "Eurostat",
                       "title": "Inflation i eurozonen, foreløbigt tal"}, events)

    def test_nationalbanken_is_expected_the_day_after_each_ecb_decision(self):
        events = upcoming_events([], today="2026-01-01")
        danish = [event["date"] for event in events if event["institution"] == "Nationalbanken"]
        self.assertEqual(danish[0], "2026-10-30")
        self.assertEqual(len(danish), len(ECB_DECISIONS))

    def test_meeting_lists_are_sorted(self):
        self.assertEqual(ECB_DECISIONS, sorted(ECB_DECISIONS))
        self.assertEqual(FED_DECISIONS, sorted(FED_DECISIONS))


class CalendarWarningsTest(unittest.TestCase):
    def test_no_warning_with_meetings_ahead(self):
        self.assertEqual(calendar_warnings("2026-10-07"), [])

    def test_warns_when_a_list_runs_out(self):
        warnings = calendar_warnings("2027-11-01")  # one ECB and one Fed meeting left
        self.assertEqual(len(warnings), 2)
        self.assertIn("ECB", warnings[0])


class FetchHicpFlashDatesTest(unittest.TestCase):
    def test_picks_flash_inflation_releases_from_the_calendar(self):
        calendar = json.dumps([
            {"start": "2026-11-04T11:00Z", "title": "Flash estimate inflation euro area"},
            {"start": "2026-11-05T11:00Z", "title": "Industrial producer prices"},
        ])
        with mock.patch.object(fetch_data, "http_get", return_value=calendar):
            self.assertEqual(fetch_data.fetch_hicp_flash_dates("2026-10-07"), ["2026-11-04"])

    def test_falls_back_to_previous_dates_when_eurostat_fails(self):
        previous = {"events": [{"date": "2026-12-01", "institution": "Eurostat", "title": "x"}]}
        with mock.patch.object(fetch_data, "http_get", side_effect=TimeoutError("down")), \
                contextlib.redirect_stdout(io.StringIO()):
            events = fetch_data.calendar_events(previous, today="2026-10-07")
        self.assertIn("2026-12-01", [e["date"] for e in events if e["institution"] == "Eurostat"])


if __name__ == "__main__":
    unittest.main()
