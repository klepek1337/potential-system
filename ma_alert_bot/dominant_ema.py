from collections.abc import Sequence

from ma_alert_bot.ema_analysis import calculate_exponential_moving_average_series
from ma_alert_bot.models import Candle, DominantEmaCandidate, PositionSide


ANALYSIS_WINDOW = 48
MINIMUM_SCORE = 70.0
ATR_PERIOD = 14
ATR_STOP_BUFFER_MULTIPLIER = 0.35
MINIMUM_STOP_ANCHOR_REPORT_CHANGE_RATIO = 0.001


def calculate_atr(candles: Sequence[Candle], period: int = ATR_PERIOD) -> float | None:
    if len(candles) < period + 1:
        return None
    ranges: list[float] = []
    for index in range(len(candles) - period, len(candles)):
        candle = candles[index]
        previous_close = candles[index - 1].closing_price
        ranges.append(
            max(
                candle.highest_price - candle.lowest_price,
                abs(candle.highest_price - previous_close),
                abs(candle.lowest_price - previous_close),
            )
        )
    return sum(ranges) / period


def score_ema_candidate(
    candles: Sequence[Candle], timeframe: str, period: int, side: PositionSide
) -> DominantEmaCandidate | None:
    confirmed = [candle for candle in candles if candle.is_confirmed]
    series = calculate_exponential_moving_average_series(confirmed, period)
    valid = [(candle, value) for candle, value in zip(confirmed, series) if value is not None]
    valid = valid[-ANALYSIS_WINDOW:]
    atr = calculate_atr(confirmed)
    if len(valid) < min(20, ANALYSIS_WINDOW) or atr is None or atr <= 0:
        return None

    def is_correct(candle: Candle, value: float) -> bool:
        return candle.closing_price >= value if side is PositionSide.LONG else candle.closing_price <= value

    correctness = [is_correct(candle, float(value)) for candle, value in valid]
    correct_ratio = sum(correctness) / len(correctness)
    longest = current = 0
    for correct in correctness:
        current = current + 1 if correct else 0
        longest = max(longest, current)
    crossings = sum(a != b for a, b in zip(correctness, correctness[1:]))
    successful_tests = 0
    for candle, raw_value in valid:
        value = float(raw_value)
        wick_crossed = candle.lowest_price <= value if side is PositionSide.LONG else candle.highest_price >= value
        if wick_crossed and is_correct(candle, value):
            successful_tests += 1

    first_value = float(valid[0][1])
    latest_value = float(valid[-1][1])
    correct_slope = latest_value > first_value if side is PositionSide.LONG else latest_value < first_value
    recent_ratio = sum(correctness[-8:]) / min(8, len(correctness))
    score = (
        35.0 * correct_ratio
        + 20.0 * min(longest / 20.0, 1.0)
        + (10.0 if correct_slope else 0.0)
        + 20.0 * min(successful_tests / 4.0, 1.0)
        + 15.0 * recent_ratio
        - min(crossings * 4.0, 25.0)
    )
    proposed_stop = (
        latest_value - ATR_STOP_BUFFER_MULTIPLIER * atr
        if side is PositionSide.LONG
        else latest_value + ATR_STOP_BUFFER_MULTIPLIER * atr
    )
    return DominantEmaCandidate(
        timeframe=timeframe,
        period=period,
        value=latest_value,
        score=max(0.0, min(score, 100.0)),
        correct_close_ratio=correct_ratio,
        longest_confirmation=longest,
        body_crossings=crossings,
        successful_tests=successful_tests,
        atr=atr,
        proposed_stop=proposed_stop,
    )


def select_dominant_ema(
    candles_by_timeframe: dict[str, Sequence[Candle]],
    periods: tuple[int, ...],
    side: PositionSide,
) -> DominantEmaCandidate | None:
    """Choose the best qualifying EMA on the smallest qualifying timeframe."""
    for timeframe, candles in candles_by_timeframe.items():
        candidates = [
            candidate
            for period in periods
            if (candidate := score_ema_candidate(candles, timeframe, period, side))
            and candidate.score >= MINIMUM_SCORE
        ]
        if candidates:
            return max(candidates, key=lambda item: item.score)
    return None


def ratchet_stop(current_stop: float, proposed_stop: float, side: PositionSide) -> float:
    return max(current_stop, proposed_stop) if side is PositionSide.LONG else min(current_stop, proposed_stop)


def dominant_ema_report_changed(
    previous_state: tuple[float, str, int, float] | None,
    timeframe: str,
    period: int,
    stop_anchor: float,
) -> bool:
    if previous_state is None:
        return True
    previous_anchor, previous_timeframe, previous_period, _ = previous_state
    if timeframe != previous_timeframe or period != previous_period:
        return True
    if previous_anchor == 0:
        return True
    return (
        abs(stop_anchor - previous_anchor) / abs(previous_anchor)
        >= MINIMUM_STOP_ANCHOR_REPORT_CHANGE_RATIO
    )
