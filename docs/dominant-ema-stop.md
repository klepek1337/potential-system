# Dominant EMA and one-way stop anchor

This engine periodically asks which configured EMA currently leads the trend. It starts with the
smallest configured timeframe and promotes its best candidate only when it passes the quality
threshold. A candidate is rewarded for sustained closes on the position's side, a long continuous
confirmation, directional slope, successful wick tests that close back on the correct side, and
recent relevance. Repeated body crossings receive a chop penalty.

Defaults:

```env
EMA_PERIODS=20,50,120,200
DOMINANT_EMA_TIMEFRAMES=15m,1H,4H,1D
DOMINANT_EMA_SCAN_INTERVAL_SECONDS=3600
```

The candidate proposes `EMA +/- 0.35 ATR(14)`. The persisted stop anchor is a ratchet: it can only
rise for a long and only fall for a short. Detection may move to a slower EMA when the regime
changes, but the already protected stop is never loosened automatically.

The value is an advisory anchor. The bot does not send an order to OKX. An exchange-side emergency
stop remains the user's responsibility, and a wick through the analytical EMA is not by itself a
confirmed trend failure.

The analysis still runs on schedule, but Telegram sends a dominant-EMA report only when the
timeframe/period changes or the one-way stop anchor moves by at least `0.1%`. Score-only drift is
stored without producing hourly notification spam.
