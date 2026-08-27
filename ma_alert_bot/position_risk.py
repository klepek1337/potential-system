from dataclasses import dataclass
from enum import StrEnum

from ma_alert_bot.positions import PositionDirection, PositionSnapshot


PERCENT_MULTIPLIER = 100.0


class PositionRiskType(StrEnum):
    STOP_NEAR = "stop_near"
    STOP_BREACHED = "stop_breached"
    LIQUIDATION_NEAR = "liquidation_near"


@dataclass(frozen=True)
class PositionRiskAlert:
    risk_type: PositionRiskType
    message: str


def _adverse_distance_percent(
    current_price: float,
    risk_level: float,
    direction: PositionDirection,
) -> float:
    if direction is PositionDirection.LONG:
        price_distance = current_price - risk_level
    else:
        price_distance = risk_level - current_price
    return price_distance / current_price * PERCENT_MULTIPLIER


def evaluate_position_risks(
    current_price: float,
    position: PositionSnapshot | None,
    stop_warning_distance_percent: float,
    liquidation_warning_distance_percent: float,
) -> dict[PositionRiskType, PositionRiskAlert]:
    if position is None:
        return {}

    active_alerts: dict[PositionRiskType, PositionRiskAlert] = {}
    if position.stop_loss_price is not None:
        stop_distance_percent = _adverse_distance_percent(
            current_price,
            position.stop_loss_price,
            position.direction,
        )
        if stop_distance_percent <= 0:
            active_alerts[PositionRiskType.STOP_BREACHED] = PositionRiskAlert(
                risk_type=PositionRiskType.STOP_BREACHED,
                message=(
                    f"🔴 {position.instrument_id}: cena {current_price:g} naruszyła "
                    f"skonfigurowany stop {position.stop_loss_price:g}."
                ),
            )
        elif stop_distance_percent <= stop_warning_distance_percent:
            active_alerts[PositionRiskType.STOP_NEAR] = PositionRiskAlert(
                risk_type=PositionRiskType.STOP_NEAR,
                message=(
                    f"🟠 {position.instrument_id}: do stopa "
                    f"{position.stop_loss_price:g} pozostało "
                    f"{stop_distance_percent:.2f}%."
                ),
            )

    if position.liquidation_price is not None:
        liquidation_distance_percent = _adverse_distance_percent(
            current_price,
            position.liquidation_price,
            position.direction,
        )
        if liquidation_distance_percent <= liquidation_warning_distance_percent:
            active_alerts[PositionRiskType.LIQUIDATION_NEAR] = PositionRiskAlert(
                risk_type=PositionRiskType.LIQUIDATION_NEAR,
                message=(
                    f"🚨 {position.instrument_id}: odległość do likwidacji "
                    f"{position.liquidation_price:g} wynosi "
                    f"{liquidation_distance_percent:.2f}%."
                ),
            )
    return active_alerts
