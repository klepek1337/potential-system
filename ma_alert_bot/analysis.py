from collections.abc import Sequence

from ma_alert_bot.models import ApproachSide, Candle, MovingAverageTest, TestOutcome


MOVING_AVERAGE_PERIODS = (20, 50, 120, 200)


def calculate_simple_moving_average(
    candles: Sequence[Candle], candle_index: int, moving_average_period: int
) -> float | None:
    first_candle_index = candle_index - moving_average_period + 1
    if first_candle_index < 0:
        return None

    relevant_candles = candles[first_candle_index : candle_index + 1]
    closing_price_sum = sum(candle.closing_price for candle in relevant_candles)
    return closing_price_sum / moving_average_period


def determine_approach_side(
    candles: Sequence[Candle], current_candle_index: int, moving_average_period: int
) -> ApproachSide | None:
    previous_candle_index = current_candle_index - 1
    if previous_candle_index < 0:
        return None

    previous_moving_average = calculate_simple_moving_average(
        candles, previous_candle_index, moving_average_period
    )
    if previous_moving_average is None:
        return None

    previous_closing_price = candles[previous_candle_index].closing_price
    if previous_closing_price >= previous_moving_average:
        return ApproachSide.ABOVE
    return ApproachSide.BELOW


def calculate_latest_moving_average_levels(
    candles: Sequence[Candle],
) -> dict[int, float]:
    if not candles:
        return {}

    latest_candle_index = len(candles) - 1
    moving_average_levels: dict[int, float] = {}
    for moving_average_period in MOVING_AVERAGE_PERIODS:
        moving_average_value = calculate_simple_moving_average(
            candles,
            latest_candle_index,
            moving_average_period,
        )
        if moving_average_value is not None:
            moving_average_levels[moving_average_period] = moving_average_value
    return moving_average_levels


def candle_touches_moving_average(
    candle: Candle,
    moving_average_value: float,
    touch_margin_ratio: float,
) -> bool:
    touch_margin_value = moving_average_value * touch_margin_ratio
    lower_touch_boundary = moving_average_value - touch_margin_value
    upper_touch_boundary = moving_average_value + touch_margin_value
    return (
        candle.lowest_price <= upper_touch_boundary
        and candle.highest_price >= lower_touch_boundary
    )


def detect_tests_on_latest_candle(
    instrument_id: str,
    candles: Sequence[Candle],
    touch_margin_ratio: float,
) -> list[MovingAverageTest]:
    if not candles:
        return []

    current_candle_index = len(candles) - 1
    current_candle = candles[current_candle_index]
    if current_candle.is_confirmed:
        return []

    detected_tests: list[MovingAverageTest] = []
    for moving_average_period in MOVING_AVERAGE_PERIODS:
        moving_average_value = calculate_simple_moving_average(
            candles, current_candle_index, moving_average_period
        )
        approach_side = determine_approach_side(
            candles, current_candle_index, moving_average_period
        )
        if moving_average_value is None or approach_side is None:
            continue

        candle_touched_moving_average = candle_touches_moving_average(
            candle=current_candle,
            moving_average_value=moving_average_value,
            touch_margin_ratio=touch_margin_ratio,
        )
        if not candle_touched_moving_average:
            continue

        detected_tests.append(
            MovingAverageTest(
                instrument_id=instrument_id,
                moving_average_period=moving_average_period,
                candle_opening_timestamp_ms=current_candle.opening_timestamp_ms,
                approach_side=approach_side,
                moving_average_value_at_detection=moving_average_value,
                price_at_detection=current_candle.closing_price,
            )
        )

    return detected_tests


def resolve_test_outcome(
    approach_side: ApproachSide,
    closing_price: float,
    final_moving_average_value: float,
) -> TestOutcome:
    if approach_side is ApproachSide.ABOVE:
        if closing_price >= final_moving_average_value:
            return TestOutcome.SUPPORT_DEFENDED
        return TestOutcome.SUPPORT_LOST

    if closing_price <= final_moving_average_value:
        return TestOutcome.RESISTANCE_REJECTED
    return TestOutcome.RESISTANCE_RECLAIMED
