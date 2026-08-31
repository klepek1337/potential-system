from collections.abc import Sequence

from ma_alert_bot.dominant_ema import calculate_atr
from ma_alert_bot.models import Candle, MinuteSmaTiltAssessment, TiltDirection


def _window_average(values: Sequence[float], end: int, period: int) -> float:
    return sum(values[end - period : end]) / period


def assess_minute_sma_tilt(
    candles: Sequence[Candle],
    period: int,
    lookback_minutes: int,
    strong_tilt_threshold_atr: float,
    change_threshold_atr: float,
) -> MinuteSmaTiltAssessment | None:
    confirmed = [candle for candle in candles if candle.is_confirmed]
    required = period + 2 * lookback_minutes
    if len(confirmed) < max(required, 15):
        return None
    atr = calculate_atr(confirmed)
    if atr is None or atr <= 0:
        return None

    closes = [candle.closing_price for candle in confirmed]
    end = len(closes)
    current_sma = _window_average(closes, end, period)
    previous_sma = _window_average(closes, end - lookback_minutes, period)
    older_sma = _window_average(closes, end - 2 * lookback_minutes, period)
    current_tilt = (current_sma - previous_sma) / atr
    previous_tilt = (previous_sma - older_sma) / atr
    tilt_change = current_tilt - previous_tilt

    if current_tilt >= strong_tilt_threshold_atr:
        direction = TiltDirection.RISING
    elif current_tilt <= -strong_tilt_threshold_atr:
        direction = TiltDirection.FALLING
    else:
        direction = TiltDirection.FLAT
    if abs(tilt_change) < change_threshold_atr:
        return None

    return MinuteSmaTiltAssessment(
        period=period,
        lookback_minutes=lookback_minutes,
        current_price=confirmed[-1].closing_price,
        sma_value=current_sma,
        previous_tilt_atr=previous_tilt,
        current_tilt_atr=current_tilt,
        tilt_change_atr=tilt_change,
        direction=direction,
        candle_timestamp_ms=confirmed[-1].opening_timestamp_ms,
    )


def should_notify_tilt(
    assessment: MinuteSmaTiltAssessment,
    previous_state: tuple[int, int | None, str | None, float | None] | None,
    cooldown_seconds: int,
    change_threshold_atr: float,
) -> bool:
    if assessment.direction is TiltDirection.FLAT:
        return False
    if previous_state is None:
        return True
    _, last_alert_timestamp_ms, last_direction, last_alert_tilt = previous_state
    if last_alert_timestamp_ms is None:
        return True
    cooldown_ms = cooldown_seconds * 1000
    if assessment.candle_timestamp_ms - last_alert_timestamp_ms < cooldown_ms:
        return False
    if assessment.direction.value != last_direction:
        return True
    return last_alert_tilt is None or (
        abs(assessment.current_tilt_atr - last_alert_tilt) >= change_threshold_atr
    )
