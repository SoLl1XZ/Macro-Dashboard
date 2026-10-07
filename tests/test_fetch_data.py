import unittest
from unittest import mock

import fetch_data
from fetch_data import apply_transforms, build_payload, fetch_source, normalize_period, parse_number
from indicators import Panel, Series


class NormalizePeriodTest(unittest.TestCase):
    def test_all_api_formats_become_iso_dates(self):
        cases = {
            "2026-10-05": "2026-10-05",  # FRED, ECB, BIS daily
            "2026M10D06": "2026-10-06",  # Statbank daily
            "2026-08": "2026-08-01",     # ECB, Eurostat, OECD monthly
            "2026M08": "2026-08-01",     # Statbank monthly
            "2026-M08": "2026-08-01",    # IMF monthly
            "2026-Q2": "2026-04-01",     # ECB quarterly
            "2026K4": "2026-10-01",      # Statbank quarterly (Danish "kvartal")
            "2026": "2026-01-01",        # IMF annual
        }
        for period, expected in cases.items():
            with self.subTest(period=period):
                self.assertEqual(normalize_period(period), expected)

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            normalize_period("week 5")


class ParseNumberTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_number("3.5"), 3.5)
        self.assertEqual(parse_number(2), 2.0)

    def test_missing_value_markers_become_none(self):
        for marker in ("", ".", "..", "NaN", None):
            with self.subTest(marker=marker):
                self.assertIsNone(parse_number(marker))


class FetchSourceTest(unittest.TestCase):
    def test_one_failing_query_does_not_stop_the_others(self):
        def fake_fetch(query: str):
            if query == "BAD":
                raise TimeoutError("timed out")
            return [("2026-01-01", 1.0)]

        with mock.patch.dict(fetch_data.SINGLE_FETCHERS, {"fred": fake_fetch}):
            batch, errors = fetch_source("fred", ["GOOD", "BAD"])
        self.assertEqual(batch["GOOD"], [("2026-01-01", 1.0)])
        self.assertIn("TimeoutError", errors["BAD"])
        self.assertNotIn("GOOD", errors)

    def test_empty_result_counts_as_error(self):
        with mock.patch.dict(fetch_data.SINGLE_FETCHERS, {"fred": lambda query: []}):
            _, errors = fetch_source("fred", ["EMPTY"])
        self.assertEqual(errors["EMPTY"], "No observations returned")

    def test_failing_batch_marks_every_query_as_failed(self):
        def broken_batch(queries):
            raise ConnectionError("API down")

        with mock.patch.dict(fetch_data.BATCH_FETCHERS, {"oecd_lt": broken_batch}):
            batch, errors = fetch_source("oecd_lt", ["DEU", "ITA"])
        self.assertEqual(batch, {})
        self.assertEqual(set(errors), {"DEU", "ITA"})


class ApplyTransformsTest(unittest.TestCase):
    def test_year_over_year_is_applied(self):
        cpi = Series("cpi", "CPI", "fred", "CPI", "yoy")
        index_values = [("2025-01-01", 100.0), ("2026-01-01", 103.0)]
        processed, errors = apply_transforms([cpi], {"cpi": index_values}, {})
        self.assertAlmostEqual(processed["cpi"][0][1], 3.0)
        self.assertEqual(errors, {})

    def test_spread_with_failed_input_becomes_an_error(self):
        it = Series("it", "Italien", "oecd_lt", "ITA")
        de = Series("de", "Tyskland", "oecd_lt", "DEU")
        it_de = Series("it_de", "IT − DE", "derived", ("it", "de"), "spread")
        processed, errors = apply_transforms(
            [it, de, it_de], {"it": [("2026-01-01", 4.0)]}, {"de": "TimeoutError: x"})
        self.assertIn("it", processed)
        self.assertEqual(errors["it_de"], "Missing input: de")
        self.assertEqual(errors["de"], "TimeoutError: x")


class BuildPayloadTest(unittest.TestCase):
    def make_panel(self, *series: Series) -> Panel:
        return Panel("p", "us", "Test", "%", "Beskrivelse", series)

    def test_failed_series_has_error_and_no_data(self):
        panel = self.make_panel(Series("ok", "OK", "fred", "A"), Series("bad", "Bad", "fred", "B"))
        payload = build_payload([panel], {"ok": [("2026-01-01", 1.0)]},
                                {"bad": "TimeoutError: x"}, today="2026-10-07")
        ok, bad = payload["panels"][0]["series"]
        self.assertIsNone(ok["error"])
        self.assertEqual(ok["data"], [["2026-01-01", 1.0]])
        self.assertEqual(ok["summary"]["last"], 1.0)
        self.assertEqual(bad["error"], "TimeoutError: x")
        self.assertEqual(bad["data"], [])
        self.assertIsNone(bad["summary"])

    def test_imf_series_marks_current_year_as_forecast(self):
        panel = self.make_panel(Series("gdp", "BNP", "imf_weo", "NGDP_RPCH/WEOWORLD"))
        payload = build_payload([panel], {"gdp": [("2026-01-01", 3.1)]}, {}, today="2026-10-07")
        self.assertEqual(payload["panels"][0]["series"][0]["forecastFrom"], "2026-01-01")

    def test_observations_before_display_start_are_dropped(self):
        panel = self.make_panel(Series("x", "X", "fred", "X"))
        observations = {"x": [("1999-06-01", 1.0), ("2000-01-01", 2.0)]}
        payload = build_payload([panel], observations, {}, today="2026-10-07")
        self.assertEqual(payload["panels"][0]["series"][0]["data"], [["2000-01-01", 2.0]])


if __name__ == "__main__":
    unittest.main()
