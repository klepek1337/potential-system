import unittest

from ma_alert_bot.position_risk import PositionRiskType, evaluate_position_risks
from ma_alert_bot.positions import PositionDirection, PositionSnapshot


class PositionRiskTests(unittest.TestCase):
    def test_long_stop_warning_uses_distance_in_adverse_direction(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.LONG,
            entry_price=100.0,
            stop_loss_price=99.0,
        )

        alerts = evaluate_position_risks(
            current_price=100.0,
            position=position,
            stop_warning_distance_percent=1.1,
            liquidation_warning_distance_percent=5.0,
        )

        self.assertIn(PositionRiskType.STOP_NEAR, alerts)
        self.assertNotIn(PositionRiskType.STOP_BREACHED, alerts)

    def test_short_stop_is_breached_after_price_rises_above_it(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.SHORT,
            entry_price=100.0,
            stop_loss_price=105.0,
        )

        alerts = evaluate_position_risks(
            current_price=106.0,
            position=position,
            stop_warning_distance_percent=1.0,
            liquidation_warning_distance_percent=5.0,
        )

        self.assertIn(PositionRiskType.STOP_BREACHED, alerts)

    def test_short_liquidation_warning_uses_level_above_price(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.SHORT,
            entry_price=100.0,
            liquidation_price=104.0,
        )

        alerts = evaluate_position_risks(
            current_price=100.0,
            position=position,
            stop_warning_distance_percent=1.0,
            liquidation_warning_distance_percent=5.0,
        )

        self.assertIn(PositionRiskType.LIQUIDATION_NEAR, alerts)


if __name__ == "__main__":
    unittest.main()
