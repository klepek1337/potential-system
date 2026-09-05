import logging
import re
from typing import Any

from ma_alert_bot.http_json import get_json
from ma_alert_bot.notifications import TelegramNotifier, format_price
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.state_store import AlertStateStore
from ma_alert_bot.szpont_analysis import (
    SZPONT_TIMEFRAMES,
    MomentumState,
    MovingAverageStructure,
    SynchronizationState,
    SzpontAssessment,
    TimeframeMomentumAssessment,
    analyse_szpont,
)


LOGGER = logging.getLogger(__name__)
TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_REQUEST_TIMEOUT_SECONDS = 10.0
TELEGRAM_LONG_POLL_TIMEOUT_SECONDS = 1
HTTP_USER_AGENT = "okx-ma-telegram-alerts/0.1"
TELEGRAM_UPDATE_OFFSET_STATE_KEY = "telegram_update_offset"
SZPONT_COMMAND_PATTERN = re.compile(
    r"^/szpont(?:@[A-Za-z0-9_]+)?(?:\s+([^\s]+))?\s*$", re.IGNORECASE
)
COMPACT_USDT_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+USDT$")
OKX_USDT_INSTRUMENT_PATTERN = re.compile(r"^[A-Z0-9]+-USDT(?:-SWAP)?$")


MOMENTUM_LABELS = {
    MomentumState.BEARISH_EXPANSION: "🔴 niedźwiedzia ekspansja",
    MomentumState.BEARISH_RECOVERY: "🟡 odbudowa pod zerem",
    MomentumState.BULLISH_CROSS: "🟢 przejście na plus",
    MomentumState.BULLISH_EXPANSION: "🟢 bycza ekspansja",
    MomentumState.BULLISH_DECELERATION: "🟠 dodatni, ale zwalnia",
    MomentumState.BEARISH_CROSS: "🔴 przejście na minus",
    MomentumState.NEUTRAL_COMPRESSION: "⚪ kompresja",
}
SYNCHRONIZATION_HEADINGS = {
    SynchronizationState.RECOVERY_PREPARATION: "🔵 Odbudowa momentum",
    SynchronizationState.EARLY_BULLISH_SYNCHRONIZATION: "🟡 Wczesny układ byczy",
    SynchronizationState.CONFIRMED_BULLISH_EXPANSION: "🟢 Pełny byczy Szpont",
    SynchronizationState.BULLISH_H4_VETO: "🟠 H4 blokuje byczy Szpont",
    SynchronizationState.EARLY_BEARISH_SYNCHRONIZATION: "🟡 Wczesny układ spadkowy",
    SynchronizationState.CONFIRMED_BEARISH_EXPANSION: "🔴 Pełny niedźwiedzi Szpont",
    SynchronizationState.BEARISH_H4_VETO: "🟠 H4 blokuje spadkowy Szpont",
    SynchronizationState.MIXED: "⚪ Brak synchronizacji",
}
MOVING_AVERAGE_STRUCTURE_LABELS = {
    MovingAverageStructure.BULLISH: "bycza",
    MovingAverageStructure.BEARISH: "niedźwiedzia",
    MovingAverageStructure.MIXED: "mieszana",
}


def normalize_okx_instrument_id(requested_symbol: str) -> str:
    normalized_symbol = requested_symbol.strip().upper().replace("/", "-")
    if COMPACT_USDT_SYMBOL_PATTERN.fullmatch(normalized_symbol):
        base_symbol = normalized_symbol[: -len("USDT")]
        return f"{base_symbol}-USDT-SWAP"
    if OKX_USDT_INSTRUMENT_PATTERN.fullmatch(normalized_symbol):
        if normalized_symbol.endswith("-SWAP"):
            return normalized_symbol
        return f"{normalized_symbol}-SWAP"
    raise ValueError(
        "Podaj parę USDT, np. /szpont BTCUSDT albo /szpont BTC-USDT-SWAP"
    )


def build_timeframe_line(assessment: TimeframeMomentumAssessment) -> str:
    structure_label = MOVING_AVERAGE_STRUCTURE_LABELS[
        assessment.moving_average_structure
    ]
    return (
        f"{assessment.timeframe}: {MOMENTUM_LABELS[assessment.momentum_state]} | "
        f"hist {assessment.histogram:+.6g} | "
        f"Δ/ATR {assessment.normalized_histogram_slope:+.4f} | "
        f"SMA {structure_label}"
    )


def build_structure_warning(assessment: TimeframeMomentumAssessment) -> str | None:
    if assessment.overhead_resistance_periods:
        periods = ", ".join(
            f"SMA{period}" for period in assessment.overhead_resistance_periods
        )
        return f"• {assessment.timeframe}: opadający opór nad ceną — {periods}"
    if assessment.underlying_support_periods:
        periods = ", ".join(
            f"SMA{period}" for period in assessment.underlying_support_periods
        )
        return f"• {assessment.timeframe}: rosnące wsparcie pod ceną — {periods}"
    return None


def build_szpont_message(assessment: SzpontAssessment) -> str:
    latest_price = assessment.timeframe_assessments[0].closing_price
    timeframe_lines = [
        build_timeframe_line(timeframe_assessment)
        for timeframe_assessment in assessment.timeframe_assessments
    ]
    structure_warnings = [
        warning
        for timeframe_assessment in assessment.timeframe_assessments
        if (warning := build_structure_warning(timeframe_assessment)) is not None
    ]
    message_lines = [
        f"{SYNCHRONIZATION_HEADINGS[assessment.synchronization_state]} — "
        f"{assessment.instrument_id}",
        f"Cena z ostatniej zamkniętej 1H: {format_price(latest_price)}",
        "",
        *timeframe_lines,
        "",
        f"Wniosek: {assessment.explanation}",
    ]
    if structure_warnings:
        message_lines.extend(("", "Struktura ceny:", *structure_warnings))
    message_lines.extend(
        (
            "",
            "Analiza używa wyłącznie zamkniętych świec OKX.",
            "To opis momentum, nie automatyczne zlecenie wejścia.",
        )
    )
    return "\n".join(message_lines)


class TelegramCommandPoller:
    def __init__(
        self,
        bot_token: str | None,
        allowed_chat_id: str | None,
        market_data_client: OkxMarketDataClient,
        notifier: TelegramNotifier,
        state_store: AlertStateStore,
        enabled: bool,
        minimum_normalized_histogram_slope: float,
    ) -> None:
        self._bot_token = bot_token
        self._allowed_chat_id = allowed_chat_id
        self._market_data_client = market_data_client
        self._notifier = notifier
        self._state_store = state_store
        self._enabled = enabled
        self._minimum_normalized_histogram_slope = (
            minimum_normalized_histogram_slope
        )

    def poll_once(self) -> None:
        if not self._enabled or not self._bot_token or not self._allowed_chat_id:
            return
        response_payload = get_json(
            base_url=TELEGRAM_API_BASE_URL,
            path=f"/bot{self._bot_token}/getUpdates",
            query_parameters=self._build_query_parameters(),
            timeout_seconds=TELEGRAM_REQUEST_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
        )
        if response_payload.get("ok") is not True:
            raise RuntimeError(
                f"Telegram API rejected getUpdates: {response_payload!r}"
            )
        updates = response_payload.get("result", [])
        if not isinstance(updates, list):
            raise ValueError("Telegram getUpdates result must be a list")
        for update in updates:
            if not isinstance(update, dict):
                continue
            self._process_update(update)
            self._save_processed_update_offset(update)

    def _build_query_parameters(self) -> dict[str, str]:
        query_parameters = {"timeout": str(TELEGRAM_LONG_POLL_TIMEOUT_SECONDS)}
        saved_offset = self._state_store.get_runtime_state(
            TELEGRAM_UPDATE_OFFSET_STATE_KEY
        )
        if saved_offset is not None:
            query_parameters["offset"] = str(int(saved_offset) + 1)
        return query_parameters

    def _save_processed_update_offset(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self._state_store.save_runtime_state(
                TELEGRAM_UPDATE_OFFSET_STATE_KEY, str(update_id)
            )

    def _process_update(self, update: dict[str, Any]) -> None:
        telegram_post = update.get("message") or update.get("channel_post")
        if not isinstance(telegram_post, dict):
            return
        chat = telegram_post.get("chat")
        message_text = telegram_post.get("text")
        if not isinstance(chat, dict) or not isinstance(message_text, str):
            return
        if str(chat.get("id")) != str(self._allowed_chat_id):
            LOGGER.warning("Ignoring Telegram command from an unauthorized chat")
            return
        command_match = SZPONT_COMMAND_PATTERN.fullmatch(message_text.strip())
        if command_match is None:
            return
        requested_symbol = command_match.group(1)
        if requested_symbol is None:
            self._notifier.send("Użycie: /szpont BTCUSDT")
            return
        try:
            instrument_id = normalize_okx_instrument_id(requested_symbol)
            candles_by_timeframe = {
                timeframe: self._market_data_client.get_candles(
                    instrument_id, timeframe
                )
                for timeframe in SZPONT_TIMEFRAMES
            }
            assessment = analyse_szpont(
                instrument_id,
                candles_by_timeframe,
                self._minimum_normalized_histogram_slope,
            )
            self._notifier.send(build_szpont_message(assessment))
        except (RuntimeError, ValueError) as error:
            LOGGER.warning("Szpont command failed for %s: %s", requested_symbol, error)
            self._notifier.send(
                f"Nie udało się przeanalizować {requested_symbol.upper()}: {error}"
            )
