import unittest

from ma_alert_bot.analysis import (
    calculate_simple_moving_average,
    detect_tests_on_latest_candle,
    resolve_test_outcome,
)
from ma_alert_bot.models import ApproachSide, Candle, TestOutcome


FOUR_HOURS_IN_MILLISECONDS = 4 * 60 * 60 * 1000


def build_candles(
    closing_prices: list[float],
    latest_lowest_price: float | None = None,
    latest_highest_price: float | None = None,
    latest_is_confirmed: bool = True,
) -> list[Candle]:
    candles: list[Candle] = []
    for candle_index, closing_price in enumerate(closing_prices):
        is_latest_candle = candle_index == len(closing_prices) - 1
        candles.append(
            Candle(
                opening_timestamp_ms=candle_index * FOUR_HOURS_IN_MILLISECONDS,
                opening_price=closing_price,
                highest_price=(
                    latest_highest_price
                    if is_latest_candle and latest_highest_price is not None
                    else closing_price
                ),
                lowest_price=(
                    latest_lowest_price
                    if is_latest_candle and latest_lowest_price is not None
                    else closing_price
                ),
                closing_price=closing_price,
                is_confirmed=(latest_is_confirmed if is_latest_candle else True),
            )
        )
    return candles


class SimpleMovingAverageTests(unittest.TestCase):
    def test_calculates_average_ending_at_requested_candle(self) -> None:
        candles = build_candles([10.0, 20.0, 30.0, 40.0])

        result = calculate_simple_moving_average(
            candles,
            candle_index=3,
            moving_average_period=3,
        )

        self.assertEqual(result, 30.0)

    def test_returns_none_when_history_is_too_short(self) -> None:
        candles = build_candles([10.0, 20.0])

        result = calculate_simple_moving_average(
            candles,
            candle_index=1,
            moving_average_period=3,
        )

        self.assertIsNone(result)

    def test_detects_touch_only_on_unconfirmed_latest_candle(self) -> None:
        confirmed_closing_prices = [100.0] * 200
        candles = build_candles(
            confirmed_closing_prices + [101.0],
            latest_lowest_price=99.0,
            latest_highest_price=102.0,
            latest_is_confirmed=False,
        )

        detected_tests = detect_tests_on_latest_candle("BTC-USDT-SWAP", candles)

        detected_periods = {
            moving_average_test.moving_average_period
            for moving_average_test in detected_tests
        }
        self.assertEqual(detected_periods, {20, 50, 120, 200})

    def test_does_not_detect_touch_after_candle_is_confirmed(self) -> None:
        candles = build_candles(
            [100.0] * 201,
            latest_lowest_price=99.0,
            latest_highest_price=101.0,
            latest_is_confirmed=True,
        )

        detected_tests = detect_tests_on_latest_candle("BTC-USDT-SWAP", candles)

        self.assertEqual(detected_tests, [])


class TestResolutionTests(unittest.TestCase):
    def test_support_is_defended_when_candle_closes_above_average(self) -> None:
        outcome = resolve_test_outcome(ApproachSide.ABOVE, 101.0, 100.0)
        self.assertEqual(outcome, TestOutcome.SUPPORT_DEFENDED)

    def test_support_is_lost_when_candle_closes_below_average(self) -> None:
        outcome = resolve_test_outcome(ApproachSide.ABOVE, 99.0, 100.0)
        self.assertEqual(outcome, TestOutcome.SUPPORT_LOST)

    def test_resistance_rejects_price_when_candle_closes_below_average(self) -> None:
        outcome = resolve_test_outcome(ApproachSide.BELOW, 99.0, 100.0)
        self.assertEqual(outcome, TestOutcome.RESISTANCE_REJECTED)

    def test_resistance_is_reclaimed_when_candle_closes_above_average(self) -> None:
        outcome = resolve_test_outcome(ApproachSide.BELOW, 101.0, 100.0)
        self.assertEqual(outcome, TestOutcome.RESISTANCE_RECLAIMED)


if __name__ == "__main__":
    unittest.main()

