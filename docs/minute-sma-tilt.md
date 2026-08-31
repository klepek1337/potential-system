# One-minute SMA tilt

The scanner can detect a sharp change in the slope of a one-minute SMA. It uses only confirmed
one-minute candles, so an unfinished candle or a single live wick cannot trigger the calculation.

```text
current tilt  = (SMA now - SMA one lookback ago) / ATR(14)
previous tilt = (SMA one lookback ago - SMA two lookbacks ago) / ATR(14)
tilt change   = current tilt - previous tilt
```

ATR normalization makes the same thresholds usable across instruments with different prices and
volatility. Defaults use SMA 20, a five-minute lookback, a minimum current tilt of 0.25 ATR and a
minimum change of 0.50 ATR. A ten-minute cooldown plus SQLite state prevents repeated alerts.

```env
MINUTE_SMA_TILT_ENABLED=true
MINUTE_SMA_TILT_PERIOD=20
MINUTE_SMA_TILT_LOOKBACK_MINUTES=5
MINUTE_SMA_TILT_STRONG_THRESHOLD_ATR=0.25
MINUTE_SMA_TILT_CHANGE_THRESHOLD_ATR=0.5
MINUTE_SMA_TILT_COOLDOWN_SECONDS=600
```

The alert includes manual-position context when available. It is a micro-momentum warning and
never changes a stop, reduces a position, or executes an order.
