from collections.abc import Sequence

from ma_alert_bot.models import Candle


def calculate_exponential_moving_average_series(
    candles: Sequence[Candle], period: int
) -> list[float | None]:
    """TradingView-compatible EMA seeded with the first period's SMA."""
    if period <= 0:
        raise ValueError("EMA period must be positive")
    result: list[float | None] = [None] * len(candles)
    if len(candles) < period:
        return result
    seed = sum(c.closing_price for c in candles[:period]) / period
    result[period - 1] = seed
    multiplier = 2.0 / (period + 1.0)
    previous = seed
    for index in range(period, len(candles)):
        previous = (candles[index].closing_price - previous) * multiplier + previous
        result[index] = previous
    return result


def calculate_latest_ema_levels(
    candles: Sequence[Candle], periods: tuple[int, ...]
) -> dict[int, float]:
    levels: dict[int, float] = {}
    for period in periods:
        series = calculate_exponential_moving_average_series(candles, period)
        if series and series[-1] is not None:
            levels[period] = float(series[-1])
    return levels
