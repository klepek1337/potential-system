# Changelog

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
