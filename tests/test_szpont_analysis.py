import unittest
from types import SimpleNamespace

from ma_alert_bot.models import Candle
from ma_alert_bot.szpont_analysis import (
    MomentumState,
    SynchronizationState,
    assess_timeframe,
    classify_momentum_state,
    determine_synchronization_state,
)


ONE_HOUR_IN_MILLISECONDS = 60 * 60 * 1000
TEST_AVERAGE_TRUE_RANGE = 10.0
TEST_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE = 0.001


def build_trending_candles(
    candle_count: int,
    latest_unconfirmed_close: float | None = None,
) -> list[Candle]:
    candles = [
        Candle(
            opening_timestamp_ms=candle_index * ONE_HOUR_IN_MILLISECONDS,
            opening_price=100.0 + candle_index,
            highest_price=101.0 + candle_index,
            lowest_price=99.0 + candle_index,
            closing_price=100.0 + candle_index,
            is_confirmed=True,
        )
        for candle_index in range(candle_count)
    ]
    if latest_unconfirmed_close is not None:
        candles.append(
            Candle(
                opening_timestamp_ms=candle_count * ONE_HOUR_IN_MILLISECONDS,
                opening_price=candles[-1].closing_price,
                highest_price=latest_unconfirmed_close,
                lowest_price=candles[-1].closing_price,
                closing_price=latest_unconfirmed_close,
                is_confirmed=False,
            )
        )
    return candles


def momentum(momentum_state: MomentumState) -> SimpleNamespace:
    return SimpleNamespace(momentum_state=momentum_state)


class MomentumClassificationTests(unittest.TestCase):
    def test_positive_but_falling_histogram_is_bullish_deceleration(self) -> None:
        state, normalized_slope = classify_momentum_state(
            current_histogram=0.10,
            previous_histogram=0.20,
            average_true_range=TEST_AVERAGE_TRUE_RANGE,
            minimum_normalized_histogram_slope=(
                TEST_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE
            ),
        )

        self.assertEqual(state, MomentumState.BULLISH_DECELERATION)
        self.assertLess(normalized_slope, 0)

    def test_negative_but_rising_histogram_is_bearish_recovery(self) -> None:
        state, normalized_slope = classify_momentum_state(
            current_histogram=-0.10,
            previous_histogram=-0.20,
            average_true_range=TEST_AVERAGE_TRUE_RANGE,
            minimum_normalized_histogram_slope=(
                TEST_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE
            ),
        )

        self.assertEqual(state, MomentumState.BEARISH_RECOVERY)
        self.assertGreater(normalized_slope, 0)

    def test_open_candle_does_not_change_official_assessment(self) -> None:
        confirmed_candles = build_trending_candles(220)
        candles_with_large_open_move = build_trending_candles(
            220, latest_unconfirmed_close=1_000.0
        )

        confirmed_assessment = assess_timeframe("1H", confirmed_candles)
        open_move_assessment = assess_timeframe("1H", candles_with_large_open_move)

        self.assertEqual(
            confirmed_assessment.closing_price, open_move_assessment.closing_price
        )
        self.assertEqual(
            confirmed_assessment.histogram, open_move_assessment.histogram
        )


class SynchronizationTests(unittest.TestCase):
    def test_h4_deceleration_vetoes_bullish_one_and_two_hour_states(self) -> None:
        state, explanation = determine_synchronization_state(
            {
                "1H": momentum(MomentumState.BULLISH_CROSS),
                "2H": momentum(MomentumState.BEARISH_RECOVERY),
                "4H": momentum(MomentumState.BULLISH_DECELERATION),
                "1D": momentum(MomentumState.BULLISH_EXPANSION),
            }
        )

        self.assertEqual(state, SynchronizationState.BULLISH_H4_VETO)
        self.assertIn("H4", explanation)

    def test_matching_lower_timeframes_with_supportive_daily_are_confirmed(self) -> None:
        state, _ = determine_synchronization_state(
            {
                "1H": momentum(MomentumState.BULLISH_CROSS),
                "2H": momentum(MomentumState.BULLISH_EXPANSION),
                "4H": momentum(MomentumState.BEARISH_RECOVERY),
                "1D": momentum(MomentumState.BEARISH_RECOVERY),
            }
        )

        self.assertEqual(
            state, SynchronizationState.CONFIRMED_BULLISH_EXPANSION
        )


if __name__ == "__main__":
    unittest.main()
