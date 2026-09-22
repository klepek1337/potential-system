# Changelog

## 2.0.1

- Suppressed all `WEAK` radar candidates below 9 points.
- Kept `VALID`, `GOOD`, `STRONG`, and `A+ FULL SYNC` alerts, ordered strongest first.
- Reset notification state below 9 points so a later qualifying re-entry can alert again.

## 2.0.0

- Replaced the old `BUILDING`/expansion radar with a symmetric LONG/SHORT score.
- Added 1H/2H/4H plus live-1D histogram synchronization with a two-timeframe minimum.
- Added 1H SMA proximity, support/resistance, cluster, cross, price-break and respect points.
- Added `WEAK`, `VALID`, `GOOD`, `STRONG`, and `A+ FULL SYNC` score bands up to 28 points.
- Preserved the existing all-perpetual liquidity, spread, and listing-age universe filters.

## 1.9.2

- Reduced the market radar's minimum confirmed D1 history from 202 to 60 candles.
- Calculated only available SMA20/SMA50 levels for shortened D1 history.
- Kept the full 202-candle requirement for 1H, 2H, and 4H assessments.
- Silently excluded instruments younger than 60 days and downgraded residual short-history
  failures to informational log entries.

## 1.9.1

- Required a rising MACD histogram on 1H, 2H, 4H, and 1D for every radar signal.
- Allowed negative H4 and 1D histograms when their normalized slopes are rising.
- Made a positive but falling histogram a veto instead of treating its sign as confirmation.
- Limited the H4 SMA trend filter to `A+`; early synchronized recovery remains visible.
- Made extreme price stretch suppress every radar level.

## 1.9.0

- Added an hourly radar over all live OKX USDT perpetual swaps.
- Added exactly three transition alerts: `BUILDING`, `STRONG`, and `A+ FULL SYNC`.
- Made rising H4 mandatory for `STRONG` and `A+`; H4 neutral/recovery is only `BUILDING`.
- Added liquidity, spread, listing-age, SMA, overheat, and multi-candle confirmation filters.
- Batched new setups into Telegram reports and persisted signal state to suppress repeats.

## 1.8.0

- Added `/obserwujlong SYMBOL` with transition-based MACD histogram alerts on 1H/2H/4H/1D.
- Added ATR-normalized MACD gap, SMA20 price stretch, bullish-leg return and overheat context.
- Added `/dodaj SYMBOL` and SQLite-backed hot runtime instruments without restarting the bot.
- Kept every action advisory-only; no authenticated exchange operations were added.

The project follows [Semantic Versioning](https://semver.org/). The version shown in the Telegram
startup notification is defined once in `ma_alert_bot/version.py`.

## [1.6.0] - 2026-08-31

### Changed

- Startup version/update notification is independent from current SMA/EMA level summaries.
- Current SMA/EMA level summaries are disabled by default through
  `SEND_STARTUP_LEVEL_SUMMARIES=false`.
- Default one-minute tilt average changed from SMA 20 to SMA 200.
- Windows launcher prompts to abort, stash, or discard tracked and non-ignored local changes while
  preserving files covered by `.gitignore`.

## [1.5.0] - 2026-08-31

### Added

- One-minute SMA 20 tilt calculated from confirmed candles.
- ATR-normalized tilt strength and direction-change alerts.
- Manual-position context in tilt notifications.

## [1.4.0] - 2026-08-31

### Added

- Advisory protection of unrealized profit.
- Reduction recommendations, including a 50% first reduction.
- Worst-case protected-PnL estimate.

## [1.3.0] - 2026-08-31

### Added

- Selection and quality scoring of the dominant EMA.
- One-way stop anchor that cannot loosen the previous stop.

## [1.2.0] - 2026-08-31

### Added

- Configurable EMA 20, 50, 120, and 200 level reports.

## [1.1.0] - 2026-08-31

### Added

- Manual LONG and SHORT position registry.
- Entry, stop, USD/USDC position value, and leverage fields.

## [1.0.0] - 2026-08-31

### Added

- H4 SMA 20, 50, 120, and 200 test scanner.
- Telegram alerts for a test, defense, loss, rejection, or reclaim.
- Persistent SQLite alert state.
