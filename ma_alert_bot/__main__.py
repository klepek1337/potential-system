import argparse
import logging
import time

from ma_alert_bot.config import Settings
from ma_alert_bot.monitor import MovingAverageMonitor
from ma_alert_bot.notifications import TelegramNotifier
from ma_alert_bot.okx_client import OkxMarketDataClient
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
    instrument_ids: tuple[str, ...],
) -> None:
    for instrument_id in instrument_ids:
        try:
            monitor.scan_instrument(instrument_id)
        except Exception:
            logging.exception("Failed to scan %s", instrument_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    arguments = build_argument_parser().parse_args()
    settings = Settings.from_environment()

    market_data_client = OkxMarketDataClient(settings.okx_api_base_url)
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
    )

    try:
        if arguments.once:
            scan_all_instruments(monitor, settings.instrument_ids)
            return

        while True:
            scan_all_instruments(monitor, settings.instrument_ids)
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

