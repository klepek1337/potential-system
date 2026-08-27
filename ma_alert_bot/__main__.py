import argparse
import logging
import time
from collections.abc import Sequence

from ma_alert_bot.ai_coordinator import AiReportCoordinator
from ma_alert_bot.ai_dispatcher import AiReportDispatcher
from ma_alert_bot.config import Settings
from ma_alert_bot.models import Candle
from ma_alert_bot.monitor import MovingAverageMonitor
from ma_alert_bot.notifications import TelegramNotifier
from ma_alert_bot.okx_account import OkxReadOnlyAccountClient
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.openai_research import OpenAiResearchClient
from ma_alert_bot.position_tracker import PositionTracker
from ma_alert_bot.positions import PositionSource, load_position_plans
from ma_alert_bot.state_store import AlertStateStore


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOOP_FAILURE_DELAY_SECONDS = 10


def build_argument_parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Monitor OKX H4 candles for SMA tests and send Telegram alerts."
    )
    argument_parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scan and exit.",
    )
    argument_parser.add_argument(
        "--ai-report-now",
        action="store_true",
        help="Run one scan, send a full AI research report immediately, and exit.",
    )
    return argument_parser


def scan_all_instruments(
    monitor: MovingAverageMonitor,
    position_tracker: PositionTracker,
    instrument_ids: tuple[str, ...],
    include_level_summary: bool,
) -> dict[str, Sequence[Candle]]:
    try:
        position_tracker.refresh()
    except Exception:
        logging.exception("Failed to refresh position data; using last known snapshot")
    candles_by_instrument: dict[str, Sequence[Candle]] = {}
    for instrument_id in instrument_ids:
        try:
            candles_by_instrument[instrument_id] = monitor.scan_instrument(
                instrument_id,
                include_level_summary=include_level_summary,
            )
        except Exception:
            logging.exception("Failed to scan %s", instrument_id)
    return candles_by_instrument


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    arguments = build_argument_parser().parse_args()
    settings = Settings.from_environment()

    market_data_client = OkxMarketDataClient(settings.okx_api_base_url)
    position_plans = load_position_plans(settings.position_plans_path)
    okx_account_client = None
    if settings.position_source is not PositionSource.MANUAL:
        okx_account_client = OkxReadOnlyAccountClient(
            api_base_url=settings.okx_api_base_url,
            api_key=settings.okx_api_key or "",
            api_secret=settings.okx_api_secret or "",
            api_passphrase=settings.okx_api_passphrase or "",
        )
    position_tracker = PositionTracker(
        source=settings.position_source,
        plans=position_plans,
        okx_account_client=okx_account_client,
    )
    if settings.position_source is PositionSource.MANUAL:
        position_tracker.refresh()
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        dry_run=settings.dry_run,
    )
    state_store = AlertStateStore(settings.state_database_path)
    ai_report_coordinator = None
    ai_report_dispatcher = None
    if settings.ai_analysis_enabled:
        if settings.ai_daily_report_local_time is None:
            raise RuntimeError("AI daily report time was not validated")
        research_client = OpenAiResearchClient(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort,
        )
        ai_report_coordinator = AiReportCoordinator(
            research_client=research_client,
            market_data_client=market_data_client,
            position_tracker=position_tracker,
            state_store=state_store,
            notifier=notifier,
            timezone_name=settings.display_timezone,
            daily_report_local_time=settings.ai_daily_report_local_time,
            event_reports_enabled=settings.ai_event_reports_enabled,
        )
        ai_report_dispatcher = AiReportDispatcher(ai_report_coordinator)
    monitor = MovingAverageMonitor(
        market_data_client=market_data_client,
        state_store=state_store,
        notifier=notifier,
        timezone_name=settings.display_timezone,
        touch_margin_ratio=settings.moving_average_touch_margin_ratio,
        position_tracker=position_tracker,
        send_decision_reports=settings.send_decision_reports,
        daily_decision_report_local_time=(
            settings.daily_decision_report_local_time
        ),
        ai_report_dispatcher=ai_report_dispatcher,
        stop_warning_distance_percent=settings.stop_warning_distance_percent,
        liquidation_warning_distance_percent=(
            settings.liquidation_warning_distance_percent
        ),
    )

    try:
        if settings.send_startup_summary:
            monitor.send_program_started(settings.instrument_ids)

        if arguments.once or arguments.ai_report_now:
            candles_by_instrument = scan_all_instruments(
                monitor,
                position_tracker,
                settings.instrument_ids,
                include_level_summary=settings.send_startup_summary,
            )
            if arguments.ai_report_now:
                if ai_report_coordinator is None:
                    raise RuntimeError(
                        "--ai-report-now requires AI_ANALYSIS_ENABLED=true"
                    )
                ai_report_coordinator.send_daily_report_now(candles_by_instrument)
            elif ai_report_dispatcher is not None:
                ai_report_dispatcher.submit_daily_report_if_due(
                    candles_by_instrument
                )
            return

        is_first_scan = True
        while True:
            candles_by_instrument = scan_all_instruments(
                monitor,
                position_tracker,
                settings.instrument_ids,
                include_level_summary=(
                    is_first_scan and settings.send_startup_summary
                ),
            )
            if ai_report_dispatcher is not None:
                ai_report_dispatcher.submit_daily_report_if_due(
                    candles_by_instrument
                )
            is_first_scan = False
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        logging.info("Stopping monitor")
    except Exception:
        logging.exception("Monitor loop failed")
        time.sleep(LOOP_FAILURE_DELAY_SECONDS)
        raise
    finally:
        if ai_report_dispatcher is not None:
            ai_report_dispatcher.close()
        market_data_client.close()
        notifier.close()


if __name__ == "__main__":
    main()
