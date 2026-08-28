import unittest

from ma_alert_bot.decision_state import (
    AddingAction,
    CoreAction,
    PositionPhase,
    RibbonState,
    build_decision_state,
    classify_ribbon,
)
from ma_alert_bot.positions import (
    HoldingHorizon,
    PositionDirection,
    PositionRole,
    PositionSnapshot,
)


BULLISH_LEVELS = {20: 100.0, 50: 95.0, 120: 90.0, 200: 80.0}
BEARISH_LEVELS = {20: 90.0, 50: 95.0, 120: 100.0, 200: 110.0}


def build_long_position(**overrides) -> PositionSnapshot:
    position_values = {
        "instrument_id": "EXAMPLE-USDT-SWAP",
        "direction": PositionDirection.LONG,
        "entry_price": 95.0,
        "stop_loss_price": 90.0,
    }
    position_values.update(overrides)
    return PositionSnapshot(**position_values)


def build_short_position(**overrides) -> PositionSnapshot:
    position_values = {
        "instrument_id": "EXAMPLE-USDT-SWAP",
        "direction": PositionDirection.SHORT,
        "entry_price": 95.0,
        "stop_loss_price": 110.0,
    }
    position_values.update(overrides)
    return PositionSnapshot(**position_values)


class DecisionStateTests(unittest.TestCase):
    def test_classifies_complete_ordered_ribbons(self) -> None:
        self.assertEqual(
            classify_ribbon(105.0, BULLISH_LEVELS),
            RibbonState.FULL_BULLISH,
        )
        self.assertEqual(
            classify_ribbon(85.0, BEARISH_LEVELS),
            RibbonState.FULL_BEARISH,
        )

    def test_long_close_below_sma20_only_pauses_adds(self) -> None:
        state = build_decision_state(
            current_price=99.0,
            latest_confirmed_price=99.0,
            moving_average_levels=BULLISH_LEVELS,
            position=build_long_position(),
        )

        self.assertEqual(state.position_phase, PositionPhase.MOMENTUM_WARNING)
        self.assertEqual(state.core_action, CoreAction.HOLD)
        self.assertEqual(state.adding_action, AddingAction.PAUSE_ADDS)

    def test_long_close_below_sma50_escalates_to_reduce_risk(self) -> None:
        state = build_decision_state(
            current_price=94.0,
            latest_confirmed_price=94.0,
            moving_average_levels=BULLISH_LEVELS,
            position=build_long_position(),
        )

        self.assertEqual(state.position_phase, PositionPhase.THESIS_AT_RISK)
        self.assertEqual(state.core_action, CoreAction.REDUCE_RISK)

    def test_long_term_core_is_not_closed_by_h4_structure_alone(self) -> None:
        state = build_decision_state(
            current_price=94.0,
            latest_confirmed_price=94.0,
            moving_average_levels=BULLISH_LEVELS,
            position=build_long_position(
                role=PositionRole.CORE,
                holding_horizon=HoldingHorizon.CYCLE,
            ),
        )

        self.assertEqual(
            state.position_phase,
            PositionPhase.EXECUTION_STRUCTURE_BROKEN,
        )
        self.assertEqual(state.core_action, CoreAction.HOLD)
        self.assertEqual(state.adding_action, AddingAction.PAUSE_ADDS)
        self.assertTrue(state.strategic_review_required)

    def test_hard_stop_has_priority_over_moving_average_state(self) -> None:
        state = build_decision_state(
            current_price=89.0,
            latest_confirmed_price=96.0,
            moving_average_levels=BULLISH_LEVELS,
            position=build_long_position(),
        )

        self.assertEqual(state.position_phase, PositionPhase.THESIS_INVALIDATED)
        self.assertEqual(state.core_action, CoreAction.EXIT)
        self.assertEqual(state.adding_action, AddingAction.DISABLED)

    def test_short_logic_is_symmetric(self) -> None:
        momentum_warning = build_decision_state(
            current_price=91.0,
            latest_confirmed_price=91.0,
            moving_average_levels=BEARISH_LEVELS,
            position=build_short_position(),
        )
        structural_risk = build_decision_state(
            current_price=96.0,
            latest_confirmed_price=96.0,
            moving_average_levels=BEARISH_LEVELS,
            position=build_short_position(),
        )

        self.assertEqual(
            momentum_warning.position_phase,
            PositionPhase.MOMENTUM_WARNING,
        )
        self.assertEqual(momentum_warning.core_action, CoreAction.HOLD)
        self.assertEqual(
            structural_risk.position_phase,
            PositionPhase.THESIS_AT_RISK,
        )
        self.assertEqual(structural_risk.core_action, CoreAction.REDUCE_RISK)

    def test_extension_uses_ribbon_width_instead_of_fixed_percent(self) -> None:
        state = build_decision_state(
            current_price=111.0,
            latest_confirmed_price=105.0,
            moving_average_levels=BULLISH_LEVELS,
            position=build_long_position(),
        )

        self.assertTrue(state.is_extended_from_momentum)
        self.assertEqual(state.position_phase, PositionPhase.HOLDING_EXTENDED)
        self.assertEqual(state.adding_action, AddingAction.PAUSE_ADDS)


if __name__ == "__main__":
    unittest.main()
