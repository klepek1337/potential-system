import os
from dataclasses import dataclass
from pathlib import Path

from ma_alert_bot.environment import load_environment_file


DEFAULT_OKX_API_BASE_URL = "https://www.okx.com"
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_DISPLAY_TIMEZONE = "Europe/Luxembourg"
DEFAULT_STATE_DATABASE_PATH = "data/ma_alerts.sqlite3"
DEFAULT_POSITIONS_FILE_PATH = "data/positions.json"
DEFAULT_MOVING_AVERAGE_TOUCH_MARGIN_PERCENT = 0.1
DEFAULT_SEND_STARTUP_SUMMARY = True
DEFAULT_SEND_STARTUP_CONFIGURATION = False
DEFAULT_SEND_STARTUP_LEVEL_SUMMARIES = False
DEFAULT_EMA_PERIODS = (20, 50, 120, 200)
DEFAULT_DOMINANT_EMA_TIMEFRAMES = ("15m", "1H", "4H", "1D")
DEFAULT_DOMINANT_EMA_SCAN_INTERVAL_SECONDS = 3600
DEFAULT_MINUTE_SMA_TILT_ENABLED = True
DEFAULT_MINUTE_SMA_TILT_PERIOD = 200
DEFAULT_MINUTE_SMA_TILT_LOOKBACK_MINUTES = 5
DEFAULT_MINUTE_SMA_TILT_STRONG_THRESHOLD_ATR = 0.25
DEFAULT_MINUTE_SMA_TILT_CHANGE_THRESHOLD_ATR = 0.5
DEFAULT_MINUTE_SMA_TILT_COOLDOWN_SECONDS = 600
DEFAULT_TELEGRAM_COMMANDS_ENABLED = True
DEFAULT_SZPONT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE = 0.001
MINIMUM_POLL_INTERVAL_SECONDS = 10
MINIMUM_TOUCH_MARGIN_PERCENT = 0.0
MAXIMUM_TOUCH_MARGIN_PERCENT = 5.0
PERCENT_TO_RATIO_DIVISOR = 100.0


def parse_boolean(environment_value: str | None, default_value: bool) -> bool:
    if environment_value is None:
        return default_value
    return environment_value.strip().lower() in {"1", "true", "yes", "on"}


def parse_instrument_ids(environment_value: str | None) -> tuple[str, ...]:
    if environment_value is None:
        return ()
    return tuple(
        instrument_id.strip().upper()
        for instrument_id in environment_value.split(",")
        if instrument_id.strip()
    )


def parse_positive_periods(environment_value: str | None) -> tuple[int, ...]:
    if environment_value is None:
        return DEFAULT_EMA_PERIODS
    periods = tuple(dict.fromkeys(int(value.strip()) for value in environment_value.split(",") if value.strip()))
    if not periods or any(period <= 0 for period in periods):
        raise ValueError("EMA_PERIODS must contain positive integers")
    return periods


def parse_csv_values(environment_value: str | None, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if environment_value is None:
        return defaults
    values = tuple(dict.fromkeys(value.strip() for value in environment_value.split(",") if value.strip()))
    if not values:
        raise ValueError("Configuration list cannot be empty")
    return values


@dataclass(frozen=True)
class Settings:
    okx_api_base_url: str
    instrument_ids: tuple[str, ...]
    poll_interval_seconds: int
    display_timezone: str
    state_database_path: Path
    positions_file_path: Path
    moving_average_touch_margin_ratio: float
    send_startup_summary: bool
    send_startup_configuration: bool
    send_startup_level_summaries: bool
    ema_periods: tuple[int, ...]
    dominant_ema_timeframes: tuple[str, ...]
    dominant_ema_scan_interval_seconds: int
    minute_sma_tilt_enabled: bool
    minute_sma_tilt_period: int
    minute_sma_tilt_lookback_minutes: int
    minute_sma_tilt_strong_threshold_atr: float
    minute_sma_tilt_change_threshold_atr: float
    minute_sma_tilt_cooldown_seconds: int
    telegram_commands_enabled: bool
    szpont_minimum_normalized_histogram_slope: float
    dry_run: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_environment_file()

        settings = cls(
            okx_api_base_url=os.getenv("OKX_API_BASE_URL", DEFAULT_OKX_API_BASE_URL),
            instrument_ids=parse_instrument_ids(os.getenv("OKX_INSTRUMENT_IDS")),
            poll_interval_seconds=int(
                os.getenv("POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS))
            ),
            display_timezone=os.getenv("DISPLAY_TIMEZONE", DEFAULT_DISPLAY_TIMEZONE),
            state_database_path=Path(
                os.getenv("STATE_DATABASE_PATH", DEFAULT_STATE_DATABASE_PATH)
            ),
            positions_file_path=Path(
                os.getenv("POSITIONS_FILE_PATH", DEFAULT_POSITIONS_FILE_PATH)
            ),
            moving_average_touch_margin_ratio=(
                float(
                    os.getenv(
                        "MOVING_AVERAGE_TOUCH_MARGIN_PERCENT",
                        str(DEFAULT_MOVING_AVERAGE_TOUCH_MARGIN_PERCENT),
                    )
                )
                / PERCENT_TO_RATIO_DIVISOR
            ),
            send_startup_summary=parse_boolean(
                os.getenv("SEND_STARTUP_SUMMARY"),
                default_value=DEFAULT_SEND_STARTUP_SUMMARY,
            ),
            send_startup_configuration=parse_boolean(
                os.getenv("SEND_STARTUP_CONFIGURATION"),
                default_value=DEFAULT_SEND_STARTUP_CONFIGURATION,
            ),
            send_startup_level_summaries=parse_boolean(
                os.getenv("SEND_STARTUP_LEVEL_SUMMARIES"),
                default_value=DEFAULT_SEND_STARTUP_LEVEL_SUMMARIES,
            ),
            ema_periods=parse_positive_periods(os.getenv("EMA_PERIODS")),
            dominant_ema_timeframes=parse_csv_values(
                os.getenv("DOMINANT_EMA_TIMEFRAMES"), DEFAULT_DOMINANT_EMA_TIMEFRAMES
            ),
            dominant_ema_scan_interval_seconds=int(
                os.getenv(
                    "DOMINANT_EMA_SCAN_INTERVAL_SECONDS",
                    str(DEFAULT_DOMINANT_EMA_SCAN_INTERVAL_SECONDS),
                )
            ),
            minute_sma_tilt_enabled=parse_boolean(
                os.getenv("MINUTE_SMA_TILT_ENABLED"), DEFAULT_MINUTE_SMA_TILT_ENABLED
            ),
            minute_sma_tilt_period=int(
                os.getenv("MINUTE_SMA_TILT_PERIOD", str(DEFAULT_MINUTE_SMA_TILT_PERIOD))
            ),
            minute_sma_tilt_lookback_minutes=int(
                os.getenv(
                    "MINUTE_SMA_TILT_LOOKBACK_MINUTES",
                    str(DEFAULT_MINUTE_SMA_TILT_LOOKBACK_MINUTES),
                )
            ),
            minute_sma_tilt_strong_threshold_atr=float(
                os.getenv(
                    "MINUTE_SMA_TILT_STRONG_THRESHOLD_ATR",
                    str(DEFAULT_MINUTE_SMA_TILT_STRONG_THRESHOLD_ATR),
                )
            ),
            minute_sma_tilt_change_threshold_atr=float(
                os.getenv(
                    "MINUTE_SMA_TILT_CHANGE_THRESHOLD_ATR",
                    str(DEFAULT_MINUTE_SMA_TILT_CHANGE_THRESHOLD_ATR),
                )
            ),
            minute_sma_tilt_cooldown_seconds=int(
                os.getenv(
                    "MINUTE_SMA_TILT_COOLDOWN_SECONDS",
                    str(DEFAULT_MINUTE_SMA_TILT_COOLDOWN_SECONDS),
                )
            ),
            telegram_commands_enabled=parse_boolean(
                os.getenv("TELEGRAM_COMMANDS_ENABLED"),
                DEFAULT_TELEGRAM_COMMANDS_ENABLED,
            ),
            szpont_minimum_normalized_histogram_slope=float(
                os.getenv(
                    "SZPONT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE",
                    str(DEFAULT_SZPONT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE),
                )
            ),
            dry_run=parse_boolean(os.getenv("DRY_RUN"), default_value=True),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.instrument_ids:
            raise ValueError("OKX_INSTRUMENT_IDS must contain at least one instrument")
        if self.poll_interval_seconds < MINIMUM_POLL_INTERVAL_SECONDS:
            raise ValueError(
                f"POLL_INTERVAL_SECONDS must be at least {MINIMUM_POLL_INTERVAL_SECONDS}"
            )
        touch_margin_percent = (
            self.moving_average_touch_margin_ratio * PERCENT_TO_RATIO_DIVISOR
        )
        if not MINIMUM_TOUCH_MARGIN_PERCENT <= touch_margin_percent <= MAXIMUM_TOUCH_MARGIN_PERCENT:
            raise ValueError(
                "MOVING_AVERAGE_TOUCH_MARGIN_PERCENT must be between "
                f"{MINIMUM_TOUCH_MARGIN_PERCENT} and {MAXIMUM_TOUCH_MARGIN_PERCENT}"
            )
        if not self.dry_run and not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required when DRY_RUN=false")
        if not self.dry_run and not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required when DRY_RUN=false")
        if self.minute_sma_tilt_period <= 0 or self.minute_sma_tilt_lookback_minutes <= 0:
            raise ValueError("Minute SMA tilt period and lookback must be positive")
        if self.minute_sma_tilt_strong_threshold_atr <= 0:
            raise ValueError("MINUTE_SMA_TILT_STRONG_THRESHOLD_ATR must be positive")
        if self.minute_sma_tilt_change_threshold_atr <= 0:
            raise ValueError("MINUTE_SMA_TILT_CHANGE_THRESHOLD_ATR must be positive")
        if self.minute_sma_tilt_cooldown_seconds < 60:
            raise ValueError("MINUTE_SMA_TILT_COOLDOWN_SECONDS must be at least 60")
        if self.szpont_minimum_normalized_histogram_slope <= 0:
            raise ValueError(
                "SZPONT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE must be positive"
            )
