from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ma_alert_bot.models import Candle


MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
AVERAGE_TRUE_RANGE_PERIOD = 14
SIMPLE_MOVING_AVERAGE_PERIODS = (20, 50, 100, 200)
MINIMUM_CONFIRMED_CANDLES = max(SIMPLE_MOVING_AVERAGE_PERIODS) + 2
DEFAULT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE = 0.001
SZPONT_TIMEFRAMES = ("1H", "2H", "4H", "1D")


class MomentumState(StrEnum):
    BEARISH_EXPANSION = "bearish_expansion"
    BEARISH_RECOVERY = "bearish_recovery"
    BULLISH_CROSS = "bullish_cross"
    BULLISH_EXPANSION = "bullish_expansion"
    BULLISH_DECELERATION = "bullish_deceleration"
    BEARISH_CROSS = "bearish_cross"
    NEUTRAL_COMPRESSION = "neutral_compression"


class SynchronizationState(StrEnum):
    RECOVERY_PREPARATION = "recovery_preparation"
    EARLY_BULLISH_SYNCHRONIZATION = "early_bullish_synchronization"
    CONFIRMED_BULLISH_EXPANSION = "confirmed_bullish_expansion"
    BULLISH_H4_VETO = "bullish_h4_veto"
    EARLY_BEARISH_SYNCHRONIZATION = "early_bearish_synchronization"
    CONFIRMED_BEARISH_EXPANSION = "confirmed_bearish_expansion"
    BEARISH_H4_VETO = "bearish_h4_veto"
    MIXED = "mixed"


class MovingAverageStructure(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"


@dataclass(frozen=True)
class TimeframeMomentumAssessment:
    timeframe: str
    candle_timestamp_ms: int
    closing_price: float
    average_true_range: float
    macd_line: float
    signal_line: float
    histogram: float
    previous_histogram: float
    normalized_histogram_slope: float
    momentum_state: MomentumState
    moving_average_structure: MovingAverageStructure
    moving_average_levels: dict[int, float]
    moving_average_slopes: dict[int, float]
    overhead_resistance_periods: tuple[int, ...]
    underlying_support_periods: tuple[int, ...]


@dataclass(frozen=True)
class SzpontAssessment:
    instrument_id: str
    synchronization_state: SynchronizationState
    timeframe_assessments: tuple[TimeframeMomentumAssessment, ...]
    explanation: str


def calculate_exponential_moving_average(
    values: Sequence[float], period: int
) -> list[float]:
    if not values:
        return []
    smoothing_multiplier = 2.0 / (period + 1.0)
    exponential_moving_average_values = [float(values[0])]
    for value in values[1:]:
        previous_value = exponential_moving_average_values[-1]
        exponential_moving_average_values.append(
            previous_value + smoothing_multiplier * (value - previous_value)
        )
    return exponential_moving_average_values


def calculate_macd_series(
    closing_prices: Sequence[float],
) -> tuple[list[float], list[float], list[float]]:
    fast_average_values = calculate_exponential_moving_average(
        closing_prices, MACD_FAST_PERIOD
    )
    slow_average_values = calculate_exponential_moving_average(
        closing_prices, MACD_SLOW_PERIOD
    )
    macd_line_values = [
        fast_value - slow_value
        for fast_value, slow_value in zip(
            fast_average_values, slow_average_values, strict=True
        )
    ]
    signal_line_values = calculate_exponential_moving_average(
        macd_line_values, MACD_SIGNAL_PERIOD
    )
    histogram_values = [
        macd_value - signal_value
        for macd_value, signal_value in zip(
            macd_line_values, signal_line_values, strict=True
        )
    ]
    return macd_line_values, signal_line_values, histogram_values


def calculate_latest_average_true_range(candles: Sequence[Candle]) -> float:
    if len(candles) <= AVERAGE_TRUE_RANGE_PERIOD:
        raise ValueError("Not enough candles to calculate ATR")
    true_ranges: list[float] = []
    for candle_index in range(1, len(candles)):
        candle = candles[candle_index]
        previous_close = candles[candle_index - 1].closing_price
        true_ranges.append(
            max(
                candle.highest_price - candle.lowest_price,
                abs(candle.highest_price - previous_close),
                abs(candle.lowest_price - previous_close),
            )
        )
    average_true_range = sum(
        true_ranges[:AVERAGE_TRUE_RANGE_PERIOD]
    ) / AVERAGE_TRUE_RANGE_PERIOD
    for true_range in true_ranges[AVERAGE_TRUE_RANGE_PERIOD:]:
        average_true_range = (
            average_true_range * (AVERAGE_TRUE_RANGE_PERIOD - 1) + true_range
        ) / AVERAGE_TRUE_RANGE_PERIOD
    return average_true_range


def calculate_latest_simple_moving_average(
    closing_prices: Sequence[float], period: int
) -> float:
    return sum(closing_prices[-period:]) / period


def classify_momentum_state(
    current_histogram: float,
    previous_histogram: float,
    average_true_range: float,
    minimum_normalized_histogram_slope: float,
) -> tuple[MomentumState, float]:
    if average_true_range <= 0:
        raise ValueError("ATR must be positive")
    normalized_histogram_slope = (
        current_histogram - previous_histogram
    ) / average_true_range
    if previous_histogram <= 0 < current_histogram:
        return MomentumState.BULLISH_CROSS, normalized_histogram_slope
    if previous_histogram >= 0 > current_histogram:
        return MomentumState.BEARISH_CROSS, normalized_histogram_slope
    if abs(normalized_histogram_slope) < minimum_normalized_histogram_slope:
        return MomentumState.NEUTRAL_COMPRESSION, normalized_histogram_slope
    if normalized_histogram_slope > 0:
        if current_histogram < 0:
            return MomentumState.BEARISH_RECOVERY, normalized_histogram_slope
        return MomentumState.BULLISH_EXPANSION, normalized_histogram_slope
    if current_histogram > 0:
        return MomentumState.BULLISH_DECELERATION, normalized_histogram_slope
    return MomentumState.BEARISH_EXPANSION, normalized_histogram_slope


def classify_moving_average_structure(
    closing_price: float, moving_average_levels: dict[int, float]
) -> MovingAverageStructure:
    ordered_periods = SIMPLE_MOVING_AVERAGE_PERIODS
    ordered_values = [moving_average_levels[period] for period in ordered_periods]
    if closing_price > max(ordered_values) and ordered_values == sorted(
        ordered_values, reverse=True
    ):
        return MovingAverageStructure.BULLISH
    if closing_price < min(ordered_values) and ordered_values == sorted(ordered_values):
        return MovingAverageStructure.BEARISH
    return MovingAverageStructure.MIXED


def assess_timeframe(
    timeframe: str,
    candles: Sequence[Candle],
    minimum_normalized_histogram_slope: float = (
        DEFAULT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE
    ),
) -> TimeframeMomentumAssessment:
    confirmed_candles = [candle for candle in candles if candle.is_confirmed]
    if len(confirmed_candles) < MINIMUM_CONFIRMED_CANDLES:
        raise ValueError(
            f"{timeframe} requires at least {MINIMUM_CONFIRMED_CANDLES} confirmed candles"
        )
    closing_prices = [candle.closing_price for candle in confirmed_candles]
    macd_values, signal_values, histogram_values = calculate_macd_series(closing_prices)
    average_true_range = calculate_latest_average_true_range(confirmed_candles)
    momentum_state, normalized_histogram_slope = classify_momentum_state(
        histogram_values[-1],
        histogram_values[-2],
        average_true_range,
        minimum_normalized_histogram_slope,
    )
    moving_average_levels = {
        period: calculate_latest_simple_moving_average(closing_prices, period)
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
    }
    previous_moving_average_levels = {
        period: calculate_latest_simple_moving_average(closing_prices[:-1], period)
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
    }
    moving_average_slopes = {
        period: moving_average_levels[period] - previous_moving_average_levels[period]
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
    }
    closing_price = closing_prices[-1]
    overhead_resistance_periods = tuple(
        period
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
        if moving_average_levels[period] > closing_price
        and moving_average_slopes[period] <= 0
    )
    underlying_support_periods = tuple(
        period
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
        if moving_average_levels[period] < closing_price
        and moving_average_slopes[period] >= 0
    )
    return TimeframeMomentumAssessment(
        timeframe=timeframe,
        candle_timestamp_ms=confirmed_candles[-1].opening_timestamp_ms,
        closing_price=closing_price,
        average_true_range=average_true_range,
        macd_line=macd_values[-1],
        signal_line=signal_values[-1],
        histogram=histogram_values[-1],
        previous_histogram=histogram_values[-2],
        normalized_histogram_slope=normalized_histogram_slope,
        momentum_state=momentum_state,
        moving_average_structure=classify_moving_average_structure(
            closing_price, moving_average_levels
        ),
        moving_average_levels=moving_average_levels,
        moving_average_slopes=moving_average_slopes,
        overhead_resistance_periods=overhead_resistance_periods,
        underlying_support_periods=underlying_support_periods,
    )


def determine_synchronization_state(
    assessments_by_timeframe: dict[str, TimeframeMomentumAssessment],
) -> tuple[SynchronizationState, str]:
    bullish_states = {
        MomentumState.BEARISH_RECOVERY,
        MomentumState.BULLISH_CROSS,
        MomentumState.BULLISH_EXPANSION,
    }
    bearish_states = {
        MomentumState.BULLISH_DECELERATION,
        MomentumState.BEARISH_CROSS,
        MomentumState.BEARISH_EXPANSION,
    }
    one_hour_state = assessments_by_timeframe["1H"].momentum_state
    two_hour_state = assessments_by_timeframe["2H"].momentum_state
    four_hour_state = assessments_by_timeframe["4H"].momentum_state
    daily_state = assessments_by_timeframe["1D"].momentum_state

    if (
        one_hour_state is MomentumState.BEARISH_RECOVERY
        and two_hour_state is MomentumState.BEARISH_RECOVERY
        and four_hour_state is MomentumState.BEARISH_RECOVERY
    ):
        return (
            SynchronizationState.RECOVERY_PREPARATION,
            "1H, 2H i 4H odbudowują momentum pod linią zera.",
        )
    if one_hour_state in bullish_states and two_hour_state in bullish_states:
        if four_hour_state not in bullish_states:
            return (
                SynchronizationState.BULLISH_H4_VETO,
                "1H i 2H rosną, ale H4 nie potwierdza ruchu.",
            )
        if daily_state not in bearish_states:
            return (
                SynchronizationState.CONFIRMED_BULLISH_EXPANSION,
                "Momentum 1H, 2H i 4H jest zgodne, a D1 nie przeczy ruchowi.",
            )
        return (
            SynchronizationState.EARLY_BULLISH_SYNCHRONIZATION,
            "Niższe interwały są zgodne, ale D1 nadal hamuje układ.",
        )
    if one_hour_state in bearish_states and two_hour_state in bearish_states:
        if four_hour_state not in bearish_states:
            return (
                SynchronizationState.BEARISH_H4_VETO,
                "1H i 2H słabną, ale H4 nie potwierdza ruchu spadkowego.",
            )
        if daily_state not in bullish_states:
            return (
                SynchronizationState.CONFIRMED_BEARISH_EXPANSION,
                "Momentum 1H, 2H i 4H spada, a D1 nie przeczy ruchowi.",
            )
        return (
            SynchronizationState.EARLY_BEARISH_SYNCHRONIZATION,
            "Niższe interwały słabną, ale D1 nadal wspiera stronę byczą.",
        )
    if one_hour_state in bullish_states:
        return (
            SynchronizationState.EARLY_BULLISH_SYNCHRONIZATION,
            "Zapłon pojawił się na 1H, lecz 2H i H4 nie są jeszcze zgodne.",
        )
    if one_hour_state in bearish_states:
        return (
            SynchronizationState.EARLY_BEARISH_SYNCHRONIZATION,
            "Osłabienie pojawiło się na 1H, lecz 2H i H4 nie są jeszcze zgodne.",
        )
    return SynchronizationState.MIXED, "Momentum pozostaje mieszane lub skompresowane."


def analyse_szpont(
    instrument_id: str,
    candles_by_timeframe: dict[str, Sequence[Candle]],
    minimum_normalized_histogram_slope: float = (
        DEFAULT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE
    ),
) -> SzpontAssessment:
    timeframe_assessments = tuple(
        assess_timeframe(
            timeframe,
            candles_by_timeframe[timeframe],
            minimum_normalized_histogram_slope,
        )
        for timeframe in SZPONT_TIMEFRAMES
    )
    assessments_by_timeframe = {
        assessment.timeframe: assessment for assessment in timeframe_assessments
    }
    synchronization_state, explanation = determine_synchronization_state(
        assessments_by_timeframe
    )
    return SzpontAssessment(
        instrument_id=instrument_id,
        synchronization_state=synchronization_state,
        timeframe_assessments=timeframe_assessments,
        explanation=explanation,
    )
