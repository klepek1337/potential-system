import unittest

from ma_alert_bot.minute_sma_tilt import assess_minute_sma_tilt, should_notify_tilt
from ma_alert_bot.models import Candle, TiltDirection


def candles_from_closes(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            opening_timestamp_ms=index * 60_000,
            opening_price=close,
            highest_price=close + 0.5,
            lowest_price=close - 0.5,
            closing_price=close,
            is_confirmed=True,
        )
        for index, close in enumerate(closes)
    ]


class MinuteSmaTiltTests(unittest.TestCase):
    def test_detects_strong_upward_change(self) -> None:
        assessment = assess_minute_sma_tilt(
            candles_from_closes([100.0] * 20 + [101, 102, 103, 104, 105, 106]),
            period=5,
            lookback_minutes=3,
            strong_tilt_threshold_atr=0.25,
            change_threshold_atr=0.5,
        )
        self.assertIsNotNone(assessment)
        assert assessment is not None
        self.assertEqual(assessment.direction, TiltDirection.RISING)
        self.assertGreater(assessment.tilt_change_atr, 0.5)

    def test_ignores_flat_noise(self) -> None:
        assessment = assess_minute_sma_tilt(
            candles_from_closes([100.0, 100.02, 99.98] * 10),
            period=20,
            lookback_minutes=5,
            strong_tilt_threshold_atr=0.25,
            change_threshold_atr=0.5,
        )
        self.assertIsNone(assessment)

    def test_cooldown_suppresses_repeated_alert(self) -> None:
        assessment = assess_minute_sma_tilt(
            candles_from_closes([100.0] * 20 + [101, 102, 103, 104, 105, 106]),
            period=5,
            lookback_minutes=3,
            strong_tilt_threshold_atr=0.25,
            change_threshold_atr=0.5,
        )
        assert assessment is not None
        previous = (
            assessment.candle_timestamp_ms - 60_000,
            assessment.candle_timestamp_ms - 60_000,
            TiltDirection.RISING.value,
            assessment.current_tilt_atr - 1.0,
        )
        self.assertFalse(should_notify_tilt(assessment, previous, 600, 0.5))


if __name__ == "__main__":
    unittest.main()
