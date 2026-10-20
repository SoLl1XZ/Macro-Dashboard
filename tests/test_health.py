import unittest

from health import failed_series, issue_body


def payload(*series: dict) -> dict:
    return {"generatedAt": "2026-10-20T06:30:00+00:00",
            "panels": [{"id": "p", "title": "Inflation", "section": "us", "series": list(series)}]}


OK = {"key": "us_cpi", "label": "CPI", "error": None, "fallbackFrom": None}
FAILED_WITH_OLD_DATA = {"key": "eq_us", "label": "USA", "error": "HTTPError: HTTP Error 403: Forbidden",
                        "fallbackFrom": "2026-10-19T06:30:00+00:00"}
FAILED_WITHOUT_DATA = {"key": "eq_ca", "label": "Canada", "error": "HTTPError: HTTP Error 403: Forbidden",
                       "fallbackFrom": None}
REFERENCE = {"ref": "eq_ca", "label": "Canada", "error": "HTTPError: HTTP Error 403: Forbidden"}


class HealthTest(unittest.TestCase):
    def test_no_failures_gives_no_issue(self):
        self.assertEqual(failed_series(payload(OK)), [])
        self.assertEqual(issue_body(payload(OK)), "")

    def test_failures_are_listed_once_and_references_are_ignored(self):
        failed = failed_series(payload(OK, FAILED_WITH_OLD_DATA, FAILED_WITHOUT_DATA, REFERENCE))
        self.assertEqual([series["key"] for series in failed], ["eq_us", "eq_ca"])

    def test_issue_groups_series_by_error_and_says_what_the_page_shows(self):
        body = issue_body(payload(FAILED_WITH_OLD_DATA, FAILED_WITHOUT_DATA))
        self.assertIn("2 serier", body)
        self.assertEqual(body.count("HTTP Error 403"), 2)  # one line per error and what the page shows
        self.assertIn("(1 serie, siden viser data fra 2026-10-19): `eq_us`", body)
        self.assertIn("(1 serie, ingen data på siden): `eq_ca`", body)


if __name__ == "__main__":
    unittest.main()
