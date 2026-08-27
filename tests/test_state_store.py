import tempfile
import unittest
from pathlib import Path

from ma_alert_bot.state_store import AlertStateStore


class DailyReportStateTests(unittest.TestCase):
    def test_daily_report_is_recorded_per_instrument_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = AlertStateStore(Path(temporary_directory) / "state.sqlite3")

            self.assertFalse(
                store.was_daily_report_sent("BTC-USDT-SWAP", "2026-08-27")
            )
            store.mark_daily_report_sent("BTC-USDT-SWAP", "2026-08-27")

            self.assertTrue(
                store.was_daily_report_sent("BTC-USDT-SWAP", "2026-08-27")
            )
            self.assertFalse(
                store.was_daily_report_sent("ETH-USDT-SWAP", "2026-08-27")
            )
            self.assertFalse(
                store.was_daily_report_sent("BTC-USDT-SWAP", "2026-08-28")
            )


if __name__ == "__main__":
    unittest.main()
