import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from ma_alert_bot.environment import load_environment_file
from ma_alert_bot.positions import PositionSource


DEFAULT_OKX_API_BASE_URL = "https://www.okx.com"
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_DISPLAY_TIMEZONE = "Europe/Luxembourg"
DEFAULT_STATE_DATABASE_PATH = "data/ma_alerts.sqlite3"
DEFAULT_MOVING_AVERAGE_TOUCH_MARGIN_PERCENT = 0.1
DEFAULT_SEND_STARTUP_SUMMARY = True
DEFAULT_SEND_DECISION_REPORTS = True
DEFAULT_POSITION_SOURCE = PositionSource.MANUAL
DEFAULT_POSITION_PLANS_PATH = "position_plans.json"
DEFAULT_DAILY_DECISION_REPORT_LOCAL_TIME = "08:00"
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


def parse_local_time(environment_value: str | None) -> time | None:
    if environment_value is not None and not environment_value.strip():
        return None
    time_value = environment_value or DEFAULT_DAILY_DECISION_REPORT_LOCAL_TIME
    try:
        hour_text, minute_text = time_value.strip().split(":", maxsplit=1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "DAILY_DECISION_REPORT_LOCAL_TIME must use HH:MM or be empty"
        ) from error


@dataclass(frozen=True)
class Settings:
    okx_api_base_url: str
    instrument_ids: tuple[str, ...]
    poll_interval_seconds: int
    display_timezone: str
    state_database_path: Path
    moving_average_touch_margin_ratio: float
    send_startup_summary: bool
    send_decision_reports: bool
    position_source: PositionSource
    position_plans_path: Path
    daily_decision_report_local_time: time | None
    okx_api_key: str | None
    okx_api_secret: str | None
    okx_api_passphrase: str | None
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
            send_decision_reports=parse_boolean(
                os.getenv("SEND_DECISION_REPORTS"),
                default_value=DEFAULT_SEND_DECISION_REPORTS,
            ),
            position_source=PositionSource(
                os.getenv("POSITION_SOURCE", DEFAULT_POSITION_SOURCE.value)
                .strip()
                .lower()
            ),
            position_plans_path=Path(
                os.getenv("POSITION_PLANS_PATH", DEFAULT_POSITION_PLANS_PATH)
            ),
            daily_decision_report_local_time=parse_local_time(
                os.getenv("DAILY_DECISION_REPORT_LOCAL_TIME")
            ),
            okx_api_key=os.getenv("OKX_API_KEY") or None,
            okx_api_secret=os.getenv("OKX_API_SECRET") or None,
            okx_api_passphrase=os.getenv("OKX_API_PASSPHRASE") or None,
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
        if self.position_source is not PositionSource.MANUAL:
            missing_credentials = [
                environment_name
                for environment_name, credential_value in (
                    ("OKX_API_KEY", self.okx_api_key),
                    ("OKX_API_SECRET", self.okx_api_secret),
                    ("OKX_API_PASSPHRASE", self.okx_api_passphrase),
                )
                if not credential_value
            ]
            if missing_credentials:
                raise ValueError(
                    "Automatic position detection requires: "
                    + ", ".join(missing_credentials)
                )
