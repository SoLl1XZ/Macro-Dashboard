import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fetch_data
from fetch_data import (apply_transforms, build_payload, fetch_source, load_previous_payload,
                        normalize_period, parse_number, reuse_previous_data, source_url,
                        write_data_js)
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

    def test_reference_lines_are_passed_to_the_page(self):
        panel = Panel("p", "us", "Test", "%", "Beskrivelse", (Series("x", "X", "fred", "X"),),
                      reference_lines=((2.0, "Mål 2 %"),))
        payload = build_payload([panel], {"x": [("2026-01-01", 2.5)]}, {}, today="2026-10-07")
        self.assertEqual(payload["panels"][0]["referenceLines"], [{"value": 2.0, "label": "Mål 2 %"}])

    def test_observations_before_display_start_are_dropped(self):
        panel = self.make_panel(Series("x", "X", "fred", "X"))
        observations = {"x": [("1999-06-01", 1.0), ("2000-01-01", 2.0)]}
        payload = build_payload([panel], observations, {}, today="2026-10-07")
        self.assertEqual(payload["panels"][0]["series"][0]["data"], [["2000-01-01", 2.0]])


class FetchEurostatTest(unittest.TestCase):
    """fetch_eurostat with a canned JSON-stat answer instead of the network."""

    def answer(self, sizes: dict, values: dict) -> str:
        times = {"2026-07": 0, "2026-08": 1}
        return json.dumps({
            "id": list(sizes), "size": list(sizes.values()), "value": values,
            "dimension": {"time": {"category": {"index": times}}},
        })

    def test_values_are_matched_to_their_periods(self):
        text = self.answer({"geo": 1, "time": 2}, {"0": 1.5, "1": 2.5})
        with mock.patch.object(fetch_data, "http_get", return_value=text):
            self.assertEqual(fetch_data.fetch_eurostat("ds?geo=DE"),
                             [("2026-07-01", 1.5), ("2026-08-01", 2.5)])

    def test_unknown_code_says_so(self):
        text = self.answer({"geo": 0, "time": 2}, {})
        with mock.patch.object(fetch_data, "http_get", return_value=text):
            with self.assertRaisesRegex(ValueError, "may not exist"):
                fetch_data.fetch_eurostat("ds?geo=EA")

    def test_unfixed_dimension_is_ambiguous(self):
        text = self.answer({"unit": 2, "time": 2}, {})
        with mock.patch.object(fetch_data, "http_get", return_value=text):
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                fetch_data.fetch_eurostat("ds?geo=DE")


class FetchBisTest(unittest.TestCase):
    """fetch_bis with canned SDMX-CSV answers instead of the network."""

    POLICY_RATE = "DATAFLOW,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nBIS:WS_CBPOL(1.0),D,US,2026-09-28,3.875\n"
    TOTAL_CREDIT = ("DATAFLOW,FREQ,BORROWERS_CTY,TIME_PERIOD,OBS_VALUE\n"
                    "BIS:WS_TC(2.0),Q,KR,2025-Q4,86.0\nBIS:WS_TC(2.0),Q,KR,2026-Q1,85.1\n")

    def test_plain_key_means_policy_rates(self):
        with mock.patch.object(fetch_data, "http_get", return_value=self.POLICY_RATE) as http_get:
            self.assertEqual(fetch_data.fetch_bis("D.US"), [("2026-09-28", 3.875)])
        self.assertIn("/WS_CBPOL/1.0/D.US?", http_get.call_args.args[0])

    def test_named_dataflow_uses_its_own_version(self):
        with mock.patch.object(fetch_data, "http_get", return_value=self.TOTAL_CREDIT) as http_get:
            observations = fetch_data.fetch_bis("WS_TC/Q.KR.H.A.M.770.A")
        self.assertEqual(observations, [("2025-10-01", 86.0), ("2026-01-01", 85.1)])
        self.assertIn("/WS_TC/2.0/Q.KR.H.A.M.770.A?", http_get.call_args.args[0])


class MofJgbTest(unittest.TestCase):
    """JGB yields from Japan's Ministry of Finance, parsed from saved sample files."""

    # Shaped like the real files: title line, header, "-" for missing, and (in the
    # current-month file) a note line at the end that is not data.
    HISTORICAL = ("Interest Rate,,,,(Unit : %)\n"
                  "Date,1Y,2Y,10Y,40Y\n"
                  "1999/12/30,0.1,0.2,1.7,-\n"
                  "2026/9/30,1.684,1.952,3.057,4.1\n")
    CURRENT = ("Interest Rate (October 2026),,,,(Unit : %)\n"
               "Date,1Y,2Y,10Y,40Y\n"
               "2026/9/30,1.7,1.95,3.06,4.1\n"
               "2026/10/1,1.668,1.939,3.092,4.125\n"
               '"  �If you cannot download the latest csv data, please clear the cache"\n')

    def test_parses_dates_and_skips_missing_values_and_notes(self):
        parsed = fetch_data.parse_mof_csv(self.HISTORICAL)
        self.assertEqual(set(parsed), {"1Y", "2Y", "10Y", "40Y"})
        self.assertEqual(parsed["10Y"], [("1999-12-30", 1.7), ("2026-09-30", 3.057)])
        self.assertEqual(parsed["40Y"], [("2026-09-30", 4.1)])  # "-" in 1999 is dropped
        self.assertEqual(len(fetch_data.parse_mof_csv(self.CURRENT)["2Y"]), 2)  # note line ignored

    def test_file_without_header_is_an_error(self):
        with self.assertRaises(ValueError):
            fetch_data.parse_mof_csv("<html>Maintenance</html>")

    def test_current_month_is_merged_on_top_of_history(self):
        with mock.patch.object(fetch_data, "http_get", side_effect=[self.HISTORICAL, self.CURRENT]) as http_get:
            batch = fetch_data.fetch_mof_jgb(["10Y", "7Y"])
        self.assertEqual(batch["10Y"], [("1999-12-30", 1.7), ("2026-09-30", 3.06), ("2026-10-01", 3.092)])
        self.assertNotIn("7Y", batch)  # unknown maturity: left out, so fetch_source reports it
        self.assertTrue(all(call.kwargs["errors"] == "replace" for call in http_get.call_args_list))


class FetchRecessionsTest(unittest.TestCase):
    def test_us_dates_fall_back_to_previous_run_when_fred_fails(self):
        def fred_down(series_id):
            raise TimeoutError("down")

        previous = {"recessions": {"us": [["2020-03-01", "2020-05-01"]]}}
        with mock.patch.object(fetch_data, "fetch_fred", fred_down), \
                contextlib.redirect_stdout(io.StringIO()):  # silence the expected FAIL line
            recessions = fetch_data.fetch_recessions(previous)
        self.assertEqual(recessions["us"], [["2020-03-01", "2020-05-01"]])
        self.assertIn(["2020-01-01", "2020-07-01"], recessions["euro_area"])


class SourceUrlTest(unittest.TestCase):
    def test_links_point_to_the_series_page(self):
        self.assertEqual(source_url(Series("x", "X", "fred", "DGS10")),
                         "https://fred.stlouisfed.org/series/DGS10")
        self.assertEqual(source_url(Series("x", "X", "ecb", "EXR/D.USD.EUR.SP00.A")),
                         "https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A")
        self.assertEqual(source_url(Series("x", "X", "statbank", "PRIS01?VAREGR=000000&ENHED=300")),
                         "https://www.statistikbanken.dk/PRIS01")

    def test_derived_series_have_no_link(self):
        self.assertIsNone(source_url(Series("x", "X", "derived", ("a", "b"), "spread")))


class ReusePreviousDataTest(unittest.TestCase):
    TODAY = "2026-10-07"

    def payload_for(self, observations: dict, errors: dict) -> dict:
        panel = Panel("p", "us", "Test", "%", "Beskrivelse",
                      (Series("ok", "OK", "fred", "A"), Series("flaky", "Flaky", "fred", "B")))
        return build_payload([panel], observations, errors, today=self.TODAY)

    def previous_run(self) -> dict:
        previous = self.payload_for({"ok": [("2026-08-01", 1.0)], "flaky": [("2026-08-01", 2.0)]}, {})
        previous["generatedAt"] = "2026-10-06T06:00:00+00:00"
        return previous

    def test_failed_series_gets_previous_data_with_its_fetch_time(self):
        payload = self.payload_for({"ok": [("2026-09-01", 1.5)]}, {"flaky": "TimeoutError: x"})
        reused = reuse_previous_data(payload, self.previous_run(), self.TODAY)
        ok, flaky = payload["panels"][0]["series"]
        self.assertEqual(reused, ["flaky"])
        self.assertEqual(flaky["data"], [["2026-08-01", 2.0]])
        self.assertEqual(flaky["error"], "TimeoutError: x")  # the failure stays visible
        self.assertEqual(flaky["fallbackFrom"], "2026-10-06T06:00:00+00:00")
        self.assertEqual(ok["data"], [["2026-09-01", 1.5]])  # fresh data is never overwritten
        self.assertIsNone(ok["fallbackFrom"])

    def test_fallback_keeps_the_original_fetch_time_across_runs(self):
        previous = self.previous_run()
        previous["panels"][0]["series"][1]["fallbackFrom"] = "2026-10-01T06:00:00+00:00"
        payload = self.payload_for({"ok": [("2026-09-01", 1.5)]}, {"flaky": "TimeoutError: x"})
        reuse_previous_data(payload, previous, self.TODAY)
        self.assertEqual(payload["panels"][0]["series"][1]["fallbackFrom"], "2026-10-01T06:00:00+00:00")

    def test_without_previous_data_the_series_stays_empty(self):
        payload = self.payload_for({"ok": [("2026-09-01", 1.5)]}, {"flaky": "TimeoutError: x"})
        self.assertEqual(reuse_previous_data(payload, None, self.TODAY), [])
        self.assertEqual(payload["panels"][0]["series"][1]["data"], [])


class DataFileTest(unittest.TestCase):
    def test_written_file_can_be_read_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.js"
            write_data_js({"generatedAt": "x", "panels": []}, path)
            self.assertEqual(load_previous_payload(path), {"generatedAt": "x", "panels": []})

    def test_missing_or_corrupt_file_gives_none(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.js"
            self.assertIsNone(load_previous_payload(path))
            path.write_text("window.MACRO_DATA = {broken", encoding="utf-8")
            self.assertIsNone(load_previous_payload(path))


if __name__ == "__main__":
    unittest.main()
