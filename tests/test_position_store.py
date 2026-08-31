import tempfile
import unittest
from pathlib import Path

from ma_alert_bot.models import ManualPosition, PositionSide
from ma_alert_bot.position_store import PositionStore


class PositionStoreTests(unittest.TestCase):
    def test_sets_replaces_and_removes_position(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PositionStore(Path(directory) / "positions.json")
            first = ManualPosition("SOL-USDT-SWAP", PositionSide.LONG, 100, 95, 2000, 4)
            replacement = ManualPosition("SOL-USDT-SWAP", PositionSide.LONG, 102, 98, 3000, 3)
            store.set(first)
            store.set(replacement)
            self.assertEqual(store.list_positions(), [replacement])
            self.assertTrue(store.remove("sol-usdt-swap"))
            self.assertEqual(store.list_positions(), [])

    def test_rejects_invalid_long_stop_on_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "positions.json"
            path.write_text(
                '[{"instrument_id":"BTC-USDT-SWAP","side":"long",'
                '"entry_price":100,"stop_price":101}]',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "long position stop"):
                PositionStore(path).list_positions()


if __name__ == "__main__":
    unittest.main()
