import unittest

from ma_alert_bot.dominant_ema import (
    dominant_ema_report_changed,
    ratchet_stop,
    score_ema_candidate,
)
from ma_alert_bot.models import PositionSide
from tests.test_analysis import build_candles


class DominantEmaTests(unittest.TestCase):
    def test_clean_uptrend_scores_as_candidate(self) -> None:
        candidate = score_ema_candidate(
            build_candles([100 + index for index in range(80)]),
            "1H",
            20,
            PositionSide.LONG,
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertGreater(candidate.score, 70)
        self.assertGreater(candidate.proposed_stop, 100)

    def test_stop_ratchet_never_loosens(self) -> None:
        self.assertEqual(ratchet_stop(100, 98, PositionSide.LONG), 100)
        self.assertEqual(ratchet_stop(100, 104, PositionSide.LONG), 104)
        self.assertEqual(ratchet_stop(100, 103, PositionSide.SHORT), 100)
        self.assertEqual(ratchet_stop(100, 97, PositionSide.SHORT), 97)

    def test_report_is_suppressed_for_unchanged_ema_and_tiny_anchor_move(self) -> None:
        previous = (100.0, "1H", 20, 85.0)
        self.assertFalse(dominant_ema_report_changed(previous, "1H", 20, 100.05))
        self.assertTrue(dominant_ema_report_changed(previous, "1H", 20, 100.2))
        self.assertTrue(dominant_ema_report_changed(previous, "4H", 20, 100.0))


if __name__ == "__main__":
    unittest.main()
