# Configurable EMA levels

The original SMA 20/50/120/200 scanner remains unchanged. This module adds a separate EMA layer
for position management. Defaults match the user's ribbon:

```env
EMA_PERIODS=20,50,120,200
```

At startup the bot sends a dedicated EMA H4 message next to the existing SMA report. EMA values
are seeded with an SMA of the first `period` closes, then use `2 / (period + 1)`, matching the
standard TradingView definition. The open candle is included in the live level, exactly like the
existing startup SMA calculation.

Additional periods such as `45` can be enabled without code changes:

```env
EMA_PERIODS=20,45,50,120,200
```
