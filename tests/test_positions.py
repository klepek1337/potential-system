import json
import tempfile
import unittest
from pathlib import Path

from ma_alert_bot.positions import (
    PositionDirection,
    PositionSnapshot,
    apply_manual_override,
    load_position_plans,
)


class PositionPlanTests(unittest.TestCase):
    def test_loads_manual_position_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            configuration_path = Path(temporary_directory) / "positions.json"
            configuration_path.write_text(
                json.dumps(
                    {
                        "positions": [
                            {
                                "instrument_id": "example-usdt-swap",
                                "direction": "long",
                                "entry_price": 100,
                                "stop_loss_price": 95,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            plans = load_position_plans(configuration_path)

        plan = plans["EXAMPLE-USDT-SWAP"]
        self.assertEqual(plan.direction, PositionDirection.LONG)
        self.assertEqual(plan.entry_price, 100.0)
        self.assertEqual(plan.stop_loss_price, 95.0)

    def test_manual_plan_overrides_thesis_but_not_live_entry(self) -> None:
        live_position = PositionSnapshot(
            instrument_id="EXAMPLE-USDT-SWAP",
            direction=PositionDirection.LONG,
            entry_price=100.0,
            position_size=1.0,
            leverage=2.0,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            configuration_path = Path(temporary_directory) / "positions.json"
            configuration_path.write_text(
                json.dumps(
                    {
                        "positions": [
                            {
                                "instrument_id": "EXAMPLE-USDT-SWAP",
                                "stop_loss_price": 95,
                                "thesis": "H4 must defend support",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            plan = load_position_plans(configuration_path)["EXAMPLE-USDT-SWAP"]

        merged_position = apply_manual_override(live_position, plan)

        self.assertEqual(merged_position.entry_price, 100.0)
        self.assertEqual(merged_position.leverage, 2.0)
        self.assertEqual(merged_position.stop_loss_price, 95.0)
        self.assertEqual(merged_position.thesis, "H4 must defend support")


if __name__ == "__main__":
    unittest.main()
