import logging
from collections.abc import Sequence
from datetime import datetime, time
from zoneinfo import ZoneInfo

from ma_alert_bot.ai_dispatcher import AiReportDispatcher
from ma_alert_bot.analysis import (
    calculate_latest_moving_average_levels,
    calculate_simple_moving_average,
    detect_tests_on_latest_candle,
    resolve_test_outcome,
)
from ma_alert_bot.decision_report import build_decision_report
from ma_alert_bot.models import Candle
from ma_alert_bot.notifications import (
    TelegramNotifier,
    build_current_levels_message,
    build_program_started_message,
    build_test_resolved_message,
    build_test_started_message,
)
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.position_risk import PositionRiskType, evaluate_position_risks
from ma_alert_bot.position_tracker import PositionTracker
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
        position_tracker: PositionTracker,
        send_decision_reports: bool,
        daily_decision_report_local_time: time | None,
        ai_report_dispatcher: AiReportDispatcher | None,
        stop_warning_distance_percent: float,
        liquidation_warning_distance_percent: float,
    ) -> None:
        self._market_data_client = market_data_client
        self._state_store = state_store
        self._notifier = notifier
        self._timezone_name = timezone_name
        self._touch_margin_ratio = touch_margin_ratio
        self._position_tracker = position_tracker
        self._send_decision_reports = send_decision_reports
        self._daily_decision_report_local_time = daily_decision_report_local_time
        self._ai_report_dispatcher = ai_report_dispatcher
        self._stop_warning_distance_percent = stop_warning_distance_percent
        self._liquidation_warning_distance_percent = (
            liquidation_warning_distance_percent
        )

    def send_program_started(self, instrument_ids: tuple[str, ...]) -> None:
        self._notifier.send(
            build_program_started_message(
                instrument_ids=instrument_ids,
                touch_margin_ratio=self._touch_margin_ratio,
            )
        )

    def scan_instrument(
        self,
        instrument_id: str,
        include_level_summary: bool = False,
    ) -> Sequence[Candle]:
        candles = self._market_data_client.get_four_hour_candles(instrument_id)
        if not candles:
            return candles
        daily_report_date = self._get_due_daily_report_date(instrument_id)
        if include_level_summary or daily_report_date is not None:
            self._send_current_level_summary(instrument_id, candles)
            if daily_report_date is not None:
                self._state_store.mark_daily_report_sent(
                    instrument_id,
                    daily_report_date,
                )
        position_risk_events = self._check_position_risk(
            instrument_id,
            candles[-1].closing_price,
        )
        resolved_events = self._resolve_finished_tests(instrument_id, candles)
        started_events = self._register_current_tests(instrument_id, candles)
        self._send_ai_event_report(
            instrument_id,
            candles,
            position_risk_events + resolved_events + started_events,
        )
        return candles

    def _send_current_level_summary(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> None:
        if not candles:
            return
        moving_average_levels = calculate_latest_moving_average_levels(candles)
        message = build_current_levels_message(
            instrument_id=instrument_id,
            current_price=candles[-1].closing_price,
            moving_average_levels=moving_average_levels,
        )
        if self._send_decision_reports:
            message += "\n\n" + self._build_decision_report(
                instrument_id,
                candles[-1].closing_price,
                moving_average_levels,
                candles,
            )
        self._notifier.send(message)

    def _register_current_tests(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> list[str]:
        ai_market_events: list[str] = []
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
            message = build_test_started_message(
                moving_average_test,
                self._timezone_name,
            )
            if self._send_decision_reports:
                message += "\n\n" + self._build_decision_report(
                    instrument_id,
                    candles[-1].closing_price,
                    calculate_latest_moving_average_levels(candles),
                    candles,
                )
            self._notifier.send(message)
            ai_market_events.append(
                f"Rozpoczęto test SMA {moving_average_test.moving_average_period} "
                f"od strony {moving_average_test.approach_side.value}."
            )
        return ai_market_events

    def _resolve_finished_tests(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> list[str]:
        candle_index_by_timestamp = {
            candle.opening_timestamp_ms: candle_index
            for candle_index, candle in enumerate(candles)
        }
        unresolved_tests = self._state_store.get_unresolved_tests(instrument_id)
        ai_market_events: list[str] = []

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
            message = build_test_resolved_message(
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
            if self._send_decision_reports:
                message += "\n\n" + self._build_decision_report(
                    instrument_id,
                    candles[-1].closing_price,
                    calculate_latest_moving_average_levels(candles),
                    candles,
                )
            self._notifier.send(message)
            self._state_store.mark_test_resolved(unresolved_test, outcome.value)
            ai_market_events.append(
                f"Test SMA {unresolved_test.moving_average_period} zakończył się "
                f"wynikiem {outcome.value} po potwierdzonym zamknięciu H4."
            )
        return ai_market_events

    def _build_decision_report(
        self,
        instrument_id: str,
        current_price: float,
        moving_average_levels: dict[int, float],
        candles: Sequence[Candle],
    ) -> str:
        latest_confirmed_price = next(
            (
                candle.closing_price
                for candle in reversed(candles)
                if candle.is_confirmed
            ),
            current_price,
        )
        return build_decision_report(
            instrument_id=instrument_id,
            current_price=current_price,
            moving_average_levels=moving_average_levels,
            position=self._position_tracker.get_position(instrument_id),
            latest_confirmed_price=latest_confirmed_price,
        )

    def _get_due_daily_report_date(self, instrument_id: str) -> str | None:
        if (
            not self._send_decision_reports
            or self._daily_decision_report_local_time is None
        ):
            return None
        local_datetime = datetime.now(ZoneInfo(self._timezone_name))
        if local_datetime.time() < self._daily_decision_report_local_time:
            return None
        local_date = local_datetime.date().isoformat()
        if self._state_store.was_daily_report_sent(instrument_id, local_date):
            return None
        return local_date

    def _send_ai_event_report(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
        market_events: list[str],
    ) -> None:
        if self._ai_report_dispatcher is None or not market_events:
            return
        self._ai_report_dispatcher.submit_event_report(
            instrument_id=instrument_id,
            candles=candles,
            market_events=market_events,
        )

    def _check_position_risk(
        self,
        instrument_id: str,
        current_price: float,
    ) -> list[str]:
        active_alerts = evaluate_position_risks(
            current_price=current_price,
            position=self._position_tracker.get_position(instrument_id),
            stop_warning_distance_percent=self._stop_warning_distance_percent,
            liquidation_warning_distance_percent=(
                self._liquidation_warning_distance_percent
            ),
        )
        new_risk_events: list[str] = []
        for risk_type in PositionRiskType:
            active_alert = active_alerts.get(risk_type)
            if active_alert is None:
                self._state_store.clear_position_risk_alert(
                    instrument_id,
                    risk_type.value,
                )
                continue
            if not self._state_store.activate_position_risk_alert_if_new(
                instrument_id,
                risk_type.value,
            ):
                continue
            self._notifier.send(active_alert.message)
            new_risk_events.append(active_alert.message)
        return new_risk_events
