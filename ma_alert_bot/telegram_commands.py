import json
import logging
import re
import time
from typing import Any

from ma_alert_bot.http_json import get_json
from ma_alert_bot.notifications import TelegramNotifier, format_price
from ma_alert_bot.okx_client import OkxMarketDataClient
from ma_alert_bot.state_store import AlertStateStore
from ma_alert_bot.szpont_analysis import (
    SZPONT_TIMEFRAMES,
    LongOverheatState,
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
DYNAMIC_INSTRUMENTS_STATE_KEY = "dynamic_instrument_ids"
LONG_WATCH_INSTRUMENTS_STATE_KEY = "long_watch_instrument_ids"
LONG_WATCH_TIMEFRAME_STATE_PREFIX = "long_watch_timeframe"
COMMAND_PATTERN = re.compile(
    r"^/(szpont|dodaj|obserwujlong)(?:@[A-Za-z0-9_]+)?(?:\s+([^\s]+))?\s*$",
    re.IGNORECASE,
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
OVERHEAT_LABELS = {
    LongOverheatState.NORMAL: "🟢 normalne",
    LongOverheatState.ELEVATED: "🟠 podwyższone",
    LongOverheatState.HIGH: "🔴 wysokie",
}
FALLING_MOMENTUM_STATES = {
    MomentumState.BULLISH_DECELERATION,
    MomentumState.BEARISH_CROSS,
    MomentumState.BEARISH_EXPANSION,
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
        f"od SMA20 {assessment.price_distance_from_sma20_atr:+.2f} ATR | "
        f"SMA {structure_label}"
    )


def build_long_watch_alert(
    assessment: SzpontAssessment,
    falling_timeframes: tuple[str, ...],
) -> str:
    assessments_by_timeframe = {
        timeframe_assessment.timeframe: timeframe_assessment
        for timeframe_assessment in assessment.timeframe_assessments
    }
    currently_falling = tuple(
        timeframe_assessment.timeframe
        for timeframe_assessment in assessment.timeframe_assessments
        if timeframe_assessment.momentum_state in FALLING_MOMENTUM_STATES
    )
    if ("4H" in falling_timeframes or "1D" in falling_timeframes) and len(
        currently_falling
    ) >= 2:
        recommendation = (
            "MOCNA OCHRONA ZYSKU — rozważ wyjście lub dużą redukcję longa."
        )
    elif "4H" in falling_timeframes or "1D" in falling_timeframes:
        recommendation = (
            "REDUKUJ RYZYKO — wyższy interwał zwalnia; rozważ częściową realizację."
        )
    elif len(currently_falling) >= 2:
        recommendation = (
            "ZABEZPIECZ ZYSK — kilka interwałów słabnie; nie dokładaj do longa."
        )
    else:
        recommendation = (
            "WCZESNE OSTRZEŻENIE — niższy interwał zwalnia; zacieśnij kontrolę ryzyka."
        )

    trigger_lines: list[str] = []
    for timeframe in falling_timeframes:
        timeframe_assessment = assessments_by_timeframe[timeframe]
        bullish_leg = (
            f"{timeframe_assessment.bullish_leg_return_percent:+.2f}%"
            if timeframe_assessment.bullish_leg_return_percent is not None
            else "brak aktywnej dodatniej nogi MACD"
        )
        trigger_lines.extend(
            (
                f"\n{timeframe} — histogram właśnie zaczął spadać",
                f"MACD {timeframe_assessment.macd_line:+.6g} | "
                f"Signal {timeframe_assessment.signal_line:+.6g}",
                "Różnica MACD−Signal (= histogram): "
                f"{timeframe_assessment.histogram:+.6g} "
                f"({timeframe_assessment.macd_signal_gap_atr:+.4f} ATR)",
                "Zmiana histogramu: "
                f"{timeframe_assessment.histogram - timeframe_assessment.previous_histogram:+.6g} "
                f"({timeframe_assessment.normalized_histogram_slope:+.4f} ATR)",
                "Rozciągnięcie od SMA20: "
                f"{timeframe_assessment.price_distance_from_sma20_percent:+.2f}% / "
                f"{timeframe_assessment.price_distance_from_sma20_atr:+.2f} ATR",
                f"Ruch od początku dodatniej nogi MACD: {bullish_leg}",
                "Przegrzanie longa: "
                f"{OVERHEAT_LABELS[timeframe_assessment.long_overheat_state]} "
                f"(histogram: {timeframe_assessment.histogram_percentile:.0f}. percentyl)",
            )
        )

    state_lines = [
        f"{item.timeframe}: {MOMENTUM_LABELS[item.momentum_state]}"
        for item in assessment.timeframe_assessments
    ]
    return "\n".join(
        (
            f"⚠️ LONG WATCH — {assessment.instrument_id}",
            f"Cena: {format_price(assessment.timeframe_assessments[0].closing_price)}",
            *trigger_lines,
            "",
            "Cały układ:",
            *state_lines,
            f"Synchronizacja: {assessment.explanation}",
            "",
            f"Zalecenie: {recommendation}",
            "Bot nie wykonuje zleceń, wypłat ani zamknięć pozycji.",
        )
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
        long_watch_scan_interval_seconds: int = 60,
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
        self._long_watch_scan_interval_seconds = long_watch_scan_interval_seconds
        self._next_long_watch_scan_at = 0.0

    def get_active_instrument_ids(
        self, configured_instrument_ids: tuple[str, ...]
    ) -> tuple[str, ...]:
        dynamic_instrument_ids = self._load_instrument_ids(
            DYNAMIC_INSTRUMENTS_STATE_KEY
        )
        return tuple(dict.fromkeys((*configured_instrument_ids, *dynamic_instrument_ids)))

    def scan_long_watches(self) -> None:
        if not self._enabled:
            return
        current_time = time.monotonic()
        if current_time < self._next_long_watch_scan_at:
            return
        self._next_long_watch_scan_at = (
            current_time + self._long_watch_scan_interval_seconds
        )
        for instrument_id in self._load_instrument_ids(
            LONG_WATCH_INSTRUMENTS_STATE_KEY
        ):
            try:
                assessment = self._analyse(instrument_id)
                falling_timeframes = self._update_long_watch_state(assessment)
                if falling_timeframes:
                    self._notifier.send(
                        build_long_watch_alert(assessment, falling_timeframes)
                    )
            except (RuntimeError, ValueError):
                LOGGER.exception("Long watch scan failed for %s", instrument_id)

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
        command_match = COMMAND_PATTERN.fullmatch(message_text.strip())
        if command_match is None:
            return
        command_name = command_match.group(1).lower()
        requested_symbol = command_match.group(2)
        if requested_symbol is None:
            self._notifier.send(f"Użycie: /{command_name} BTCUSDT")
            return
        try:
            instrument_id = normalize_okx_instrument_id(requested_symbol)
            if command_name == "szpont":
                self._notifier.send(build_szpont_message(self._analyse(instrument_id)))
            elif command_name == "dodaj":
                self._add_dynamic_instrument(instrument_id)
            else:
                self._start_long_watch(instrument_id)
        except (RuntimeError, ValueError) as error:
            LOGGER.warning("Telegram command failed for %s: %s", requested_symbol, error)
            self._notifier.send(
                f"Nie udało się obsłużyć {requested_symbol.upper()}: {error}"
            )

    def _analyse(self, instrument_id: str) -> SzpontAssessment:
        candles_by_timeframe = {
            timeframe: self._market_data_client.get_candles(instrument_id, timeframe)
            for timeframe in SZPONT_TIMEFRAMES
        }
        return analyse_szpont(
            instrument_id,
            candles_by_timeframe,
            self._minimum_normalized_histogram_slope,
        )

    def _add_dynamic_instrument(self, instrument_id: str) -> None:
        candles = self._market_data_client.get_candles(instrument_id, "1H")
        if not any(candle.is_confirmed for candle in candles):
            raise ValueError("OKX nie zwrócił zamkniętych świec dla tego instrumentu")
        instrument_ids = self._load_instrument_ids(DYNAMIC_INSTRUMENTS_STATE_KEY)
        if instrument_id in instrument_ids:
            self._notifier.send(f"{instrument_id} już jest na liście skanera.")
            return
        instrument_ids.append(instrument_id)
        self._save_instrument_ids(DYNAMIC_INSTRUMENTS_STATE_KEY, instrument_ids)
        self._notifier.send(
            f"✅ Dodano {instrument_id} do skanera bez restartu. "
            "Wpis jest zapisany w SQLite i przetrwa restart."
        )

    def _start_long_watch(self, instrument_id: str) -> None:
        assessment = self._analyse(instrument_id)
        instrument_ids = self._load_instrument_ids(LONG_WATCH_INSTRUMENTS_STATE_KEY)
        already_watched = instrument_id in instrument_ids
        if not already_watched:
            instrument_ids.append(instrument_id)
            self._save_instrument_ids(
                LONG_WATCH_INSTRUMENTS_STATE_KEY, instrument_ids
            )
        dynamic_ids = self._load_instrument_ids(DYNAMIC_INSTRUMENTS_STATE_KEY)
        if instrument_id not in dynamic_ids:
            dynamic_ids.append(instrument_id)
            self._save_instrument_ids(DYNAMIC_INSTRUMENTS_STATE_KEY, dynamic_ids)
        self._prime_long_watch_state(assessment)
        status = (
            "już był obserwowany; odświeżono punkt bazowy"
            if already_watched
            else "włączony"
        )
        self._notifier.send(
            "\n".join(
                (
                    f"👁 LONG WATCH {status} — {instrument_id}",
                    "Alert pojawi się, gdy na nowej zamkniętej świecy histogram "
                    "1H, 2H, 4H lub 1D przejdzie z niespadającego w spadający.",
                    f"Stan teraz: {assessment.explanation}",
                    "Bot tylko rekomenduje ochronę zysku; nie wykonuje transakcji ani wypłat.",
                )
            )
        )

    def _prime_long_watch_state(self, assessment: SzpontAssessment) -> None:
        for timeframe_assessment in assessment.timeframe_assessments:
            self._save_long_watch_timeframe_state(
                assessment.instrument_id,
                timeframe_assessment.timeframe,
                timeframe_assessment.candle_timestamp_ms,
                timeframe_assessment.normalized_histogram_slope
                < -self._minimum_normalized_histogram_slope,
            )

    def _update_long_watch_state(
        self, assessment: SzpontAssessment
    ) -> tuple[str, ...]:
        falling_timeframes: list[str] = []
        for timeframe_assessment in assessment.timeframe_assessments:
            previous_state = self._load_long_watch_timeframe_state(
                assessment.instrument_id, timeframe_assessment.timeframe
            )
            is_falling = (
                timeframe_assessment.normalized_histogram_slope
                < -self._minimum_normalized_histogram_slope
            )
            if previous_state is None:
                self._save_long_watch_timeframe_state(
                    assessment.instrument_id,
                    timeframe_assessment.timeframe,
                    timeframe_assessment.candle_timestamp_ms,
                    is_falling,
                )
                continue
            previous_timestamp, was_falling = previous_state
            if timeframe_assessment.candle_timestamp_ms <= previous_timestamp:
                continue
            if is_falling and not was_falling:
                falling_timeframes.append(timeframe_assessment.timeframe)
            self._save_long_watch_timeframe_state(
                assessment.instrument_id,
                timeframe_assessment.timeframe,
                timeframe_assessment.candle_timestamp_ms,
                is_falling,
            )
        return tuple(falling_timeframes)

    def _long_watch_state_key(self, instrument_id: str, timeframe: str) -> str:
        return f"{LONG_WATCH_TIMEFRAME_STATE_PREFIX}:{instrument_id}:{timeframe}"

    def _load_long_watch_timeframe_state(
        self, instrument_id: str, timeframe: str
    ) -> tuple[int, bool] | None:
        raw_state = self._state_store.get_runtime_state(
            self._long_watch_state_key(instrument_id, timeframe)
        )
        if raw_state is None:
            return None
        try:
            state = json.loads(raw_state)
            return int(state["candle_timestamp_ms"]), bool(state["is_falling"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            LOGGER.warning("Ignoring invalid long-watch state for %s %s", instrument_id, timeframe)
            return None

    def _save_long_watch_timeframe_state(
        self,
        instrument_id: str,
        timeframe: str,
        candle_timestamp_ms: int,
        is_falling: bool,
    ) -> None:
        self._state_store.save_runtime_state(
            self._long_watch_state_key(instrument_id, timeframe),
            json.dumps(
                {
                    "candle_timestamp_ms": candle_timestamp_ms,
                    "is_falling": is_falling,
                },
                separators=(",", ":"),
            ),
        )

    def _load_instrument_ids(self, state_key: str) -> list[str]:
        raw_value = self._state_store.get_runtime_state(state_key)
        if raw_value is None:
            return []
        try:
            values = json.loads(raw_value)
        except json.JSONDecodeError:
            LOGGER.warning("Ignoring invalid runtime instrument list: %s", state_key)
            return []
        if not isinstance(values, list):
            return []
        return list(
            dict.fromkeys(
                value for value in values if isinstance(value, str) and value
            )
        )

    def _save_instrument_ids(self, state_key: str, instrument_ids: list[str]) -> None:
        self._state_store.save_runtime_state(
            state_key, json.dumps(instrument_ids, separators=(",", ":"))
        )
