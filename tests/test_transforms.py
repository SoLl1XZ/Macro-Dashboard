import unittest

from transforms import (change_since, difference, infer_frequency, shift_months, spread,
                        summarize, thin_before, year_over_year)


def monthly(start_year: int, values: list[float]) -> list[tuple[str, float]]:
    """Monthly observations starting in January of start_year."""
    return [(shift_months(f"{start_year}-01-01", i), value) for i, value in enumerate(values)]


class ShiftMonthsTest(unittest.TestCase):
    def test_moves_back_across_year_boundary(self):
        self.assertEqual(shift_months("2026-01-15", -1), "2025-12-15")

    def test_clamps_day_to_end_of_shorter_month(self):
        self.assertEqual(shift_months("2026-03-31", -1), "2026-02-28")

    def test_handles_leap_day(self):
        self.assertEqual(shift_months("2024-02-29", -12), "2023-02-28")


class YearOverYearTest(unittest.TestCase):
    def test_percent_change_versus_same_month_last_year(self):
        result = year_over_year(monthly(2025, [100.0] * 12 + [110.0]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "2026-01-01")
        self.assertAlmostEqual(result[0][1], 10.0)

    def test_skips_months_without_a_value_one_year_earlier(self):
        self.assertEqual(year_over_year(monthly(2025, [100.0] * 12)), [])

    def test_skips_zero_base_instead_of_dividing_by_zero(self):
        self.assertEqual(year_over_year(monthly(2025, [0.0] + [1.0] * 12)), [])


class DifferenceTest(unittest.TestCase):
    def test_change_versus_previous_observation(self):
        obs = [("2026-01-01", 100.0), ("2026-02-01", 103.0), ("2026-03-01", 101.0)]
        self.assertEqual(difference(obs), [("2026-02-01", 3.0), ("2026-03-01", -2.0)])


class SpreadTest(unittest.TestCase):
    def test_only_dates_present_in_both_series(self):
        a = [("2026-01-01", 4.0), ("2026-02-01", 4.5), ("2026-03-01", 5.0)]
        b = [("2026-01-01", 3.0), ("2026-03-01", 3.5)]
        self.assertEqual(spread(a, b), [("2026-01-01", 1.0), ("2026-03-01", 1.5)])


class ChangeSinceTest(unittest.TestCase):
    def test_difference_over_one_month_and_one_year(self):
        obs = monthly(2025, [float(i) for i in range(1, 14)])  # 1, 2, ..., 13
        self.assertEqual(change_since(obs, 1, "diff"), 1.0)
        self.assertEqual(change_since(obs, 12, "diff"), 12.0)

    def test_percent_change(self):
        obs = monthly(2025, [100.0] * 12 + [105.0])
        self.assertAlmostEqual(change_since(obs, 12, "pct"), 5.0)

    def test_quarterly_series_has_no_one_month_change(self):
        obs = [("2025-10-01", 1.0), ("2026-01-01", 2.0), ("2026-04-01", 3.0)]
        self.assertIsNone(change_since(obs, 1, "diff"))

    def test_daily_series_uses_closest_earlier_day(self):
        # 2026-09-05 is a Saturday, so the Friday before is the reference.
        obs = [("2026-09-04", 1.0), ("2026-09-07", 1.5), ("2026-10-05", 2.0)]
        self.assertEqual(change_since(obs, 1, "diff"), 1.0)


class SummarizeTest(unittest.TestCase):
    def test_ignores_future_forecasts(self):
        obs = [("2025-01-01", 3.0), ("2026-01-01", 3.2), ("2027-01-01", 3.5)]
        summary = summarize(obs, "diff", today="2026-10-07")
        self.assertEqual(summary["lastDate"], "2026-01-01")
        self.assertEqual(summary["last"], 3.2)
        self.assertAlmostEqual(summary["change1y"], 0.2)
        self.assertIsNone(summary["change1m"])

    def test_empty_series_has_no_summary(self):
        self.assertIsNone(summarize([], "diff", today="2026-10-07"))


class InferFrequencyTest(unittest.TestCase):
    def test_recognizes_each_frequency(self):
        business_days = [("2026-09-28", 1.0), ("2026-09-29", 1.0), ("2026-09-30", 1.0),
                         ("2026-10-01", 1.0), ("2026-10-02", 1.0), ("2026-10-05", 1.0)]
        cases = {
            "D": business_days,
            "W": [("2026-09-05", 1.0), ("2026-09-12", 1.0), ("2026-09-19", 1.0)],
            "M": monthly(2026, [1.0, 2.0, 3.0]),
            "Q": [("2026-01-01", 1.0), ("2026-04-01", 1.0), ("2026-07-01", 1.0)],
            "A": [("2024-01-01", 1.0), ("2025-01-01", 1.0), ("2026-01-01", 1.0)],
        }
        for expected, obs in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(infer_frequency(obs), expected)

    def test_single_observation_is_unknown(self):
        self.assertIsNone(infer_frequency([("2026-01-01", 1.0)]))


class ThinBeforeTest(unittest.TestCase):
    def test_keeps_last_day_per_week_before_cutoff_and_all_days_after(self):
        week_1 = [(f"2026-01-0{day}", float(day)) for day in range(5, 10)]  # Mon 5 .. Fri 9
        week_2 = [(f"2026-01-{day}", float(day)) for day in range(12, 17)]  # Mon 12 .. Fri 16
        result = thin_before(week_1 + week_2, cutoff="2026-01-12")
        self.assertEqual(result, [("2026-01-09", 9.0)] + week_2)

    def test_monthly_series_is_unchanged(self):
        obs = monthly(2020, [1.0, 2.0, 3.0])
        self.assertEqual(thin_before(obs, cutoff="2026-01-01"), obs)


if __name__ == "__main__":
    unittest.main()
