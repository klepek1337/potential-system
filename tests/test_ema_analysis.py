import unittest

from ma_alert_bot.ema_analysis import (
    calculate_exponential_moving_average_series,
    calculate_latest_ema_levels,
)
from tests.test_analysis import build_candles


class ExponentialMovingAverageTests(unittest.TestCase):
    def test_seeds_with_sma_then_applies_multiplier(self) -> None:
        candles = build_candles([1, 2, 3, 4])
        series = calculate_exponential_moving_average_series(candles, 3)
        self.assertEqual(series[:2], [None, None])
        self.assertEqual(series[2], 2.0)
        self.assertEqual(series[3], 3.0)

    def test_calculates_configured_latest_levels(self) -> None:
        levels = calculate_latest_ema_levels(build_candles([10] * 10), (3, 5))
        self.assertEqual(levels, {3: 10.0, 5: 10.0})


if __name__ == "__main__":
    unittest.main()
