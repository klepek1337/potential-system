import logging
from collections.abc import Sequence

from ma_alert_bot.analysis import (
    calculate_latest_moving_average_levels,
    calculate_simple_moving_average,
    detect_tests_on_latest_candle,
    resolve_test_outcome,
)
from ma_alert_bot.models import Candle
from ma_alert_bot.ema_analysis import calculate_latest_ema_levels
from ma_alert_bot.notifications import (
    TelegramNotifier,
    build_current_levels_message,
    build_current_ema_levels_message,
    build_program_started_message,
    build_test_resolved_message,
    build_test_started_message,
)
from ma_alert_bot.okx_client import OkxMarketDataClient
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
    ) -> None:
        self._market_data_client = market_data_client
        self._state_store = state_store
        self._notifier = notifier
        self._timezone_name = timezone_name
        self._touch_margin_ratio = touch_margin_ratio
        self._ema_periods = ema_periods

    def send_program_started(self, instrument_ids: tuple[str, ...]) -> None:
        self._notifier.send(
            build_program_started_message(
                instrument_ids=instrument_ids,
                touch_margin_ratio=self._touch_margin_ratio,
                ema_periods=self._ema_periods,
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
