from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ma_alert_bot.http_json import post_json
from ma_alert_bot.models import ApproachSide, MovingAverageTest, TestOutcome


TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_REQUEST_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "okx-ma-telegram-alerts/0.1"
FOUR_HOUR_CANDLE_DURATION = timedelta(hours=4)
RATIO_TO_PERCENT_MULTIPLIER = 100.0

OUTCOME_HEADINGS = {
    TestOutcome.SUPPORT_DEFENDED: "🟢 SMA obroniona jako wsparcie",
    TestOutcome.SUPPORT_LOST: "🔴 Zamknięcie pod SMA — wsparcie utracone",
    TestOutcome.RESISTANCE_REJECTED: "🔴 Odrzucenie od SMA — opór utrzymany",
    TestOutcome.RESISTANCE_RECLAIMED: "🟢 Zamknięcie nad SMA — opór przejęty",
}


def format_price(price: float) -> str:
    return f"{price:.10f}".rstrip("0").rstrip(".")


def format_local_time(timestamp_ms: int, timezone_name: str) -> str:
    utc_datetime = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    local_datetime = utc_datetime.astimezone(ZoneInfo(timezone_name))
    return local_datetime.strftime("%Y-%m-%d %H:%M %Z")


def format_percentage(percentage_value: float) -> str:
    return f"{percentage_value:+.2f}%"


def build_program_started_message(
    instrument_ids: tuple[str, ...],
    touch_margin_ratio: float,
) -> str:
    touch_margin_percent = touch_margin_ratio * RATIO_TO_PERCENT_MULTIPLIER
    return "\n".join(
        (
            "🚀 OKX SMA scanner uruchomiony",
            "Interwał: H4",
            "Średnie: SMA 20, SMA 50, SMA 120, SMA 200",
            f"Margines kontaktu: {touch_margin_percent:.3g}%",
            f"Instrumenty: {', '.join(instrument_ids)}",
        )
    )


def build_current_levels_message(
    instrument_id: str,
    current_price: float,
    moving_average_levels: dict[int, float],
) -> str:
    message_lines = [
        f"📊 Aktualne poziomy SMA H4 — {instrument_id}",
        f"Cena: {format_price(current_price)}",
    ]
    for moving_average_period, moving_average_value in moving_average_levels.items():
        distance_percent = (
            (current_price - moving_average_value)
            / moving_average_value
            * RATIO_TO_PERCENT_MULTIPLIER
        )
        price_position = "nad" if distance_percent >= 0 else "pod"
        message_lines.append(
            f"SMA {moving_average_period}: {format_price(moving_average_value)} "
            f"({format_percentage(abs(distance_percent))} {price_position})"
        )
    return "\n".join(message_lines)


def build_test_started_message(
    moving_average_test: MovingAverageTest,
    timezone_name: str,
) -> str:
    candle_closing_timestamp_ms = int(
        (
            datetime.fromtimestamp(
                moving_average_test.candle_opening_timestamp_ms / 1000,
                tz=UTC,
            )
            + FOUR_HOUR_CANDLE_DURATION
        ).timestamp()
        * 1000
    )
    expected_role = (
        "potencjalne wsparcie"
        if moving_average_test.approach_side is ApproachSide.ABOVE
        else "potencjalny opór"
    )
    return "\n".join(
        (
            "🟡 Test SMA na H4",
            f"Instrument: {moving_average_test.instrument_id}",
            f"Średnia: SMA {moving_average_test.moving_average_period}",
            f"Cena: {format_price(moving_average_test.price_at_detection)}",
            "Wartość SMA: "
            f"{format_price(moving_average_test.moving_average_value_at_detection)}",
            f"Kierunek testu: {expected_role}",
            "Zamknięcie świecy: "
            f"{format_local_time(candle_closing_timestamp_ms, timezone_name)}",
        )
    )


def build_test_resolved_message(
    instrument_id: str,
    moving_average_period: int,
    candle_opening_timestamp_ms: int,
    closing_price: float,
    final_moving_average_value: float,
    outcome: TestOutcome,
    timezone_name: str,
) -> str:
    return "\n".join(
        (
            OUTCOME_HEADINGS[outcome],
            f"Instrument: {instrument_id}",
            f"Średnia: SMA {moving_average_period}",
            f"Zamknięcie: {format_price(closing_price)}",
            f"Końcowa wartość SMA: {format_price(final_moving_average_value)}",
            "Świeca otwarta: "
            f"{format_local_time(candle_opening_timestamp_ms, timezone_name)}",
        )
    )


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        dry_run: bool,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._dry_run = dry_run

    def close(self) -> None:
        return None

    def send(self, message: str) -> None:
        if self._dry_run:
            print(f"\n--- DRY RUN TELEGRAM ---\n{message}\n")
            return

        response_payload = post_json(
            base_url=TELEGRAM_API_BASE_URL,
            path=f"/bot{self._bot_token}/sendMessage",
            request_payload={
                "chat_id": self._chat_id,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout_seconds=TELEGRAM_REQUEST_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
        )
        if response_payload.get("ok") is not True:
            raise RuntimeError(f"Telegram API rejected the message: {response_payload!r}")
