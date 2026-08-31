import logging
import time
from collections.abc import Sequence

from ma_alert_bot.analysis import (
    calculate_latest_moving_average_levels,
    calculate_simple_moving_average,
    detect_tests_on_latest_candle,
    resolve_test_outcome,
)
from ma_alert_bot.models import Candle
from ma_alert_bot.minute_sma_tilt import assess_minute_sma_tilt, should_notify_tilt
from ma_alert_bot.ema_analysis import calculate_latest_ema_levels
from ma_alert_bot.dominant_ema import (
    dominant_ema_report_changed,
    ratchet_stop,
    select_dominant_ema,
)
from ma_alert_bot.notifications import (
    TelegramNotifier,
    build_current_levels_message,
    build_current_ema_levels_message,
    build_dominant_ema_message,
    build_profit_protection_message,
    build_minute_sma_tilt_message,
    build_program_started_message,
    build_test_resolved_message,
    build_test_started_message,
)
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.position_store import PositionStore
from ma_alert_bot.profit_protection import assess_profit_protection
from ma_alert_bot.state_store import AlertStateStore


LOGGER = logging.getLogger(__name__)


class MovingAverageMonitor:
    def __init__(
        self,
        market_data_client: OkxMarketDataClient,
        state_store: AlertStateStore,
        notifier: TelegramNotifier,
        timezone_name: str,
        touch_margin_ratio: float,
        ema_periods: tuple[int, ...] = (20, 50, 120, 200),
        position_store: PositionStore | None = None,
        dominant_ema_timeframes: tuple[str, ...] = ("15m", "1H", "4H", "1D"),
        dominant_ema_scan_interval_seconds: int = 3600,
        minute_sma_tilt_enabled: bool = True,
        minute_sma_tilt_period: int = 20,
        minute_sma_tilt_lookback_minutes: int = 5,
        minute_sma_tilt_strong_threshold_atr: float = 0.25,
        minute_sma_tilt_change_threshold_atr: float = 0.5,
        minute_sma_tilt_cooldown_seconds: int = 600,
    ) -> None:
        self._market_data_client = market_data_client
        self._state_store = state_store
        self._notifier = notifier
        self._timezone_name = timezone_name
        self._touch_margin_ratio = touch_margin_ratio
        self._ema_periods = ema_periods
        self._position_store = position_store
        self._dominant_ema_timeframes = dominant_ema_timeframes
        self._dominant_ema_scan_interval_seconds = dominant_ema_scan_interval_seconds
        self._last_dominant_scan_at: dict[str, float] = {}
        self._minute_sma_tilt_enabled = minute_sma_tilt_enabled
        self._minute_sma_tilt_period = minute_sma_tilt_period
        self._minute_sma_tilt_lookback_minutes = minute_sma_tilt_lookback_minutes
        self._minute_sma_tilt_strong_threshold_atr = minute_sma_tilt_strong_threshold_atr
        self._minute_sma_tilt_change_threshold_atr = minute_sma_tilt_change_threshold_atr
        self._minute_sma_tilt_cooldown_seconds = minute_sma_tilt_cooldown_seconds

    def send_program_started(self, instrument_ids: tuple[str, ...]) -> None:
        self._notifier.send(
            build_program_started_message(
                instrument_ids=instrument_ids,
                touch_margin_ratio=self._touch_margin_ratio,
                ema_periods=self._ema_periods,
                minute_sma_tilt_enabled=self._minute_sma_tilt_enabled,
                minute_sma_tilt_period=self._minute_sma_tilt_period,
                minute_sma_tilt_lookback_minutes=self._minute_sma_tilt_lookback_minutes,
            )
        )

    def scan_instrument(
        self,
        instrument_id: str,
        include_level_summary: bool = False,
    ) -> None:
        candles = self._market_data_client.get_four_hour_candles(instrument_id)
        if include_level_summary:
            self._send_current_level_summary(instrument_id, candles)
        self._resolve_finished_tests(instrument_id, candles)
        self._register_current_tests(instrument_id, candles)
        self._scan_minute_sma_tilt(instrument_id)
        self._scan_dominant_ema_if_due(instrument_id)

    def _scan_minute_sma_tilt(self, instrument_id: str) -> None:
        if not self._minute_sma_tilt_enabled:
            return
        candles = self._market_data_client.get_candles(instrument_id, "1m")
        assessment = assess_minute_sma_tilt(
            candles,
            period=self._minute_sma_tilt_period,
            lookback_minutes=self._minute_sma_tilt_lookback_minutes,
            strong_tilt_threshold_atr=self._minute_sma_tilt_strong_threshold_atr,
            change_threshold_atr=self._minute_sma_tilt_change_threshold_atr,
        )
        if assessment is None:
            return
        previous_state = self._state_store.get_minute_sma_tilt_state(instrument_id)
        if previous_state is not None and assessment.candle_timestamp_ms <= previous_state[0]:
            return
        notify = should_notify_tilt(
            assessment,
            previous_state,
            self._minute_sma_tilt_cooldown_seconds,
            self._minute_sma_tilt_change_threshold_atr,
        )
        self._state_store.save_minute_sma_tilt_state(
            instrument_id,
            assessment.candle_timestamp_ms,
            assessment.candle_timestamp_ms if notify else None,
            assessment.direction.value if notify else None,
            assessment.current_tilt_atr if notify else None,
        )
        if notify:
            position = self._position_store.get(instrument_id) if self._position_store else None
            self._notifier.send(
                build_minute_sma_tilt_message(instrument_id, assessment, position)
            )

    def _scan_dominant_ema_if_due(self, instrument_id: str) -> None:
        if self._position_store is None:
            return
        position = self._position_store.get(instrument_id)
        if position is None:
            return
        now = time.monotonic()
        last_scan = self._last_dominant_scan_at.get(instrument_id)
        if last_scan is not None and now - last_scan < self._dominant_ema_scan_interval_seconds:
            return
        candles_by_timeframe = {
            timeframe: self._market_data_client.get_candles(instrument_id, timeframe)
            for timeframe in self._dominant_ema_timeframes
        }
        candidate = select_dominant_ema(candles_by_timeframe, self._ema_periods, position.side)
        self._last_dominant_scan_at[instrument_id] = now
        if candidate is None:
            return
        current_price = candles_by_timeframe[self._dominant_ema_timeframes[0]][-1].closing_price
        proposed_is_valid = (
            candidate.proposed_stop < current_price
            if position.side.value == "long"
            else candidate.proposed_stop > current_price
        )
        if not proposed_is_valid:
            LOGGER.warning("Ignoring dominant EMA stop beyond current price for %s", instrument_id)
            return
        previous_state = self._state_store.get_dominant_ema_state(instrument_id)
        previous_stop = previous_state[0] if previous_state else position.stop_price
        stop_anchor = ratchet_stop(previous_stop, candidate.proposed_stop, position.side)
        should_notify = dominant_ema_report_changed(
            previous_state, candidate.timeframe, candidate.period, stop_anchor
        )
        self._state_store.save_stop_anchor(
            instrument_id, stop_anchor, candidate.timeframe, candidate.period, candidate.score
        )
        if should_notify:
            self._notifier.send(
                build_dominant_ema_message(
                    instrument_id, candidate, previous_stop, stop_anchor
                )
            )
        previous_stage = self._state_store.get_profit_protection_stage(instrument_id)
        assessment = assess_profit_protection(
            position, current_price, stop_anchor, candidate, previous_stage
        )
        if assessment.stage > previous_stage:
            self._notifier.send(
                build_profit_protection_message(
                    position, current_price, stop_anchor, assessment
                )
            )
            self._state_store.save_profit_protection_stage(
                instrument_id, assessment.stage
            )

    def _send_current_level_summary(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> None:
        if not candles:
            return
        moving_average_levels = calculate_latest_moving_average_levels(candles)
        self._notifier.send(
            build_current_levels_message(
                instrument_id=instrument_id,
                current_price=candles[-1].closing_price,
                moving_average_levels=moving_average_levels,
            )
        )
        ema_levels = calculate_latest_ema_levels(candles, self._ema_periods)
        self._notifier.send(
            build_current_ema_levels_message(
                instrument_id=instrument_id,
                current_price=candles[-1].closing_price,
                ema_levels=ema_levels,
            )
        )

    def _register_current_tests(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> None:
        for moving_average_test in detect_tests_on_latest_candle(
            instrument_id,
            candles,
            touch_margin_ratio=self._touch_margin_ratio,
        ):
            if not self._state_store.register_test_if_new(moving_average_test):
                continue

            LOGGER.info(
                "%s started testing SMA %s",
                instrument_id,
                moving_average_test.moving_average_period,
            )
            self._notifier.send(
                build_test_started_message(moving_average_test, self._timezone_name)
            )

    def _resolve_finished_tests(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> None:
        candle_index_by_timestamp = {
            candle.opening_timestamp_ms: candle_index
            for candle_index, candle in enumerate(candles)
        }
        unresolved_tests = self._state_store.get_unresolved_tests(instrument_id)

        for unresolved_test in unresolved_tests:
            candle_index = candle_index_by_timestamp.get(
                unresolved_test.candle_opening_timestamp_ms
            )
            if candle_index is None:
                LOGGER.warning(
                    "Cannot resolve old SMA test because its candle is no longer available: %s",
                    unresolved_test,
                )
                continue

            tested_candle = candles[candle_index]
            if not tested_candle.is_confirmed:
                continue

            final_moving_average_value = calculate_simple_moving_average(
                candles,
                candle_index,
                unresolved_test.moving_average_period,
            )
            if final_moving_average_value is None:
                continue

            outcome = resolve_test_outcome(
                unresolved_test.approach_side,
                tested_candle.closing_price,
                final_moving_average_value,
            )
            self._notifier.send(
                build_test_resolved_message(
                    instrument_id=unresolved_test.instrument_id,
                    moving_average_period=unresolved_test.moving_average_period,
                    candle_opening_timestamp_ms=(
                        unresolved_test.candle_opening_timestamp_ms
                    ),
                    closing_price=tested_candle.closing_price,
                    final_moving_average_value=final_moving_average_value,
                    outcome=outcome,
                    timezone_name=self._timezone_name,
                )
            )
            self._state_store.mark_test_resolved(unresolved_test, outcome.value)
