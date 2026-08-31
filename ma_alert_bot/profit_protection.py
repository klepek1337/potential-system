from ma_alert_bot.models import (
    DominantEmaCandidate,
    ManualPosition,
    PositionSide,
    ProfitProtectionAssessment,
)


def directional_change(start: float, end: float, side: PositionSide) -> float:
    return end - start if side is PositionSide.LONG else start - end


def assess_profit_protection(
    position: ManualPosition,
    current_price: float,
    stop_anchor: float,
    candidate: DominantEmaCandidate,
    previous_stage: int,
) -> ProfitProtectionAssessment:
    initial_risk_per_unit = abs(position.entry_price - position.stop_price)
    if initial_risk_per_unit <= 0:
        raise ValueError("Position must have positive initial risk")
    open_profit_per_unit = directional_change(position.entry_price, current_price, position.side)
    r_multiple = open_profit_per_unit / initial_risk_per_unit
    distance_atr = abs(current_price - candidate.value) / candidate.atr

    stage, target_reduction = 0, 0
    if r_multiple >= 1.0:
        stage, target_reduction = 1, 50
    if r_multiple >= 2.0:
        stage, target_reduction = 2, 65
    if r_multiple >= 3.0 or distance_atr >= 2.5:
        stage, target_reduction = 3, 80

    previous_target = {0: 0, 1: 50, 2: 65, 3: 80}.get(previous_stage, 80)
    newly_recommended = max(0, target_reduction - previous_target)
    remaining_ratio = (100 - target_reduction) / 100.0
    realized_ratio = target_reduction / 100.0
    protected_per_unit = (
        realized_ratio * open_profit_per_unit
        + remaining_ratio * directional_change(position.entry_price, stop_anchor, position.side)
    )
    implied_base_units = (
        position.position_value_usd / current_price
        if position.position_value_usd is not None
        else None
    )
    projected_total = (
        protected_per_unit * implied_base_units
        if implied_base_units is not None
        else None
    )
    return ProfitProtectionAssessment(
        r_multiple=r_multiple,
        distance_from_ema_atr=distance_atr,
        target_reduction_percent=target_reduction,
        newly_recommended_reduction_percent=newly_recommended,
        remaining_percent=100 - target_reduction,
        protected_pnl_per_unit=protected_per_unit,
        projected_total_pnl=projected_total,
        stage=stage,
    )
