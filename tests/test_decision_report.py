import unittest

from ma_alert_bot.decision_report import build_decision_report
from ma_alert_bot.positions import PositionDirection, PositionSnapshot


class DecisionReportTests(unittest.TestCase):
    def test_report_always_contains_long_short_and_neutral_scenarios(self) -> None:
        report = build_decision_report(
            instrument_id="EXAMPLE-USDT-SWAP",
            current_price=102.0,
            moving_average_levels={20: 101.0, 50: 99.0, 120: 103.0, 200: 95.0},
            position=None,
        )

        self.assertIn("LONG", report)
        self.assertIn("SHORT", report)
        self.assertIn("NEUTRAL", report)
        self.assertIn("brak skonfigurowanej", report)

    def test_losing_long_is_not_automatically_invalidated(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.LONG,
            entry_price=100.0,
            stop_loss_price=90.0,
            thesis_support_price=95.0,
        )

        report = build_decision_report(
            instrument_id=position.instrument_id,
            current_price=97.0,
            moving_average_levels={20: 96.0},
            position=position,
        )

        self.assertIn("TEZA JESZCZE AKTYWNA, ALE NIE DOKŁADAJ", report)
        self.assertNotIn("STOP NARUSZONY", report)

    def test_short_stop_is_breached_when_price_rises_through_it(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.SHORT,
            entry_price=100.0,
            stop_loss_price=105.0,
        )

        report = build_decision_report(
            instrument_id=position.instrument_id,
            current_price=106.0,
            moving_average_levels={20: 104.0},
            position=position,
        )

        self.assertIn("STOP NARUSZONY", report)

    def test_short_target_is_reached_when_price_falls_to_it(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.SHORT,
            entry_price=100.0,
            target_price=90.0,
        )

        report = build_decision_report(
            instrument_id=position.instrument_id,
            current_price=89.0,
            moving_average_levels={20: 92.0},
            position=position,
        )

        self.assertIn("CEL OSIĄGNIĘTY", report)

    def test_open_candle_wick_does_not_invalidate_h4_thesis(self) -> None:
        position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.LONG,
            entry_price=100.0,
            thesis_support_price=95.0,
        )

        report = build_decision_report(
            instrument_id=position.instrument_id,
            current_price=94.0,
            latest_confirmed_price=97.0,
            moving_average_levels={20: 96.0},
            position=position,
        )

        self.assertIn("TEZA JESZCZE AKTYWNA", report)
        self.assertNotIn("RUCH ZDYSKWALIFIKOWANY", report)


if __name__ == "__main__":
    unittest.main()
