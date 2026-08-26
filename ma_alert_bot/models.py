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

