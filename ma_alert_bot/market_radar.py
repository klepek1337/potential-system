import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from ma_alert_bot.okx_client import (
    OkxMarketDataClient,
    PerpetualInstrument,
    PerpetualTicker,
)
from ma_alert_bot.state_store import AlertStateStore
from ma_alert_bot.szpont_analysis import (
    SZPONT_TIMEFRAMES,
    LongOverheatState,
    MomentumState,
    MovingAverageStructure,
    TimeframeMomentumAssessment,
    assess_timeframe,
)

LOGGER = logging.getLogger(__name__)
MILLISECONDS_PER_DAY = 86_400_000
SECONDS_PER_HOUR = 3_600
SMA_FILTER_PERIOD = 20
TELEGRAM_SAFE_MESSAGE_LENGTH = 3_900
RADAR_LAST_SCAN_SLOT_STATE_KEY = "market_radar:last_scan_slot"
RADAR_SIGNAL_STATE_KEY_PREFIX = "market_radar:signal:"

RISING_MOMENTUM_STATES = frozenset(
    {
        MomentumState.BEARISH_RECOVERY,
        MomentumState.BULLISH_CROSS,
        MomentumState.BULLISH_EXPANSION,
    }
)
FALLING_MOMENTUM_STATES = frozenset(
    {
        MomentumState.BULLISH_DECELERATION,
        MomentumState.BEARISH_CROSS,
        MomentumState.BEARISH_EXPANSION,
    }
)


class MessageSender(Protocol):
    def send(self, message: str) -> None: ...


class MarketRadarSignal(StrEnum):
    NONE = "none"
    BUILDING = "building"
    STRONG = "strong"
    FULL_SYNC = "a_plus_full_sync"


SIGNAL_RANK = {
    MarketRadarSignal.NONE: 0,
    MarketRadarSignal.BUILDING: 1,
    MarketRadarSignal.STRONG: 2,
    MarketRadarSignal.FULL_SYNC: 3,
}


@dataclass(frozen=True)
class MarketRadarCandidate:
    instrument_id: str
    signal: MarketRadarSignal
    assessments_by_timeframe: dict[str, TimeframeMomentumAssessment]
    quote_notional_24h: float
    spread_ratio: float


def passes_bullish_h4_moving_average_filter(
    assessment: TimeframeMomentumAssessment,
) -> bool:
    sma20 = assessment.moving_average_levels[SMA_FILTER_PERIOD]
    sma20_slope = assessment.moving_average_slopes[SMA_FILTER_PERIOD]
    return (
        assessment.closing_price >= sma20
        and sma20_slope > 0
        and assessment.moving_average_structure is not MovingAverageStructure.BEARISH
    )


def classify_market_radar_signal(
    assessments_by_timeframe: dict[str, TimeframeMomentumAssessment],
    full_sync_confirmation_candles: int,
) -> MarketRadarSignal:
    one_hour = assessments_by_timeframe["1H"]
    two_hour = assessments_by_timeframe["2H"]
    four_hour = assessments_by_timeframe["4H"]
    daily = assessments_by_timeframe["1D"]

    all_rising = all(
        assessment.momentum_state in RISING_MOMENTUM_STATES
        for assessment in (one_hour, two_hour, four_hour, daily)
    )
    full_sync_confirmed = all(
        assessment.consecutive_rising_histogram_candles
        >= full_sync_confirmation_candles
        for assessment in (one_hour, two_hour, four_hour, daily)
    )
    price_not_overheated = all(
        assessment.long_overheat_state is not LongOverheatState.HIGH
        for assessment in (one_hour, two_hour, four_hour, daily)
    )
    h4_sma_filter_passes = passes_bullish_h4_moving_average_filter(four_hour)

    if (
        all_rising
        and full_sync_confirmed
        and price_not_overheated
        and h4_sma_filter_passes
    ):
        return MarketRadarSignal.FULL_SYNC

    lower_timeframes_rising = all(
        assessment.momentum_state in RISING_MOMENTUM_STATES
        for assessment in (one_hour, two_hour)
    )
    if (
        lower_timeframes_rising
        and four_hour.momentum_state in RISING_MOMENTUM_STATES
        and daily.momentum_state not in FALLING_MOMENTUM_STATES
        and h4_sma_filter_passes
    ):
        return MarketRadarSignal.STRONG

    h4_is_neutral_or_recovering = four_hour.momentum_state in {
        MomentumState.NEUTRAL_COMPRESSION,
        MomentumState.BEARISH_RECOVERY,
    }
    lower_timeframes_not_extreme = all(
        assessment.long_overheat_state is not LongOverheatState.HIGH
        for assessment in (one_hour, two_hour)
    )
    if (
        lower_timeframes_rising
        and h4_is_neutral_or_recovering
        and lower_timeframes_not_extreme
    ):
        return MarketRadarSignal.BUILDING

    return MarketRadarSignal.NONE


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
    return tuple(
        sorted(eligible, key=lambda pair: pair[1].quote_notional_24h, reverse=True)
    )


def should_notify_signal(
    previous_signal_value: str | None, current_signal: MarketRadarSignal
) -> bool:
    try:
        previous_signal = MarketRadarSignal(previous_signal_value)
    except (TypeError, ValueError):
        previous_signal = MarketRadarSignal.NONE
    return (
        current_signal is not MarketRadarSignal.NONE
        and SIGNAL_RANK[current_signal] > SIGNAL_RANK[previous_signal]
    )


def build_market_radar_report(candidates: list[MarketRadarCandidate]) -> str:
    headings = {
        MarketRadarSignal.FULL_SYNC: "💎 A+ FULL SYNC",
        MarketRadarSignal.STRONG: "🔥 STRONG",
        MarketRadarSignal.BUILDING: "🟡 BUILDING",
    }
    lines = ["📡 SZPONT — nowe setupy perpetual"]
    for signal in (
        MarketRadarSignal.FULL_SYNC,
        MarketRadarSignal.STRONG,
        MarketRadarSignal.BUILDING,
    ):
        matching = [candidate for candidate in candidates if candidate.signal is signal]
        if not matching:
            continue
        lines.extend(("", headings[signal]))
        for candidate in matching:
            assessments = candidate.assessments_by_timeframe
            state_summary = " | ".join(
                f"{timeframe} {assessments[timeframe].momentum_state.value}"
                for timeframe in SZPONT_TIMEFRAMES
            )
            h4 = assessments["4H"]
            lines.extend(
                (
                    f"• {candidate.instrument_id}",
                    f"  {state_summary}",
                    "  H4: "
                    f"{h4.price_distance_from_sma20_atr:+.2f} ATR od SMA20; "
                    f"MACD−Signal {h4.macd_signal_gap_atr:+.3f} ATR",
                    "  Płynność 24h: "
                    f"{candidate.quote_notional_24h / 1_000_000:.1f} mln USDT; "
                    f"spread {candidate.spread_ratio * 100:.3f}%",
                )
            )
    lines.extend(("", "Tylko zamknięte świece. To alert układu, nie zlecenie."))
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
        full_sync_confirmation_candles: int,
    ) -> None:
        self._market_data_client = market_data_client
        self._state_store = state_store
        self._notifier = notifier
        self._enabled = enabled
        self._minimum_normalized_histogram_slope = (
            minimum_normalized_histogram_slope
        )
        self._minimum_quote_notional_24h = minimum_quote_notional_24h
        self._maximum_spread_ratio = maximum_spread_ratio
        self._minimum_listing_age_days = minimum_listing_age_days
        self._candle_confirmation_delay_seconds = candle_confirmation_delay_seconds
        self._request_delay_seconds = request_delay_seconds
        self._full_sync_confirmation_candles = full_sync_confirmation_candles

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
            self._minimum_listing_age_days,
            self._minimum_quote_notional_24h,
            self._maximum_spread_ratio,
        )
        new_candidates: list[MarketRadarCandidate] = []
        evaluated_signals: list[tuple[str, MarketRadarSignal]] = []
        for instrument, ticker in eligible:
            try:
                assessments = self._assess_instrument(instrument.instrument_id)
                signal = classify_market_radar_signal(
                    assessments, self._full_sync_confirmation_candles
                )
            except Exception:
                LOGGER.exception("Market radar failed for %s", instrument.instrument_id)
                continue
            state_key = RADAR_SIGNAL_STATE_KEY_PREFIX + instrument.instrument_id
            previous_signal = self._state_store.get_runtime_state(state_key)
            evaluated_signals.append((state_key, signal))
            if not should_notify_signal(previous_signal, signal):
                continue
            new_candidates.append(
                MarketRadarCandidate(
                    instrument_id=instrument.instrument_id,
                    signal=signal,
                    assessments_by_timeframe=assessments,
                    quote_notional_24h=ticker.quote_notional_24h,
                    spread_ratio=ticker.spread_ratio,
                )
            )
        if new_candidates:
            report = build_market_radar_report(new_candidates)
            for message in split_telegram_message(report):
                self._notifier.send(message)
        for state_key, signal in evaluated_signals:
            self._state_store.save_runtime_state(state_key, signal.value)

    def _assess_instrument(
        self, instrument_id: str
    ) -> dict[str, TimeframeMomentumAssessment]:
        assessments = {}
        for timeframe in SZPONT_TIMEFRAMES:
            candles = self._market_data_client.get_candles(instrument_id, timeframe)
            assessments[timeframe] = assess_timeframe(
                timeframe,
                candles,
                self._minimum_normalized_histogram_slope,
            )
            if self._request_delay_seconds > 0:
                time.sleep(self._request_delay_seconds)
        return assessments
