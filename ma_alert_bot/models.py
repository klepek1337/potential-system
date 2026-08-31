from dataclasses import dataclass
from enum import StrEnum


class ApproachSide(StrEnum):
    ABOVE = "above"
    BELOW = "below"


class TestOutcome(StrEnum):
    SUPPORT_DEFENDED = "support_defended"
    SUPPORT_LOST = "support_lost"
    RESISTANCE_REJECTED = "resistance_rejected"
    RESISTANCE_RECLAIMED = "resistance_reclaimed"


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class Candle:
    opening_timestamp_ms: int
    opening_price: float
    highest_price: float
    lowest_price: float
    closing_price: float
    is_confirmed: bool


@dataclass(frozen=True)
class MovingAverageTest:
    instrument_id: str
    moving_average_period: int
    candle_opening_timestamp_ms: int
    approach_side: ApproachSide
    moving_average_value_at_detection: float
    price_at_detection: float


@dataclass(frozen=True)
class UnresolvedTest:
    instrument_id: str
    moving_average_period: int
    candle_opening_timestamp_ms: int
    approach_side: ApproachSide


@dataclass(frozen=True)
class ManualPosition:
    instrument_id: str
    side: PositionSide
    entry_price: float
    stop_price: float
    position_value_usd: float | None = None
    leverage: float | None = None


@dataclass(frozen=True)
class DominantEmaCandidate:
    timeframe: str
    period: int
    value: float
    score: float
    correct_close_ratio: float
    longest_confirmation: int
    body_crossings: int
    successful_tests: int
    atr: float
    proposed_stop: float


@dataclass(frozen=True)
class ProfitProtectionAssessment:
    r_multiple: float
    distance_from_ema_atr: float
    target_reduction_percent: int
    newly_recommended_reduction_percent: int
    remaining_percent: int
    protected_pnl_per_unit: float
    projected_total_pnl: float | None
    stage: int
