import unittest
from types import SimpleNamespace

from ma_alert_bot.market_radar import (
    MarketRadarSignal,
    classify_market_radar_signal,
    select_eligible_instruments,
    should_notify_signal,
)
from ma_alert_bot.okx_client import PerpetualInstrument, PerpetualTicker
from ma_alert_bot.szpont_analysis import (
    LongOverheatState,
    MomentumState,
    MovingAverageStructure,
)

CURRENT_TIMESTAMP_MS = 2_000_000_000_000
ONE_DAY_MS = 86_400_000


def assessment(
    state: MomentumState,
    *,
    overheat: LongOverheatState = LongOverheatState.NORMAL,
    confirmation_candles: int = 2,
    close: float = 101.0,
    sma20: float = 100.0,
    sma20_slope: float = 1.0,
    structure: MovingAverageStructure = MovingAverageStructure.MIXED,
) -> SimpleNamespace:
    return SimpleNamespace(
        momentum_state=state,
        long_overheat_state=overheat,
        consecutive_rising_histogram_candles=confirmation_candles,
        closing_price=close,
        moving_average_levels={20: sma20},
        moving_average_slopes={20: sma20_slope},
        moving_average_structure=structure,
    )


class MarketRadarClassificationTests(unittest.TestCase):
    def test_building_accepts_neutral_h4(self) -> None:
        signal = classify_market_radar_signal(
            {
                "1H": assessment(MomentumState.BEARISH_RECOVERY),
                "2H": assessment(MomentumState.BULLISH_CROSS),
                "4H": assessment(MomentumState.NEUTRAL_COMPRESSION),
                "1D": assessment(MomentumState.BEARISH_EXPANSION),
            },
            full_sync_confirmation_candles=2,
        )
        self.assertEqual(signal, MarketRadarSignal.BUILDING)

    def test_strong_requires_rising_h4_and_non_falling_daily(self) -> None:
        signal = classify_market_radar_signal(
            {
                "1H": assessment(MomentumState.BULLISH_EXPANSION),
                "2H": assessment(MomentumState.BEARISH_RECOVERY),
                "4H": assessment(MomentumState.BULLISH_EXPANSION),
                "1D": assessment(MomentumState.NEUTRAL_COMPRESSION),
            },
            full_sync_confirmation_candles=2,
        )
        self.assertEqual(signal, MarketRadarSignal.STRONG)

    def test_h4_deceleration_vetoes_all_alerts(self) -> None:
        signal = classify_market_radar_signal(
            {
                "1H": assessment(MomentumState.BULLISH_EXPANSION),
                "2H": assessment(MomentumState.BULLISH_EXPANSION),
                "4H": assessment(MomentumState.BULLISH_DECELERATION),
                "1D": assessment(MomentumState.BULLISH_EXPANSION),
            },
            full_sync_confirmation_candles=2,
        )
        self.assertEqual(signal, MarketRadarSignal.NONE)

    def test_a_plus_requires_multi_candle_confirmation(self) -> None:
        assessments = {
            timeframe: assessment(MomentumState.BULLISH_EXPANSION)
            for timeframe in ("1H", "2H", "4H", "1D")
        }
        assessments["1H"] = assessment(
            MomentumState.BULLISH_EXPANSION, confirmation_candles=1
        )
        self.assertEqual(
            classify_market_radar_signal(assessments, 2),
            MarketRadarSignal.STRONG,
        )
        assessments["1H"] = assessment(
            MomentumState.BULLISH_EXPANSION, confirmation_candles=2
        )
        self.assertEqual(
            classify_market_radar_signal(assessments, 2),
            MarketRadarSignal.FULL_SYNC,
        )

    def test_overheated_price_downgrades_a_plus_to_strong(self) -> None:
        signal = classify_market_radar_signal(
            {
                "1H": assessment(
                    MomentumState.BULLISH_EXPANSION,
                    overheat=LongOverheatState.HIGH,
                ),
                "2H": assessment(MomentumState.BULLISH_EXPANSION),
                "4H": assessment(MomentumState.BULLISH_EXPANSION),
                "1D": assessment(MomentumState.BULLISH_EXPANSION),
            },
            full_sync_confirmation_candles=2,
        )
        self.assertEqual(signal, MarketRadarSignal.STRONG)


class MarketRadarLiquidityTests(unittest.TestCase):
    def test_filters_age_notional_and_spread(self) -> None:
        instruments = (
            PerpetualInstrument("GOOD-USDT-SWAP", CURRENT_TIMESTAMP_MS - 30 * ONE_DAY_MS),
            PerpetualInstrument("NEW-USDT-SWAP", CURRENT_TIMESTAMP_MS - ONE_DAY_MS),
            PerpetualInstrument("THIN-USDT-SWAP", CURRENT_TIMESTAMP_MS - 30 * ONE_DAY_MS),
        )
        tickers = {
            "GOOD-USDT-SWAP": PerpetualTicker(
                "GOOD-USDT-SWAP", 100.0, 99.9, 100.1, 100_000.0
            ),
            "NEW-USDT-SWAP": PerpetualTicker(
                "NEW-USDT-SWAP", 100.0, 99.9, 100.1, 100_000.0
            ),
            "THIN-USDT-SWAP": PerpetualTicker(
                "THIN-USDT-SWAP", 100.0, 99.0, 101.0, 1_000.0
            ),
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
    def test_only_new_or_stronger_setup_is_notified(self) -> None:
        self.assertTrue(should_notify_signal(None, MarketRadarSignal.BUILDING))
        self.assertFalse(
            should_notify_signal("building", MarketRadarSignal.BUILDING)
        )
        self.assertTrue(
            should_notify_signal("building", MarketRadarSignal.STRONG)
        )
        self.assertFalse(
            should_notify_signal("a_plus_full_sync", MarketRadarSignal.STRONG)
        )
        self.assertFalse(
            should_notify_signal("strong", MarketRadarSignal.NONE)
        )


if __name__ == "__main__":
    unittest.main()
