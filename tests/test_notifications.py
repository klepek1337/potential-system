import unittest

from ma_alert_bot.notifications import (
    build_current_ema_levels_message,
    build_current_levels_message,
    build_minute_sma_tilt_message,
    build_program_started_message,
)
from ma_alert_bot.models import (
    ManualPosition,
    MinuteSmaTiltAssessment,
    PositionSide,
    TiltDirection,
)


class StartupNotificationTests(unittest.TestCase):
    def test_started_message_contains_configuration(self) -> None:
        message = build_program_started_message(
            instrument_ids=("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
            touch_margin_ratio=0.001,
            minute_sma_tilt_enabled=True,
        )

        self.assertIn("Cryptostrata v1.5.0 uruchomiona", message)
        self.assertIn("Najnowsza aktualizacja: SMA Tilt 1m", message)
        self.assertIn("Zmiany w v1.5.0", message)
        self.assertIn("kierunek SMA 20", message)
        self.assertIn("SMA/EMA", message)
        self.assertIn("EMA: 20, 50, 120, 200", message)
        self.assertIn("0.1%", message)
        self.assertIn("BTC-USDT-SWAP, ETH-USDT-SWAP", message)
        self.assertIn("Tilt SMA 1m: ON", message)

    def test_level_message_contains_price_and_all_averages(self) -> None:
        message = build_current_levels_message(
            instrument_id="BTC-USDT-SWAP",
            current_price=102.0,
            moving_average_levels={20: 100.0, 50: 101.0, 120: 103.0, 200: 104.0},
        )

        self.assertIn("Cena: 102", message)
        self.assertIn("SMA 20: 100", message)
        self.assertIn("SMA 50: 101", message)
        self.assertIn("SMA 120: 103", message)
        self.assertIn("SMA 200: 104", message)
        self.assertIn("nad", message)
        self.assertIn("pod", message)

    def test_ema_message_is_separate_from_sma_message(self) -> None:
        message = build_current_ema_levels_message(
            "SOL-USDT-SWAP", 105.0, {20: 103.0, 50: 100.0}
        )
        self.assertIn("EMA 20", message)
        self.assertNotIn("SMA 20", message)

    def test_tilt_message_marks_move_against_long_position(self) -> None:
        message = build_minute_sma_tilt_message(
            "BTC-USDT-SWAP",
            MinuteSmaTiltAssessment(
                period=20,
                lookback_minutes=5,
                current_price=78_700,
                sma_value=78_750,
                previous_tilt_atr=0.3,
                current_tilt_atr=-0.4,
                tilt_change_atr=-0.7,
                direction=TiltDirection.FALLING,
                candle_timestamp_ms=1_000,
            ),
            ManualPosition("BTC-USDT-SWAP", PositionSide.LONG, 78_856, 76_415),
        )
        self.assertIn("PRZECIW pozycji", message)
        self.assertIn("nie samodzielny sygnał", message)


if __name__ == "__main__":
    unittest.main()
