import unittest

from ma_alert_bot.models import DominantEmaCandidate, ManualPosition, PositionSide
from ma_alert_bot.profit_protection import assess_profit_protection
from ma_alert_bot.notifications import build_profit_protection_message


def candidate(value: float = 110, atr: float = 4) -> DominantEmaCandidate:
    return DominantEmaCandidate("1H", 20, value, 85, 0.9, 20, 1, 3, atr, 108)


class ProfitProtectionTests(unittest.TestCase):
    def test_two_r_recommends_cumulative_sixty_five_percent(self) -> None:
        position = ManualPosition(
            "SOL-USDT-SWAP", PositionSide.LONG, 100, 95, position_value_usd=1100
        )
        result = assess_profit_protection(position, 110, 102, candidate(), 0)
        self.assertEqual(result.stage, 2)
        self.assertEqual(result.target_reduction_percent, 65)
        self.assertEqual(result.newly_recommended_reduction_percent, 65)
        self.assertAlmostEqual(result.projected_total_pnl or 0, 72)

    def test_first_stage_recommends_reducing_half(self) -> None:
        position = ManualPosition(
            "SOL-USDT-SWAP", PositionSide.LONG, 100, 95, position_value_usd=1050
        )
        result = assess_profit_protection(position, 105, 101, candidate(104), 0)
        self.assertEqual(result.stage, 1)
        self.assertEqual(result.target_reduction_percent, 50)
        self.assertEqual(result.newly_recommended_reduction_percent, 50)

    def test_previous_stage_prevents_duplicate_reduction(self) -> None:
        position = ManualPosition("BTC-USDT-SWAP", PositionSide.LONG, 100, 90)
        result = assess_profit_protection(position, 120, 105, candidate(119), 2)
        self.assertEqual(result.newly_recommended_reduction_percent, 0)

    def test_short_uses_inverse_direction(self) -> None:
        position = ManualPosition("ETH-USDT-SWAP", PositionSide.SHORT, 100, 105)
        result = assess_profit_protection(position, 90, 98, candidate(92), 0)
        self.assertEqual(result.r_multiple, 2)
        self.assertGreater(result.protected_pnl_per_unit, 0)

    def test_message_labels_estimated_dollar_result(self) -> None:
        position = ManualPosition(
            "SOL-USDT-SWAP", PositionSide.LONG, 100, 95, position_value_usd=1100
        )
        result = assess_profit_protection(position, 110, 102, candidate(), 0)
        message = build_profit_protection_message(position, 110, 102, result)
        self.assertIn("USD/USDC (estymacja)", message)
        self.assertNotIn("quote currency", message)


if __name__ == "__main__":
    unittest.main()
