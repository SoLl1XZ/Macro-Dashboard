import math
import unittest
from datetime import date, timedelta

from transforms import (change_since, difference, drawdown, in_latest_prices, infer_frequency, is_stale,
                        peak_trough_periods, percentile_rank, ratio, recession_periods, shift_months,
                        spread, summarize, thin_before, weekly_move, year_over_year, z_score)


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


class RatioTest(unittest.TestCase):
    def test_only_dates_present_in_both_and_never_divides_by_zero(self):
        copper = [("2026-01-01", 9000.0), ("2026-02-01", 9900.0), ("2026-03-01", 9500.0)]
        gold = [("2026-01-01", 3000.0), ("2026-02-01", 0.0)]
        self.assertEqual(ratio(copper, gold), [("2026-01-01", 3.0)])


class InLatestPricesTest(unittest.TestCase):
    def test_older_prices_are_scaled_up_to_todays_price_level(self):
        oil = [("2000-01-01", 25.0), ("2026-01-01", 80.0)]
        cpi = [("2000-01-01", 170.0), ("2026-01-01", 340.0)]  # prices have doubled
        self.assertEqual(in_latest_prices(oil, cpi), [("2000-01-01", 50.0), ("2026-01-01", 80.0)])

    def test_months_without_an_index_value_are_left_out(self):
        self.assertEqual(in_latest_prices([("2026-02-01", 80.0)], [("2026-01-01", 340.0)]), [])
        self.assertEqual(in_latest_prices([("2026-02-01", 80.0)], []), [])


class DrawdownTest(unittest.TestCase):
    def test_percent_below_the_highest_value_so_far(self):
        obs = monthly(2026, [100.0, 120.0, 90.0, 130.0])
        self.assertEqual([value for _, value in drawdown(obs)], [0.0, 0.0, -25.0, 0.0])

    def test_empty_series_has_no_drawdown(self):
        self.assertEqual(drawdown([]), [])


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


class PercentileRankTest(unittest.TestCase):
    def test_new_high_ranks_near_the_top(self):
        obs = monthly(2016, [float(i) for i in range(1, 122)])  # 121 months, rising
        self.assertGreater(percentile_rank(obs), 99)

    def test_unchanged_value_ranks_in_the_middle(self):
        obs = monthly(2016, [2.0] * 121)
        self.assertEqual(percentile_rank(obs), 50.0)

    def test_series_younger_than_the_window_has_no_percentile(self):
        self.assertIsNone(percentile_rank(monthly(2023, [1.0] * 40)))

    def test_too_few_observations_has_no_percentile(self):
        yearly = [(f"{year}-01-01", float(year)) for year in range(2015, 2027)]
        self.assertIsNone(percentile_rank(yearly))


def daily(start: str, values: list[float]) -> list[tuple[str, float]]:
    """One observation per calendar day from `start`."""
    first = date.fromisoformat(start)
    return [((first + timedelta(days=i)).isoformat(), value) for i, value in enumerate(values)]


class ZScoreTest(unittest.TestCase):
    def test_new_high_is_well_above_the_mean(self):
        # Evenly spread 1..121: the top value is (121 - 61) / 34.9 ≈ 1.7 standard deviations up.
        self.assertAlmostEqual(z_score(monthly(2016, [float(i) for i in range(1, 122)])), 1.72, places=2)

    def test_flat_series_has_no_z_score(self):
        self.assertIsNone(z_score(monthly(2016, [2.0] * 121)))


class WeeklyMoveTest(unittest.TestCase):
    DAYS = 11 * 365

    # Values i + i % 2: a steady trend with wiggles, so every 7-day change is 6 (even i) or
    # 8 (odd i). The last day, i = 4014, is even. The typical change is the root mean square
    # of equally many 6s and 8s: sqrt((36 + 64) / 2) = sqrt(50) ≈ 7.07.

    def test_unusual_week_stands_out(self):
        values = [float(i + i % 2) for i in range(self.DAYS)]
        values[-1] += 20  # the last 7-day change becomes 6 + 20 = 26
        change, move = weekly_move(daily("2015-01-01", values), "diff")
        self.assertAlmostEqual(change, 26.0)
        self.assertGreater(move, 3)  # ≈ 26 / 7.07

    def test_ordinary_week_is_measured_against_the_typical_week(self):
        values = [float(i + i % 2) for i in range(self.DAYS)]
        _, move = weekly_move(daily("2015-01-01", values), "diff")
        self.assertAlmostEqual(move, 6 / math.sqrt(50), places=2)  # ≈ 0.85

    def test_weekly_move_needs_data_from_this_week(self):
        values = [float(i + i % 2) for i in range(self.DAYS)]
        obs = daily("2015-01-01", values)  # last day: 2025-12-28
        self.assertIsNotNone(summarize(obs, "diff", today="2026-01-02")["weekMoveZ"])  # 5 days old
        self.assertIsNone(summarize(obs, "diff", today="2026-01-20")["weekMoveZ"])  # 23 days old

    def test_monthly_series_has_no_weekly_move(self):
        self.assertIsNone(weekly_move(monthly(2015, [float(i) for i in range(140)]), "diff"))


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


class RecessionPeriodsTest(unittest.TestCase):
    def test_indicator_months_become_periods(self):
        indicator = monthly(2020, [0, 0, 1, 1, 0, 0, 1])  # Mar–Apr 2020, then Jul onwards
        self.assertEqual(recession_periods(indicator),
                         [("2020-03-01", "2020-05-01"), ("2020-07-01", "2020-08-01")])

    def test_peak_and_trough_quarters_follow_cepr_convention(self):
        # Peak 2019Q4, trough 2020Q2: recession is 2020Q1 through 2020Q2.
        self.assertEqual(peak_trough_periods([("2019-Q4", "2020-Q2")]), [("2020-01-01", "2020-07-01")])


class IsStaleTest(unittest.TestCase):
    def test_normal_publication_lag_is_not_stale(self):
        self.assertFalse(is_stale("2026-08-01", "M", today="2026-10-07"))  # August CPI in October
        self.assertFalse(is_stale("2026-10-05", "D", today="2026-10-07"))

    def test_too_old_is_stale(self):
        self.assertTrue(is_stale("2026-05-01", "M", today="2026-10-07"))
        self.assertTrue(is_stale("2026-07-23", "D", today="2026-10-07"))

    def test_unknown_frequency_is_never_stale(self):
        self.assertFalse(is_stale("2000-01-01", None, today="2026-10-07"))

    def test_a_series_can_allow_a_longer_delay(self):
        # BIS total credit: the first quarter arrives in September, the second in December.
        self.assertTrue(is_stale("2026-01-01", "Q", today="2026-10-07"))  # 279 days > 220
        self.assertFalse(is_stale("2026-01-01", "Q", today="2026-10-07", max_age_days=365))
        self.assertTrue(is_stale("2025-07-01", "Q", today="2026-10-07", max_age_days=365))


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
