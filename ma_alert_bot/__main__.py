import argparse
import logging
import time

from ma_alert_bot.config import Settings
from ma_alert_bot.monitor import MovingAverageMonitor
from ma_alert_bot.notifications import TelegramNotifier
from ma_alert_bot.okx_account import OkxReadOnlyAccountClient
from ma_alert_bot.okx_client import OkxMarketDataClient
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
    return argument_parser


def scan_all_instruments(
    monitor: MovingAverageMonitor,
    position_tracker: PositionTracker,
    instrument_ids: tuple[str, ...],
    include_level_summary: bool,
) -> None:
    try:
        position_tracker.refresh()
    except Exception:
        logging.exception("Failed to refresh position data; using last known snapshot")
    for instrument_id in instrument_ids:
        try:
            monitor.scan_instrument(
                instrument_id,
                include_level_summary=include_level_summary,
            )
        except Exception:
            logging.exception("Failed to scan %s", instrument_id)


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
    )

    try:
        if settings.send_startup_summary:
            monitor.send_program_started(settings.instrument_ids)

        if arguments.once:
            scan_all_instruments(
                monitor,
                position_tracker,
                settings.instrument_ids,
                include_level_summary=settings.send_startup_summary,
            )
            return

        is_first_scan = True
        while True:
            scan_all_instruments(
                monitor,
                position_tracker,
                settings.instrument_ids,
                include_level_summary=(
                    is_first_scan and settings.send_startup_summary
                ),
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
        market_data_client.close()
        notifier.close()


if __name__ == "__main__":
    main()
