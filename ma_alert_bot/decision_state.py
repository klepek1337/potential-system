from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from itertools import pairwise

from ma_alert_bot.positions import (
    HoldingHorizon,
    PositionDirection,
    PositionRole,
    PositionSnapshot,
)


MOMENTUM_MOVING_AVERAGE_PERIOD = 20
STRUCTURAL_MOVING_AVERAGE_PERIOD = 50
MEDIUM_TERM_MOVING_AVERAGE_PERIOD = 120
LONG_TERM_MOVING_AVERAGE_PERIOD = 200
REQUIRED_RIBBON_PERIODS = (
    MOMENTUM_MOVING_AVERAGE_PERIOD,
    STRUCTURAL_MOVING_AVERAGE_PERIOD,
    MEDIUM_TERM_MOVING_AVERAGE_PERIOD,
    LONG_TERM_MOVING_AVERAGE_PERIOD,
)
MINIMUM_RIBBON_WIDTH = 0.0
LONG_TERM_HORIZONS = (HoldingHorizon.POSITION_W1, HoldingHorizon.CYCLE)


class RibbonState(StrEnum):
    FULL_BULLISH = "FULL_BULLISH"
    FULL_BEARISH = "FULL_BEARISH"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MomentumState(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PositionPhase(StrEnum):
    NO_POSITION = "NO_POSITION"
    HOLDING = "HOLDING"
    HOLDING_EXTENDED = "HOLDING_EXTENDED"
    MOMENTUM_WARNING = "MOMENTUM_WARNING"
    EXECUTION_STRUCTURE_BROKEN = "EXECUTION_STRUCTURE_BROKEN"
    THESIS_AT_RISK = "THESIS_AT_RISK"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    TARGET_REACHED = "TARGET_REACHED"


class CoreAction(StrEnum):
    HOLD = "HOLD"
    REDUCE_RISK = "REDUCE_RISK"
    EXIT = "EXIT"
    REVIEW_PROFIT = "REVIEW_PROFIT"
    NO_ACTION = "NO_ACTION"


class AddingAction(StrEnum):
    PAUSE_ADDS = "PAUSE_ADDS"
    ALLOW_ONLY_AFTER_CONFIRMATION = "ALLOW_ONLY_AFTER_CONFIRMATION"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class DecisionState:
    ribbon_state: RibbonState
    momentum_state: MomentumState
    position_phase: PositionPhase
    core_action: CoreAction
    adding_action: AddingAction
    momentum_level: float | None
    structural_level: float | None
    hard_invalidation_level: float | None
    is_extended_from_momentum: bool
    position_role: PositionRole | None
    holding_horizon: HoldingHorizon | None
    strategic_review_required: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_ribbon(
    current_price: float,
    moving_average_levels: Mapping[int, float],
) -> RibbonState:
    if any(period not in moving_average_levels for period in REQUIRED_RIBBON_PERIODS):
        return RibbonState.INSUFFICIENT_DATA

    ordered_levels = [
        moving_average_levels[period] for period in REQUIRED_RIBBON_PERIODS
    ]
    bullish_order = all(
        higher_level > lower_level
        for higher_level, lower_level in pairwise(ordered_levels)
    )
    bearish_order = all(
        higher_level < lower_level
        for higher_level, lower_level in pairwise(ordered_levels)
    )
    if bullish_order and current_price > ordered_levels[0]:
        return RibbonState.FULL_BULLISH
    if bearish_order and current_price < ordered_levels[0]:
        return RibbonState.FULL_BEARISH
    return RibbonState.MIXED


def classify_momentum(
    latest_confirmed_price: float,
    moving_average_levels: Mapping[int, float],
) -> MomentumState:
    momentum_level = moving_average_levels.get(MOMENTUM_MOVING_AVERAGE_PERIOD)
    if momentum_level is None:
        return MomentumState.INSUFFICIENT_DATA
    if latest_confirmed_price > momentum_level:
        return MomentumState.BULLISH
    if latest_confirmed_price < momentum_level:
        return MomentumState.BEARISH
    return MomentumState.NEUTRAL


def _is_extended_from_momentum(
    current_price: float,
    moving_average_levels: Mapping[int, float],
) -> bool:
    momentum_level = moving_average_levels.get(MOMENTUM_MOVING_AVERAGE_PERIOD)
    structural_level = moving_average_levels.get(STRUCTURAL_MOVING_AVERAGE_PERIOD)
    if momentum_level is None or structural_level is None:
        return False
    ribbon_width = abs(momentum_level - structural_level)
    if ribbon_width <= MINIMUM_RIBBON_WIDTH:
        return False
    return abs(current_price - momentum_level) > ribbon_width


def _level_breached(
    price: float,
    level: float | None,
    direction: PositionDirection,
) -> bool:
    if level is None:
        return False
    if direction is PositionDirection.LONG:
        return price <= level
    return price >= level


def _confirmed_level_breached(
    confirmed_price: float,
    level: float | None,
    direction: PositionDirection,
) -> bool:
    if level is None:
        return False
    if direction is PositionDirection.LONG:
        return confirmed_price < level
    return confirmed_price > level


def _target_reached(current_price: float, position: PositionSnapshot) -> bool:
    if position.target_price is None:
        return False
    if position.direction is PositionDirection.LONG:
        return current_price >= position.target_price
    return current_price <= position.target_price


def build_decision_state(
    current_price: float,
    latest_confirmed_price: float,
    moving_average_levels: Mapping[int, float],
    position: PositionSnapshot | None,
) -> DecisionState:
    ribbon_state = classify_ribbon(current_price, moving_average_levels)
    momentum_state = classify_momentum(
        latest_confirmed_price,
        moving_average_levels,
    )
    momentum_level = moving_average_levels.get(MOMENTUM_MOVING_AVERAGE_PERIOD)
    structural_level = moving_average_levels.get(STRUCTURAL_MOVING_AVERAGE_PERIOD)
    is_extended = _is_extended_from_momentum(
        current_price,
        moving_average_levels,
    )

    if position is None:
        return DecisionState(
            ribbon_state=ribbon_state,
            momentum_state=momentum_state,
            position_phase=PositionPhase.NO_POSITION,
            core_action=CoreAction.NO_ACTION,
            adding_action=AddingAction.DISABLED,
            momentum_level=momentum_level,
            structural_level=structural_level,
            hard_invalidation_level=None,
            is_extended_from_momentum=is_extended,
            position_role=None,
            holding_horizon=None,
            strategic_review_required=False,
        )

    hard_invalidation_level = position.stop_loss_price
    stop_breached = _level_breached(
        current_price,
        position.stop_loss_price,
        position.direction,
    )
    thesis_breached = _confirmed_level_breached(
        latest_confirmed_price,
        (
            position.thesis_support_price
            if position.direction is PositionDirection.LONG
            else position.thesis_resistance_price
        ),
        position.direction,
    )
    if stop_breached or thesis_breached:
        return DecisionState(
            ribbon_state=ribbon_state,
            momentum_state=momentum_state,
            position_phase=PositionPhase.THESIS_INVALIDATED,
            core_action=CoreAction.EXIT,
            adding_action=AddingAction.DISABLED,
            momentum_level=momentum_level,
            structural_level=structural_level,
            hard_invalidation_level=hard_invalidation_level,
            is_extended_from_momentum=is_extended,
            position_role=position.role,
            holding_horizon=position.holding_horizon,
            strategic_review_required=True,
        )

    if _target_reached(current_price, position):
        return DecisionState(
            ribbon_state=ribbon_state,
            momentum_state=momentum_state,
            position_phase=PositionPhase.TARGET_REACHED,
            core_action=CoreAction.REVIEW_PROFIT,
            adding_action=AddingAction.PAUSE_ADDS,
            momentum_level=momentum_level,
            structural_level=structural_level,
            hard_invalidation_level=hard_invalidation_level,
            is_extended_from_momentum=is_extended,
            position_role=position.role,
            holding_horizon=position.holding_horizon,
            strategic_review_required=True,
        )

    structural_level_breached = _confirmed_level_breached(
        latest_confirmed_price,
        structural_level,
        position.direction,
    )
    if structural_level_breached:
        is_long_term_core = (
            position.role is PositionRole.CORE
            and position.holding_horizon in LONG_TERM_HORIZONS
        )
        return DecisionState(
            ribbon_state=ribbon_state,
            momentum_state=momentum_state,
            position_phase=(
                PositionPhase.EXECUTION_STRUCTURE_BROKEN
                if is_long_term_core
                else PositionPhase.THESIS_AT_RISK
            ),
            core_action=(
                CoreAction.HOLD if is_long_term_core else CoreAction.REDUCE_RISK
            ),
            adding_action=AddingAction.PAUSE_ADDS,
            momentum_level=momentum_level,
            structural_level=structural_level,
            hard_invalidation_level=hard_invalidation_level,
            is_extended_from_momentum=is_extended,
            position_role=position.role,
            holding_horizon=position.holding_horizon,
            strategic_review_required=is_long_term_core,
        )

    momentum_level_breached = _confirmed_level_breached(
        latest_confirmed_price,
        momentum_level,
        position.direction,
    )
    if momentum_level_breached:
        return DecisionState(
            ribbon_state=ribbon_state,
            momentum_state=momentum_state,
            position_phase=PositionPhase.MOMENTUM_WARNING,
            core_action=CoreAction.HOLD,
            adding_action=AddingAction.PAUSE_ADDS,
            momentum_level=momentum_level,
            structural_level=structural_level,
            hard_invalidation_level=hard_invalidation_level,
            is_extended_from_momentum=is_extended,
            position_role=position.role,
            holding_horizon=position.holding_horizon,
            strategic_review_required=False,
        )

    return DecisionState(
        ribbon_state=ribbon_state,
        momentum_state=momentum_state,
        position_phase=(
            PositionPhase.HOLDING_EXTENDED if is_extended else PositionPhase.HOLDING
        ),
        core_action=CoreAction.HOLD,
        adding_action=(
            AddingAction.PAUSE_ADDS
            if is_extended
            else AddingAction.ALLOW_ONLY_AFTER_CONFIRMATION
        ),
        momentum_level=momentum_level,
        structural_level=structural_level,
        hard_invalidation_level=hard_invalidation_level,
        is_extended_from_momentum=is_extended,
        position_role=position.role,
        holding_horizon=position.holding_horizon,
        strategic_review_required=False,
    )
