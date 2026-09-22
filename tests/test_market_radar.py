import unittest
from types import SimpleNamespace

from ma_alert_bot.market_radar import (
    MarketRadarCandidate,
    build_market_radar_report,
    notification_state_for_score,
    select_eligible_instruments,
    should_notify_score,
)
from ma_alert_bot.models import Candle
from ma_alert_bot.okx_client import PerpetualInstrument, PerpetualTicker
from ma_alert_bot.setup_scoring import (
    HistogramDirection,
    ScoreBreakdown,
    SetupDirection,
    SetupGrade,
    SetupScore,
    classify_grade,
    qualified_histogram_direction,
    score_setup,
    synchronization_points,
)

CURRENT_TIMESTAMP_MS = 2_000_000_000_000
ONE_DAY_MS = 86_400_000


def assessment(
    slope: float,
    levels: dict[int, float] | None = None,
    macd_line: float | None = None,
    signal_line: float | None = None,
) -> SimpleNamespace:
    default_line_value = -1.0 if slope > 0 else 1.0
    return SimpleNamespace(
        normalized_histogram_slope=slope,
        macd_line=macd_line if macd_line is not None else default_line_value,
        signal_line=signal_line if signal_line is not None else default_line_value,
        moving_average_levels=levels or {20: 100.0, 50: 100.0, 100: 100.0, 200: 100.0},
    )


def flat_candles(count: int = 205) -> tuple[Candle, ...]:
    return tuple(
        Candle(index, 100.0, 100.2, 99.8, 100.0, True)
        for index in range(count)
    )


def setup_score(direction: SetupDirection, grade: SetupGrade) -> SetupScore:
    points_by_grade = {
        SetupGrade.NONE: 0,
        SetupGrade.WEAK: 4,
        SetupGrade.VALID: 9,
        SetupGrade.GOOD: 14,
        SetupGrade.STRONG: 19,
        SetupGrade.FULL_SYNC: 24,
    }
    return SetupScore(
        direction=direction,
        grade=grade,
        breakdown=ScoreBreakdown(synchronization=points_by_grade[grade]),
        histogram_directions={
            timeframe: HistogramDirection.UP for timeframe in ("1H", "2H", "4H", "1D")
        },
        synchronized_timeframes=("1H", "2H"),
        nearest_sma_period=20,
        nearest_sma_distance_percent=0.1,
        nearby_sma_periods=(20,),
        crossed_sma_periods=(),
        price_broken_sma_periods=(),
    )


class SetupScoringTests(unittest.TestCase):
    def test_negative_macd_and_signal_with_rising_histogram_qualifies_long(self) -> None:
        direction = qualified_histogram_direction(
            assessment(0.01, macd_line=-0.0004, signal_line=-0.0004),
            minimum_normalized_histogram_slope=0.001,
        )

        self.assertEqual(direction, HistogramDirection.UP)

    def test_positive_macd_and_signal_veto_rising_histogram_long(self) -> None:
        direction = qualified_histogram_direction(
            assessment(0.01, macd_line=0.0004, signal_line=0.0003),
            minimum_normalized_histogram_slope=0.001,
        )

        self.assertEqual(direction, HistogramDirection.FLAT)

    def test_positive_macd_and_signal_with_falling_histogram_qualifies_short(self) -> None:
        direction = qualified_histogram_direction(
            assessment(-0.01, macd_line=0.0004, signal_line=0.0010),
            minimum_normalized_histogram_slope=0.001,
        )

        self.assertEqual(direction, HistogramDirection.DOWN)

    def test_negative_macd_and_signal_veto_falling_histogram_short(self) -> None:
        direction = qualified_histogram_direction(
            assessment(-0.01, macd_line=-0.0004, signal_line=-0.0003),
            minimum_normalized_histogram_slope=0.001,
        )

        self.assertEqual(direction, HistogramDirection.FLAT)

    def test_synchronization_requires_at_least_two_timeframes(self) -> None:
        self.assertEqual(synchronization_points(("1H",)), 0)
        self.assertEqual(synchronization_points(("1H", "2H")), 5)
        self.assertEqual(synchronization_points(("1H", "2H", "4H")), 9)
        self.assertEqual(synchronization_points(("1H", "2H", "4H", "1D")), 12)

    def test_long_and_short_are_scored_independently(self) -> None:
        score = score_setup(
            {
                "1H": assessment(-0.01),
                "2H": assessment(-0.01),
                "4H": assessment(-0.01),
                "1D": assessment(0.01),
            },
            flat_candles(),
            current_price=100.0,
            minimum_normalized_histogram_slope=0.001,
        )
        self.assertEqual(score.direction, SetupDirection.SHORT)
        self.assertEqual(score.synchronized_timeframes, ("1H", "2H", "4H"))
        self.assertGreaterEqual(score.total, 9)

    def test_extreme_one_hour_sma_proximity_gets_three_points(self) -> None:
        score = score_setup(
            {
                timeframe: assessment(0.01)
                for timeframe in ("1H", "2H", "4H", "1D")
            },
            flat_candles(),
            current_price=100.05,
            minimum_normalized_histogram_slope=0.001,
        )
        self.assertEqual(score.breakdown.sma_proximity, 3)
        self.assertEqual(score.breakdown.sma_cluster, 3)
        self.assertEqual(score.grade, SetupGrade.STRONG)

    def test_extreme_proximity_requires_one_hour_synchronization(self) -> None:
        score = score_setup(
            {
                "1H": assessment(-0.01),
                "2H": assessment(0.01),
                "4H": assessment(0.01),
                "1D": assessment(0.01),
            },
            flat_candles(),
            current_price=100.05,
            minimum_normalized_histogram_slope=0.001,
        )
        self.assertEqual(score.direction, SetupDirection.LONG)
        self.assertEqual(score.breakdown.sma_proximity, 0)

    def test_maximum_breakdown_is_twenty_eight_points(self) -> None:
        breakdown = ScoreBreakdown(12, 3, 3, 3, 3, 2, 2)
        self.assertEqual(breakdown.total, 28)

    def test_strong_requires_structural_confirmation(self) -> None:
        self.assertEqual(classify_grade(22, False), SetupGrade.GOOD)
        self.assertEqual(classify_grade(22, True), SetupGrade.STRONG)
        self.assertEqual(classify_grade(24, True), SetupGrade.FULL_SYNC)


class MarketRadarLiquidityTests(unittest.TestCase):
    def test_filters_age_notional_and_spread(self) -> None:
        instruments = (
            PerpetualInstrument("GOOD-USDT-SWAP", CURRENT_TIMESTAMP_MS - 30 * ONE_DAY_MS),
            PerpetualInstrument("NEW-USDT-SWAP", CURRENT_TIMESTAMP_MS - ONE_DAY_MS),
            PerpetualInstrument("THIN-USDT-SWAP", CURRENT_TIMESTAMP_MS - 30 * ONE_DAY_MS),
        )
        tickers = {
            "GOOD-USDT-SWAP": PerpetualTicker("GOOD-USDT-SWAP", 100.0, 99.9, 100.1, 100_000.0),
            "NEW-USDT-SWAP": PerpetualTicker("NEW-USDT-SWAP", 100.0, 99.9, 100.1, 100_000.0),
            "THIN-USDT-SWAP": PerpetualTicker("THIN-USDT-SWAP", 100.0, 99.0, 101.0, 1_000.0),
        }
        eligible = select_eligible_instruments(
            instruments,
            tickers,
            CURRENT_TIMESTAMP_MS,
            minimum_listing_age_days=7,
            minimum_quote_notional_24h=5_000_000.0,
            maximum_spread_ratio=0.003,
        )
        self.assertEqual(
            tuple(instrument.instrument_id for instrument, _ in eligible),
            ("GOOD-USDT-SWAP",),
        )


class MarketRadarNotificationTests(unittest.TestCase):
    def test_only_nine_point_or_better_setup_is_notified(self) -> None:
        valid_long = setup_score(SetupDirection.LONG, SetupGrade.VALID)
        strong_long = setup_score(SetupDirection.LONG, SetupGrade.STRONG)
        weak_long = setup_score(SetupDirection.LONG, SetupGrade.WEAK)
        valid_short = setup_score(SetupDirection.SHORT, SetupGrade.VALID)
        self.assertTrue(should_notify_score(None, valid_long))
        self.assertFalse(should_notify_score("long:valid", valid_long))
        self.assertTrue(should_notify_score("long:valid", strong_long))
        self.assertFalse(should_notify_score("long:a_plus_full_sync", strong_long))
        self.assertFalse(should_notify_score(None, weak_long))
        self.assertTrue(should_notify_score("long:valid", valid_short))

    def test_out_of_range_score_resets_notification_state(self) -> None:
        strong_long = setup_score(SetupDirection.LONG, SetupGrade.STRONG)
        valid_long = setup_score(SetupDirection.LONG, SetupGrade.VALID)

        weak_long = setup_score(SetupDirection.LONG, SetupGrade.WEAK)

        self.assertEqual(notification_state_for_score(strong_long), "long:strong")
        self.assertEqual(notification_state_for_score(weak_long), "none")
        self.assertEqual(notification_state_for_score(valid_long), "long:valid")
        self.assertTrue(should_notify_score("none", valid_long))

    def test_report_orders_all_qualifying_grades_from_strongest(self) -> None:
        candidates = [
            MarketRadarCandidate(
                "VALID-USDT-SWAP",
                setup_score(SetupDirection.LONG, SetupGrade.VALID),
                10_000_000.0,
                0.001,
            ),
            MarketRadarCandidate(
                "STRONG-USDT-SWAP",
                setup_score(SetupDirection.LONG, SetupGrade.STRONG),
                10_000_000.0,
                0.001,
            ),
            MarketRadarCandidate(
                "GOOD-USDT-SWAP",
                setup_score(SetupDirection.LONG, SetupGrade.GOOD),
                10_000_000.0,
                0.001,
            ),
        ]

        report = build_market_radar_report(candidates)

        self.assertLess(report.index("STRONG-USDT-SWAP"), report.index("GOOD-USDT-SWAP"))
        self.assertLess(report.index("GOOD-USDT-SWAP"), report.index("VALID-USDT-SWAP"))


if __name__ == "__main__":
    unittest.main()
