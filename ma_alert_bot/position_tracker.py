from ma_alert_bot.okx_account import OkxReadOnlyAccountClient
from ma_alert_bot.positions import (
    PositionPlan,
    PositionSnapshot,
    PositionSource,
    apply_manual_override,
    manual_position_from_plan,
)


class PositionTracker:
    def __init__(
        self,
        source: PositionSource,
        plans: dict[str, PositionPlan],
        okx_account_client: OkxReadOnlyAccountClient | None,
    ) -> None:
        self._source = source
        self._plans = plans
        self._okx_account_client = okx_account_client
        self._positions: dict[str, PositionSnapshot] = {}

    def refresh(self) -> None:
        if self._source is PositionSource.MANUAL:
            self._positions = {
                instrument_id: manual_position_from_plan(plan)
                for instrument_id, plan in self._plans.items()
            }
            return

        if self._okx_account_client is None:
            raise RuntimeError("OKX account client is required for automatic positions")
        detected_positions = self._okx_account_client.get_open_positions()
        positions_by_instrument: dict[str, PositionSnapshot] = {}
        for position in detected_positions:
            if position.instrument_id in positions_by_instrument:
                raise RuntimeError(
                    "Multiple OKX positions for one instrument are not supported: "
                    f"{position.instrument_id}"
                )
            if self._source is PositionSource.OKX_WITH_MANUAL_OVERRIDE:
                position = apply_manual_override(
                    position,
                    self._plans.get(position.instrument_id),
                )
            positions_by_instrument[position.instrument_id] = position
        self._positions = positions_by_instrument

    def get_position(self, instrument_id: str) -> PositionSnapshot | None:
        return self._positions.get(instrument_id)
