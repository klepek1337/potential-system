import argparse
import logging
import time

from ma_alert_bot.config import Settings
from ma_alert_bot.monitor import MovingAverageMonitor
from ma_alert_bot.models import ManualPosition, PositionSide
from ma_alert_bot.notifications import TelegramNotifier
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.position_store import PositionStore
from ma_alert_bot.state_store import AlertStateStore
from ma_alert_bot.telegram_commands import TelegramCommandPoller


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
    subparsers = argument_parser.add_subparsers(dest="command")
    position_parser = subparsers.add_parser("position", help="Manage manual positions")
    position_commands = position_parser.add_subparsers(dest="position_command", required=True)
    set_parser = position_commands.add_parser("set", help="Add or replace a position")
    set_parser.add_argument("instrument_id")
    set_parser.add_argument("side", choices=("long", "short"))
    set_parser.add_argument("--entry", type=float, required=True)
    set_parser.add_argument("--stop", type=float, required=True)
    set_parser.add_argument(
        "--value",
        dest="position_value_usd",
        type=float,
        help="Current position value shown by OKX in USD/USDC",
    )
    set_parser.add_argument("--leverage", type=float)
    list_parser = position_commands.add_parser("list", help="List configured positions")
    list_parser.set_defaults(position_command="list")
    remove_parser = position_commands.add_parser("remove", help="Remove a position")
    remove_parser.add_argument("instrument_id")
    return argument_parser


def handle_position_command(
    arguments: argparse.Namespace,
    store: PositionStore,
    state_store: AlertStateStore,
) -> None:
    if arguments.position_command == "set":
        position = ManualPosition(
            instrument_id=arguments.instrument_id.upper(),
            side=PositionSide(arguments.side),
            entry_price=arguments.entry,
            stop_price=arguments.stop,
            position_value_usd=arguments.position_value_usd,
            leverage=arguments.leverage,
        )
        # Validate through the same serialization path used for future reads.
        store.set(position)
        state_store.reset_position_risk_state(position.instrument_id)
        print(f"Saved {position.side.value} {position.instrument_id}")
        return
    if arguments.position_command == "remove":
        removed = store.remove(arguments.instrument_id)
        state_store.reset_position_risk_state(arguments.instrument_id)
        print("Removed" if removed else "Position not found")
        return
    for position in store.list_positions():
        print(
            f"{position.instrument_id} {position.side.value} "
            f"entry={position.entry_price:g} stop={position.stop_price:g} "
            f"value_usd={position.position_value_usd or '-'} "
            f"leverage={position.leverage or '-'}"
        )


def scan_all_instruments(
    monitor: MovingAverageMonitor,
    instrument_ids: tuple[str, ...],
    include_level_summary: bool,
) -> None:
    for instrument_id in instrument_ids:
        try:
            monitor.scan_instrument(
                instrument_id,
                include_level_summary=include_level_summary,
            )
        except Exception:
            logging.exception("Failed to scan %s", instrument_id)


def poll_telegram_commands(command_poller: TelegramCommandPoller) -> None:
    try:
        command_poller.poll_once()
    except Exception:
        logging.exception("Failed to poll Telegram commands")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    arguments = build_argument_parser().parse_args()
    settings = Settings.from_environment()
    position_store = PositionStore(settings.positions_file_path)
    state_store = AlertStateStore(settings.state_database_path)
    if arguments.command == "position":
        handle_position_command(arguments, position_store, state_store)
        return

    market_data_client = OkxMarketDataClient(settings.okx_api_base_url)
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        dry_run=settings.dry_run,
    )
    command_poller = TelegramCommandPoller(
        bot_token=settings.telegram_bot_token,
        allowed_chat_id=settings.telegram_chat_id,
        market_data_client=market_data_client,
        notifier=notifier,
        state_store=state_store,
        enabled=settings.telegram_commands_enabled and not settings.dry_run,
        minimum_normalized_histogram_slope=(
            settings.szpont_minimum_normalized_histogram_slope
        ),
    )
    monitor = MovingAverageMonitor(
        market_data_client=market_data_client,
        state_store=state_store,
        notifier=notifier,
        timezone_name=settings.display_timezone,
        touch_margin_ratio=settings.moving_average_touch_margin_ratio,
        ema_periods=settings.ema_periods,
        position_store=position_store,
        dominant_ema_timeframes=settings.dominant_ema_timeframes,
        dominant_ema_scan_interval_seconds=settings.dominant_ema_scan_interval_seconds,
        minute_sma_tilt_enabled=settings.minute_sma_tilt_enabled,
        minute_sma_tilt_period=settings.minute_sma_tilt_period,
        minute_sma_tilt_lookback_minutes=settings.minute_sma_tilt_lookback_minutes,
        minute_sma_tilt_strong_threshold_atr=(
            settings.minute_sma_tilt_strong_threshold_atr
        ),
        minute_sma_tilt_change_threshold_atr=(
            settings.minute_sma_tilt_change_threshold_atr
        ),
        minute_sma_tilt_cooldown_seconds=settings.minute_sma_tilt_cooldown_seconds,
        send_startup_configuration=settings.send_startup_configuration,
    )

    try:
        if settings.send_startup_summary:
            monitor.send_program_started(settings.instrument_ids)

        if arguments.once:
            scan_all_instruments(
                monitor,
                settings.instrument_ids,
                include_level_summary=settings.send_startup_level_summaries,
            )
            return

        is_first_scan = True
        while True:
            poll_telegram_commands(command_poller)
            scan_all_instruments(
                monitor,
                settings.instrument_ids,
                include_level_summary=(
                    is_first_scan and settings.send_startup_level_summaries
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
