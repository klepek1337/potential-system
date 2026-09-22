import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ma_alert_bot.models import Candle
from ma_alert_bot.okx_client import OkxMarketDataClient, PerpetualInstrument, PerpetualTicker
from ma_alert_bot.setup_scoring import GRADE_RANK, SetupGrade, SetupScore, score_setup
from ma_alert_bot.state_store import AlertStateStore
from ma_alert_bot.szpont_analysis import (
    SZPONT_TIMEFRAMES,
    TimeframeMomentumAssessment,
    assess_live_timeframe,
    assess_timeframe,
)

LOGGER = logging.getLogger(__name__)
MILLISECONDS_PER_DAY = 86_400_000
SECONDS_PER_HOUR = 3_600
TELEGRAM_SAFE_MESSAGE_LENGTH = 3_900
MINIMUM_DAILY_CONFIRMED_CANDLES = 60
DAILY_TIMEFRAME = "1D"
RADAR_LAST_SCAN_SLOT_STATE_KEY = "market_radar:v3:last_scan_slot"
RADAR_SIGNAL_STATE_KEY_PREFIX = "market_radar:v3:signal:"


class MessageSender(Protocol):
    def send(self, message: str) -> None: ...


@dataclass(frozen=True)
class MarketRadarCandidate:
    instrument_id: str
    score: SetupScore
    quote_notional_24h: float
    spread_ratio: float


class InsufficientRadarHistoryError(ValueError):
    pass


def select_eligible_instruments(
    instruments: tuple[PerpetualInstrument, ...],
    tickers: dict[str, PerpetualTicker],
    current_timestamp_ms: int,
    minimum_listing_age_days: int,
    minimum_quote_notional_24h: float,
    maximum_spread_ratio: float,
) -> tuple[tuple[PerpetualInstrument, PerpetualTicker], ...]:
    minimum_listing_age_ms = minimum_listing_age_days * MILLISECONDS_PER_DAY
    eligible = []
    for instrument in instruments:
        ticker = tickers.get(instrument.instrument_id)
        if ticker is None:
            continue
        listing_age_ms = current_timestamp_ms - instrument.listing_timestamp_ms
        if (
            listing_age_ms < minimum_listing_age_ms
            or ticker.quote_notional_24h < minimum_quote_notional_24h
            or ticker.spread_ratio > maximum_spread_ratio
        ):
            continue
        eligible.append((instrument, ticker))
    return tuple(sorted(eligible, key=lambda pair: pair[1].quote_notional_24h, reverse=True))


def _parse_previous_state(previous_state_value: str | None) -> tuple[str | None, SetupGrade]:
    if not previous_state_value:
        return None, SetupGrade.NONE
    try:
        direction, grade_value = previous_state_value.split(":", maxsplit=1)
        return direction, SetupGrade(grade_value)
    except (ValueError, AttributeError):
        return None, SetupGrade.NONE


def should_notify_score(previous_state_value: str | None, score: SetupScore) -> bool:
    previous_direction, previous_grade = _parse_previous_state(previous_state_value)
    return score.grade is not SetupGrade.NONE and (
        previous_direction != score.direction.value
        or GRADE_RANK[score.grade] > GRADE_RANK[previous_grade]
    )


def _format_periods(periods: tuple[int, ...]) -> str:
    return "/".join(f"SMA{period}" for period in periods) or "brak"


def build_market_radar_report(candidates: list[MarketRadarCandidate]) -> str:
    headings = {
        SetupGrade.FULL_SYNC: "💎 A+ FULL SYNC",
        SetupGrade.STRONG: "🔥 STRONG",
        SetupGrade.GOOD: "🟢 GOOD",
        SetupGrade.VALID: "🟡 VALID",
        SetupGrade.WEAK: "⚪ WEAK",
    }
    lines = ["📡 SZPONT — nowe setupy perpetual"]
    for grade in (
        SetupGrade.FULL_SYNC,
        SetupGrade.STRONG,
        SetupGrade.GOOD,
        SetupGrade.VALID,
        SetupGrade.WEAK,
    ):
        matching = [candidate for candidate in candidates if candidate.score.grade is grade]
        if not matching:
            continue
        lines.extend(("", headings[grade]))
        for candidate in sorted(matching, key=lambda item: item.score.total, reverse=True):
            score = candidate.score
            breakdown = score.breakdown
            direction_summary = " | ".join(
                f"{timeframe} {score.histogram_directions[timeframe].value}"
                + (" LIVE" if timeframe == DAILY_TIMEFRAME else "")
                for timeframe in SZPONT_TIMEFRAMES
            )
            nearest_sma = (
                f"SMA{score.nearest_sma_period} {score.nearest_sma_distance_percent:.3f}%"
                if score.nearest_sma_period is not None
                and score.nearest_sma_distance_percent is not None
                else "brak"
            )
            lines.extend(
                (
                    f"• {candidate.instrument_id} — "
                    f"{score.direction.value.upper()} {score.total}/28",
                    f"  {direction_summary}",
                    "  Sync: " + "/".join(score.synchronized_timeframes),
                    f"  Najbliższa 1H: {nearest_sma}; "
                    f"klaster: {_format_periods(score.nearby_sma_periods)}",
                    "  Struktura: "
                    f"sync {breakdown.synchronization} + bliskość {breakdown.sma_proximity} "
                    f"+ S/R {breakdown.support_resistance} + klaster {breakdown.sma_cluster} "
                    f"+ cross {breakdown.sma_cross} + wybicie {breakdown.price_break} "
                    f"+ respekt {breakdown.respect}",
                    f"  Cross SMA: {_format_periods(score.crossed_sma_periods)}; "
                    f"cena przebiła: {_format_periods(score.price_broken_sma_periods)}",
                    "  Płynność 24h: "
                    f"{candidate.quote_notional_24h / 1_000_000:.1f} mln USDT; "
                    f"spread {candidate.spread_ratio * 100:.3f}%",
                )
            )
    lines.extend(
        (
            "",
            "1H/2H/4H: świece zamknięte. 1D LIVE: aktualna cena jako tymczasowe zamknięcie.",
            "To alert układu, nie zlecenie.",
        )
    )
    return "\n".join(lines)


def split_telegram_message(message: str) -> tuple[str, ...]:
    if len(message) <= TELEGRAM_SAFE_MESSAGE_LENGTH:
        return (message,)
    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0
    for line in message.splitlines():
        added_length = len(line) + 1
        if current_lines and current_length + added_length > TELEGRAM_SAFE_MESSAGE_LENGTH:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_length = 0
        current_lines.append(line)
        current_length += added_length
    if current_lines:
        chunks.append("\n".join(current_lines))
    return tuple(chunks)


class MarketRadar:
    def __init__(
        self,
        market_data_client: OkxMarketDataClient,
        state_store: AlertStateStore,
        notifier: MessageSender,
        enabled: bool,
        minimum_normalized_histogram_slope: float,
        minimum_quote_notional_24h: float,
        maximum_spread_ratio: float,
        minimum_listing_age_days: int,
        candle_confirmation_delay_seconds: int,
        request_delay_seconds: float,
    ) -> None:
        self._market_data_client = market_data_client
        self._state_store = state_store
        self._notifier = notifier
        self._enabled = enabled
        self._minimum_normalized_histogram_slope = minimum_normalized_histogram_slope
        self._minimum_quote_notional_24h = minimum_quote_notional_24h
        self._maximum_spread_ratio = maximum_spread_ratio
        self._minimum_listing_age_days = minimum_listing_age_days
        self._candle_confirmation_delay_seconds = candle_confirmation_delay_seconds
        self._request_delay_seconds = request_delay_seconds

    def scan_if_due(self, current_time: datetime | None = None) -> None:
        if not self._enabled:
            return
        current_time = current_time or datetime.now(UTC)
        seconds_into_hour = current_time.minute * 60 + current_time.second
        if seconds_into_hour < self._candle_confirmation_delay_seconds:
            return
        scan_slot = str(int(current_time.timestamp()) // SECONDS_PER_HOUR)
        if self._state_store.get_runtime_state(RADAR_LAST_SCAN_SLOT_STATE_KEY) == scan_slot:
            return
        self._scan(current_time)
        self._state_store.save_runtime_state(RADAR_LAST_SCAN_SLOT_STATE_KEY, scan_slot)

    def _scan(self, current_time: datetime) -> None:
        instruments = self._market_data_client.get_live_usdt_perpetuals()
        tickers = self._market_data_client.get_swap_tickers()
        eligible = select_eligible_instruments(
            instruments,
            tickers,
            int(current_time.timestamp() * 1000),
            max(self._minimum_listing_age_days, MINIMUM_DAILY_CONFIRMED_CANDLES),
            self._minimum_quote_notional_24h,
            self._maximum_spread_ratio,
        )
        new_candidates: list[MarketRadarCandidate] = []
        evaluated_states: list[tuple[str, str]] = []
        for instrument, ticker in eligible:
            try:
                assessments, one_hour_candles = self._assess_instrument(
                    instrument.instrument_id, ticker.last_price
                )
                score = score_setup(
                    assessments,
                    one_hour_candles,
                    ticker.last_price,
                    self._minimum_normalized_histogram_slope,
                )
            except (InsufficientRadarHistoryError, ValueError) as error:
                LOGGER.info("Market radar skipped %s: %s", instrument.instrument_id, error)
                continue
            except Exception:
                LOGGER.exception("Market radar failed for %s", instrument.instrument_id)
                continue
            state_key = RADAR_SIGNAL_STATE_KEY_PREFIX + instrument.instrument_id
            previous_state = self._state_store.get_runtime_state(state_key)
            current_state = (
                score.state_value
                if score.grade is not SetupGrade.NONE
                else SetupGrade.NONE.value
            )
            evaluated_states.append((state_key, current_state))
            if not should_notify_score(previous_state, score):
                continue
            new_candidates.append(
                MarketRadarCandidate(
                    instrument_id=instrument.instrument_id,
                    score=score,
                    quote_notional_24h=ticker.quote_notional_24h,
                    spread_ratio=ticker.spread_ratio,
                )
            )
        if new_candidates:
            report = build_market_radar_report(new_candidates)
            for message in split_telegram_message(report):
                self._notifier.send(message)
        for state_key, state in evaluated_states:
            self._state_store.save_runtime_state(state_key, state)

    def _assess_instrument(
        self, instrument_id: str, current_price: float
    ) -> tuple[dict[str, TimeframeMomentumAssessment], tuple[Candle, ...]]:
        assessments: dict[str, TimeframeMomentumAssessment] = {}
        one_hour_candles: tuple[Candle, ...] = ()
        for timeframe in SZPONT_TIMEFRAMES:
            candles = self._market_data_client.get_candles(instrument_id, timeframe)
            if timeframe == "1H":
                one_hour_candles = candles
            if timeframe == DAILY_TIMEFRAME:
                confirmed_candle_count = sum(candle.is_confirmed for candle in candles)
                if confirmed_candle_count < MINIMUM_DAILY_CONFIRMED_CANDLES:
                    raise InsufficientRadarHistoryError(
                        f"1D has {confirmed_candle_count}/"
                        f"{MINIMUM_DAILY_CONFIRMED_CANDLES} confirmed candles"
                    )
                assessments[timeframe] = assess_live_timeframe(
                    timeframe,
                    candles,
                    current_price,
                    self._minimum_normalized_histogram_slope,
                    minimum_candles=MINIMUM_DAILY_CONFIRMED_CANDLES + 1,
                )
            else:
                assessments[timeframe] = assess_timeframe(
                    timeframe,
                    candles,
                    self._minimum_normalized_histogram_slope,
                )
            if self._request_delay_seconds > 0:
                time.sleep(self._request_delay_seconds)
        return assessments, one_hour_candles
