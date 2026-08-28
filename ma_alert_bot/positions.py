import json
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path


class PositionDirection(StrEnum):
    LONG = "long"
    SHORT = "short"


class PositionSource(StrEnum):
    MANUAL = "manual"
    OKX_READ_ONLY = "okx_read_only"
    OKX_WITH_MANUAL_OVERRIDE = "okx_with_manual_override"


class PositionRole(StrEnum):
    CORE = "core"
    TACTICAL = "tactical"


class HoldingHorizon(StrEnum):
    TACTICAL_H4 = "tactical_h4"
    SWING_D1 = "swing_d1"
    POSITION_W1 = "position_w1"
    CYCLE = "cycle"


@dataclass(frozen=True)
class PositionPlan:
    instrument_id: str
    direction: PositionDirection | None = None
    entry_price: float | None = None
    position_size: float | None = None
    stop_loss_price: float | None = None
    target_price: float | None = None
    thesis_support_price: float | None = None
    thesis_resistance_price: float | None = None
    thesis: str | None = None
    role: PositionRole = PositionRole.CORE
    holding_horizon: HoldingHorizon = HoldingHorizon.SWING_D1


@dataclass(frozen=True)
class PositionSnapshot:
    instrument_id: str
    direction: PositionDirection
    entry_price: float
    position_size: float | None = None
    stop_loss_price: float | None = None
    target_price: float | None = None
    thesis_support_price: float | None = None
    thesis_resistance_price: float | None = None
    thesis: str | None = None
    leverage: float | None = None
    liquidation_price: float | None = None
    unrealized_profit: float | None = None
    role: PositionRole = PositionRole.CORE
    holding_horizon: HoldingHorizon = HoldingHorizon.SWING_D1


def _optional_positive_float(raw_value: object, field_name: str) -> float | None:
    if raw_value is None:
        return None
    parsed_value = float(raw_value)
    if parsed_value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return parsed_value


def load_position_plans(configuration_path: Path) -> dict[str, PositionPlan]:
    if not configuration_path.exists():
        return {}

    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    raw_positions = configuration.get("positions", [])
    if not isinstance(raw_positions, list):
        raise ValueError("positions must be a JSON array")

    plans: dict[str, PositionPlan] = {}
    for raw_position in raw_positions:
        if not isinstance(raw_position, dict):
            raise ValueError("Every position plan must be a JSON object")
        instrument_id = str(raw_position["instrument_id"]).strip().upper()
        raw_direction = raw_position.get("direction")
        direction = (
            PositionDirection(str(raw_direction).strip().lower())
            if raw_direction is not None
            else None
        )
        plan = PositionPlan(
            instrument_id=instrument_id,
            direction=direction,
            entry_price=_optional_positive_float(
                raw_position.get("entry_price"), "entry_price"
            ),
            position_size=_optional_positive_float(
                raw_position.get("position_size"), "position_size"
            ),
            stop_loss_price=_optional_positive_float(
                raw_position.get("stop_loss_price"), "stop_loss_price"
            ),
            target_price=_optional_positive_float(
                raw_position.get("target_price"), "target_price"
            ),
            thesis_support_price=_optional_positive_float(
                raw_position.get("thesis_support_price"), "thesis_support_price"
            ),
            thesis_resistance_price=_optional_positive_float(
                raw_position.get("thesis_resistance_price"),
                "thesis_resistance_price",
            ),
            thesis=(str(raw_position["thesis"]).strip() or None)
            if raw_position.get("thesis") is not None
            else None,
            role=PositionRole(
                str(raw_position.get("role", PositionRole.CORE.value))
                .strip()
                .lower()
            ),
            holding_horizon=HoldingHorizon(
                str(
                    raw_position.get(
                        "holding_horizon",
                        HoldingHorizon.SWING_D1.value,
                    )
                )
                .strip()
                .lower()
            ),
        )
        if instrument_id in plans:
            raise ValueError(f"Duplicate position plan for {instrument_id}")
        plans[instrument_id] = plan
    return plans


def manual_position_from_plan(plan: PositionPlan) -> PositionSnapshot:
    if plan.direction is None or plan.entry_price is None:
        raise ValueError(
            f"Manual position {plan.instrument_id} requires direction and entry_price"
        )
    return PositionSnapshot(
        instrument_id=plan.instrument_id,
        direction=plan.direction,
        entry_price=plan.entry_price,
        position_size=plan.position_size,
        stop_loss_price=plan.stop_loss_price,
        target_price=plan.target_price,
        thesis_support_price=plan.thesis_support_price,
        thesis_resistance_price=plan.thesis_resistance_price,
        thesis=plan.thesis,
        role=plan.role,
        holding_horizon=plan.holding_horizon,
    )


def apply_manual_override(
    position: PositionSnapshot,
    plan: PositionPlan | None,
) -> PositionSnapshot:
    if plan is None:
        return position
    return replace(
        position,
        stop_loss_price=plan.stop_loss_price or position.stop_loss_price,
        target_price=plan.target_price or position.target_price,
        thesis_support_price=plan.thesis_support_price,
        thesis_resistance_price=plan.thesis_resistance_price,
        thesis=plan.thesis,
        role=plan.role,
        holding_horizon=plan.holding_horizon,
    )
