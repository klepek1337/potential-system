import logging
from collections.abc import Sequence
from datetime import UTC, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ma_alert_bot.ai_analysis import (
    AiReportType,
    InstrumentMarketSnapshot,
    OkxDerivativeMetrics,
    format_ai_report_for_telegram,
)
from ma_alert_bot.analysis import calculate_latest_moving_average_levels
from ma_alert_bot.decision_state import build_decision_state
from ma_alert_bot.models import Candle
from ma_alert_bot.notifications import TelegramNotifier
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.position_tracker import PositionTracker
from ma_alert_bot.state_store import AlertStateStore


LOGGER = logging.getLogger(__name__)
PORTFOLIO_SCOPE_KEY = "portfolio"
PERCENT_MULTIPLIER = 100.0
MINIMUM_PRICES_FOR_H4_CHANGE = 2


class AiResearchClient(Protocol):
    def create_report(
        self,
        report_type: AiReportType,
        snapshots: list[InstrumentMarketSnapshot],
        market_events: list[str],
        previous_report: dict[str, Any] | None,
    ) -> dict[str, Any]: ...


def _empty_derivative_metrics() -> OkxDerivativeMetrics:
    return OkxDerivativeMetrics(
        last_price=None,
        mark_price=None,
        open_interest_contracts=None,
        open_interest_currency=None,
        funding_rate=None,
        next_funding_rate=None,
        next_funding_timestamp_ms=None,
        twenty_four_hour_open_price=None,
        twenty_four_hour_high_price=None,
        twenty_four_hour_low_price=None,
        twenty_four_hour_volume_currency=None,
    )


def _percentage_change(current_value: float, previous_value: float | None) -> float | None:
    if previous_value in (None, 0):
        return None
    return (current_value - previous_value) / previous_value * PERCENT_MULTIPLIER


class AiReportCoordinator:
    def __init__(
        self,
        research_client: AiResearchClient,
        market_data_client: OkxMarketDataClient,
        position_tracker: PositionTracker,
        state_store: AlertStateStore,
        notifier: TelegramNotifier,
        timezone_name: str,
        daily_report_local_time: time,
        event_reports_enabled: bool,
    ) -> None:
        self._research_client = research_client
        self._market_data_client = market_data_client
        self._position_tracker = position_tracker
        self._state_store = state_store
        self._notifier = notifier
        self._timezone_name = timezone_name
        self._daily_report_local_time = daily_report_local_time
        self._event_reports_enabled = event_reports_enabled

    def send_daily_report_if_due(
        self,
        candles_by_instrument: dict[str, Sequence[Candle]],
    ) -> None:
        local_datetime = datetime.now(ZoneInfo(self._timezone_name))
        if local_datetime.time() < self._daily_report_local_time:
            return
        local_date = local_datetime.date().isoformat()
        if self._state_store.was_ai_daily_report_sent(local_date):
            return

        report_was_sent = self._send_daily_report(candles_by_instrument)
        if report_was_sent:
            self._state_store.mark_ai_daily_report_sent(local_date)

    def send_daily_report_now(
        self,
        candles_by_instrument: dict[str, Sequence[Candle]],
    ) -> bool:
        return self._send_daily_report(candles_by_instrument)

    def _send_daily_report(
        self,
        candles_by_instrument: dict[str, Sequence[Candle]],
    ) -> bool:
        snapshots = [
            self._build_snapshot(instrument_id, candles)
            for instrument_id, candles in candles_by_instrument.items()
            if candles
        ]
        if not snapshots:
            return False
        previous_report = self._state_store.get_latest_ai_report(
            AiReportType.DAILY.value,
            PORTFOLIO_SCOPE_KEY,
        )
        report = self._research_client.create_report(
            report_type=AiReportType.DAILY,
            snapshots=snapshots,
            market_events=[],
            previous_report=previous_report,
        )
        self._send_and_store_report(
            report_type=AiReportType.DAILY,
            scope_key=PORTFOLIO_SCOPE_KEY,
            report=report,
        )
        return True

    def send_event_report(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
        market_events: list[str],
    ) -> None:
        if not self._event_reports_enabled or not market_events or not candles:
            return
        snapshot = self._build_snapshot(instrument_id, candles)
        previous_report = self._state_store.get_latest_ai_report(
            AiReportType.DAILY.value,
            PORTFOLIO_SCOPE_KEY,
        )
        report = self._research_client.create_report(
            report_type=AiReportType.MARKET_EVENT,
            snapshots=[snapshot],
            market_events=market_events,
            previous_report=previous_report,
        )
        self._send_and_store_report(
            report_type=AiReportType.MARKET_EVENT,
            scope_key=instrument_id,
            report=report,
        )

    def _build_snapshot(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
    ) -> InstrumentMarketSnapshot:
        current_price = candles[-1].closing_price
        confirmed_candles = [candle for candle in candles if candle.is_confirmed]
        latest_confirmed_close = (
            confirmed_candles[-1].closing_price
            if confirmed_candles
            else current_price
        )
        h4_previous_close = (
            confirmed_candles[-2].closing_price
            if len(confirmed_candles) >= MINIMUM_PRICES_FOR_H4_CHANGE
            else None
        )
        try:
            derivative_metrics = self._market_data_client.get_derivative_metrics(
                instrument_id
            )
        except Exception:
            LOGGER.exception("Failed to fetch derivative metrics for %s", instrument_id)
            derivative_metrics = _empty_derivative_metrics()

        moving_average_levels = calculate_latest_moving_average_levels(candles)
        position = self._position_tracker.get_position(instrument_id)
        return InstrumentMarketSnapshot(
            instrument_id=instrument_id,
            generated_at_utc=datetime.now(tz=UTC).isoformat(),
            current_price=current_price,
            latest_confirmed_h4_close=latest_confirmed_close,
            h4_change_percent=_percentage_change(
                latest_confirmed_close,
                h4_previous_close,
            ),
            twenty_four_hour_change_percent=_percentage_change(
                current_price,
                derivative_metrics.twenty_four_hour_open_price,
            ),
            moving_average_levels={
                str(period): value
                for period, value in moving_average_levels.items()
            },
            decision_state=build_decision_state(
                current_price=current_price,
                latest_confirmed_price=latest_confirmed_close,
                moving_average_levels=moving_average_levels,
                position=position,
            ),
            derivative_metrics=derivative_metrics,
            position=position,
        )

    def _send_and_store_report(
        self,
        report_type: AiReportType,
        scope_key: str,
        report: dict[str, Any],
    ) -> None:
        self._notifier.send_long(format_ai_report_for_telegram(report))
        self._state_store.save_ai_report(
            report_type=report_type.value,
            scope_key=scope_key,
            created_at_utc=datetime.now(tz=UTC).isoformat(),
            report=report,
        )
