from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ma_alert_bot.models import Candle
from ma_alert_bot.szpont_analysis import (
    SIMPLE_MOVING_AVERAGE_PERIODS,
    SZPONT_TIMEFRAMES,
    TimeframeMomentumAssessment,
    calculate_latest_simple_moving_average,
)

ENTRY_TIMEFRAME = "1H"
STRUCTURE_DISTANCE_LIMIT_PERCENT = 0.50
CROSS_WINDOW_CANDLES = 3


class SetupDirection(StrEnum):
    LONG = "long"
    SHORT = "short"


class HistogramDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class SetupGrade(StrEnum):
    NONE = "none"
    WEAK = "weak"
    VALID = "valid"
    GOOD = "good"
    STRONG = "strong"
    FULL_SYNC = "a_plus_full_sync"


GRADE_RANK = {
    SetupGrade.NONE: 0,
    SetupGrade.WEAK: 1,
    SetupGrade.VALID: 2,
    SetupGrade.GOOD: 3,
    SetupGrade.STRONG: 4,
    SetupGrade.FULL_SYNC: 5,
}


@dataclass(frozen=True)
class ScoreBreakdown:
    synchronization: int = 0
    sma_proximity: int = 0
    support_resistance: int = 0
    sma_cluster: int = 0
    sma_cross: int = 0
    price_break: int = 0
    respect: int = 0

    @property
    def total(self) -> int:
        return sum(
            (
                self.synchronization,
                self.sma_proximity,
                self.support_resistance,
                self.sma_cluster,
                self.sma_cross,
                self.price_break,
                self.respect,
            )
        )

    @property
    def has_structural_confirmation(self) -> bool:
        return any(
            points > 0
            for points in (
                self.sma_proximity,
                self.support_resistance,
                self.sma_cluster,
                self.sma_cross,
                self.price_break,
                self.respect,
            )
        )


@dataclass(frozen=True)
class SetupScore:
    direction: SetupDirection
    grade: SetupGrade
    breakdown: ScoreBreakdown
    histogram_directions: dict[str, HistogramDirection]
    synchronized_timeframes: tuple[str, ...]
    nearest_sma_period: int | None
    nearest_sma_distance_percent: float | None
    nearby_sma_periods: tuple[int, ...]
    crossed_sma_periods: tuple[int, ...]
    price_broken_sma_periods: tuple[int, ...]

    @property
    def total(self) -> int:
        return self.breakdown.total

    @property
    def state_value(self) -> str:
        return f"{self.direction.value}:{self.grade.value}"


def histogram_direction(
    assessment: TimeframeMomentumAssessment,
    minimum_normalized_histogram_slope: float,
) -> HistogramDirection:
    slope = assessment.normalized_histogram_slope
    if slope >= minimum_normalized_histogram_slope:
        return HistogramDirection.UP
    if slope <= -minimum_normalized_histogram_slope:
        return HistogramDirection.DOWN
    return HistogramDirection.FLAT


def synchronization_points(synchronized_timeframes: Sequence[str]) -> int:
    count = len(synchronized_timeframes)
    if count < 2:
        return 0
    base_points = {2: 4, 3: 7, 4: 10}[count]
    synchronized = set(synchronized_timeframes)
    chain_bonus = sum(
        left in synchronized and right in synchronized
        for left, right in (("1H", "2H"), ("2H", "4H"), ("4H", "1D"))
    )
    return base_points + min(chain_bonus, 2)


def classify_grade(points: int, has_structural_confirmation: bool) -> SetupGrade:
    if points < 4:
        return SetupGrade.NONE
    if points <= 8:
        return SetupGrade.WEAK
    if points <= 13:
        return SetupGrade.VALID
    if points <= 18:
        return SetupGrade.GOOD
    if not has_structural_confirmation:
        return SetupGrade.GOOD
    if points <= 23:
        return SetupGrade.STRONG
    return SetupGrade.FULL_SYNC


def _sma_series(
    confirmed_candles: Sequence[Candle], period: int
) -> dict[int, float]:
    closes = [candle.closing_price for candle in confirmed_candles]
    return {
        index: calculate_latest_simple_moving_average(closes[: index + 1], period)
        for index in range(period - 1, len(closes))
    }


def _cross_events(
    confirmed_candles: Sequence[Candle], direction: SetupDirection
) -> tuple[set[int], int | None]:
    series = {
        period: _sma_series(confirmed_candles, period)
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
        if len(confirmed_candles) >= period + 1
    }
    first_transition = max(1, len(confirmed_candles) - CROSS_WINDOW_CANDLES)
    involved_periods: set[int] = set()
    latest_event_index: int | None = None
    periods = tuple(series)
    for index in range(first_transition, len(confirmed_candles)):
        for fast_index, fast_period in enumerate(periods):
            for slow_period in periods[fast_index + 1 :]:
                if index - 1 not in series[slow_period]:
                    continue
                previous_difference = (
                    series[fast_period][index - 1] - series[slow_period][index - 1]
                )
                current_difference = (
                    series[fast_period][index] - series[slow_period][index]
                )
                crossed = (
                    previous_difference <= 0 < current_difference
                    if direction is SetupDirection.LONG
                    else previous_difference >= 0 > current_difference
                )
                if crossed:
                    involved_periods.update((fast_period, slow_period))
                    latest_event_index = index
    return involved_periods, latest_event_index


def _price_break_events(
    confirmed_candles: Sequence[Candle], direction: SetupDirection
) -> tuple[set[int], int | None]:
    series = {
        period: _sma_series(confirmed_candles, period)
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
        if len(confirmed_candles) >= period + 1
    }
    first_transition = max(1, len(confirmed_candles) - CROSS_WINDOW_CANDLES)
    crossed_periods: set[int] = set()
    latest_event_index: int | None = None
    for index in range(first_transition, len(confirmed_candles)):
        previous_close = confirmed_candles[index - 1].closing_price
        current_close = confirmed_candles[index].closing_price
        for period, values in series.items():
            if index - 1 not in values:
                continue
            crossed = (
                previous_close <= values[index - 1] and current_close > values[index]
                if direction is SetupDirection.LONG
                else previous_close >= values[index - 1] and current_close < values[index]
            )
            if crossed:
                crossed_periods.add(period)
                latest_event_index = index
    return crossed_periods, latest_event_index


def _respect_points(
    confirmed_candles: Sequence[Candle],
    direction: SetupDirection,
    event_index: int | None,
    relevant_periods: set[int],
) -> int:
    if event_index is None or not relevant_periods:
        return 0
    series = {
        period: _sma_series(confirmed_candles, period)
        for period in relevant_periods
        if len(confirmed_candles) >= period + 1
    }
    holds = 0
    for index in range(event_index + 1, min(len(confirmed_candles), event_index + 3)):
        relevant_values = [values[index] for values in series.values() if index in values]
        if not relevant_values:
            continue
        close = confirmed_candles[index].closing_price
        held = (
            close >= max(relevant_values)
            if direction is SetupDirection.LONG
            else close <= min(relevant_values)
        )
        if not held:
            return -2
        holds += 1
    return min(holds, 2)


def _score_direction(
    direction: SetupDirection,
    assessments_by_timeframe: dict[str, TimeframeMomentumAssessment],
    one_hour_candles: Sequence[Candle],
    current_price: float,
    minimum_normalized_histogram_slope: float,
) -> SetupScore:
    directions = {
        timeframe: histogram_direction(
            assessments_by_timeframe[timeframe],
            minimum_normalized_histogram_slope,
        )
        for timeframe in SZPONT_TIMEFRAMES
    }
    target = (
        HistogramDirection.UP
        if direction is SetupDirection.LONG
        else HistogramDirection.DOWN
    )
    synchronized_timeframes = tuple(
        timeframe for timeframe in SZPONT_TIMEFRAMES if directions[timeframe] is target
    )
    synchronization = synchronization_points(synchronized_timeframes)
    if synchronization == 0:
        return SetupScore(
            direction=direction,
            grade=SetupGrade.NONE,
            breakdown=ScoreBreakdown(),
            histogram_directions=directions,
            synchronized_timeframes=synchronized_timeframes,
            nearest_sma_period=None,
            nearest_sma_distance_percent=None,
            nearby_sma_periods=(),
            crossed_sma_periods=(),
            price_broken_sma_periods=(),
        )

    one_hour = assessments_by_timeframe[ENTRY_TIMEFRAME]
    distances = {
        period: abs(current_price / value - 1.0) * 100.0
        for period, value in one_hour.moving_average_levels.items()
    }
    nearest_period = min(distances, key=distances.get)
    nearest_distance = distances[nearest_period]
    one_hour_is_synchronized = ENTRY_TIMEFRAME in synchronized_timeframes
    if not one_hour_is_synchronized:
        proximity = 0
    elif nearest_distance <= 0.10:
        proximity = 3
    elif nearest_distance <= 0.25:
        proximity = 2
    elif nearest_distance <= 0.50:
        proximity = 1
    else:
        proximity = 0
    nearby_periods = tuple(
        period
        for period in SIMPLE_MOVING_AVERAGE_PERIODS
        if distances.get(period, float("inf")) <= STRUCTURE_DISTANCE_LIMIT_PERCENT
    )
    cluster = {0: 0, 1: 0, 2: 1, 3: 2, 4: 3}[len(nearby_periods)]

    correct_side_periods = tuple(
        period
        for period in nearby_periods
        if (
            current_price >= one_hour.moving_average_levels[period]
            if direction is SetupDirection.LONG
            else current_price <= one_hour.moving_average_levels[period]
        )
    )
    support_resistance = 1 if correct_side_periods else 0
    confirmed_candles = [candle for candle in one_hour_candles if candle.is_confirmed]
    latest_candle = confirmed_candles[-1]
    wick_respected = any(
        (
            latest_candle.lowest_price <= one_hour.moving_average_levels[period]
            and latest_candle.closing_price >= one_hour.moving_average_levels[period]
            if direction is SetupDirection.LONG
            else latest_candle.highest_price >= one_hour.moving_average_levels[period]
            and latest_candle.closing_price <= one_hour.moving_average_levels[period]
        )
        for period in correct_side_periods
    )
    support_resistance += int(wick_respected)
    if len(correct_side_periods) >= 2:
        support_resistance += 1

    crossed_periods, sma_cross_index = _cross_events(confirmed_candles, direction)
    if len(crossed_periods) >= 4:
        sma_cross = 3
    elif len(crossed_periods) == 3:
        sma_cross = 2
    elif len(crossed_periods) == 2:
        sma_cross = 1
    else:
        sma_cross = 0
    price_broken_periods, price_break_index = _price_break_events(
        confirmed_candles, direction
    )
    if len(price_broken_periods) >= 3:
        price_break = 2
    elif len(price_broken_periods) == 2:
        price_break = 1
    else:
        price_break = 0

    event_options = [
        (index, periods)
        for index, periods in (
            (sma_cross_index, crossed_periods),
            (price_break_index, price_broken_periods),
        )
        if index is not None
    ]
    latest_event_index, respect_periods = max(
        event_options,
        default=(None, set()),
        key=lambda value: value[0] if value[0] is not None else -1,
    )
    respect = _respect_points(
        confirmed_candles,
        direction,
        latest_event_index,
        respect_periods,
    )
    breakdown = ScoreBreakdown(
        synchronization=synchronization,
        sma_proximity=proximity,
        support_resistance=min(support_resistance, 3),
        sma_cluster=cluster,
        sma_cross=sma_cross,
        price_break=price_break,
        respect=respect,
    )
    return SetupScore(
        direction=direction,
        grade=classify_grade(breakdown.total, breakdown.has_structural_confirmation),
        breakdown=breakdown,
        histogram_directions=directions,
        synchronized_timeframes=synchronized_timeframes,
        nearest_sma_period=nearest_period,
        nearest_sma_distance_percent=nearest_distance,
        nearby_sma_periods=nearby_periods,
        crossed_sma_periods=tuple(sorted(crossed_periods)),
        price_broken_sma_periods=tuple(sorted(price_broken_periods)),
    )


def score_setup(
    assessments_by_timeframe: dict[str, TimeframeMomentumAssessment],
    one_hour_candles: Sequence[Candle],
    current_price: float,
    minimum_normalized_histogram_slope: float,
) -> SetupScore:
    scores = tuple(
        _score_direction(
            direction,
            assessments_by_timeframe,
            one_hour_candles,
            current_price,
            minimum_normalized_histogram_slope,
        )
        for direction in SetupDirection
    )
    long_score, short_score = scores
    if long_score.total == short_score.total and long_score.total > 0:
        return SetupScore(
            direction=long_score.direction,
            grade=SetupGrade.NONE,
            breakdown=ScoreBreakdown(),
            histogram_directions=long_score.histogram_directions,
            synchronized_timeframes=(),
            nearest_sma_period=long_score.nearest_sma_period,
            nearest_sma_distance_percent=long_score.nearest_sma_distance_percent,
            nearby_sma_periods=(),
            crossed_sma_periods=(),
            price_broken_sma_periods=(),
        )
    return max(scores, key=lambda score: score.total)
