import tempfile
from datetime import UTC, datetime
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

    def test_saves_and_reads_latest_ai_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = AlertStateStore(Path(temporary_directory) / "state.sqlite3")
            first_report = {"report_title": "first"}
            second_report = {"report_title": "second"}

            store.save_ai_report(
                report_type="daily",
                scope_key="portfolio",
                created_at_utc=datetime.now(tz=UTC).isoformat(),
                report=first_report,
            )
            store.save_ai_report(
                report_type="daily",
                scope_key="portfolio",
                created_at_utc=datetime.now(tz=UTC).isoformat(),
                report=second_report,
            )

            loaded_report = store.get_latest_ai_report("daily", "portfolio")

        self.assertEqual(loaded_report, second_report)

    def test_position_risk_alert_can_be_rearmed_after_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = AlertStateStore(Path(temporary_directory) / "state.sqlite3")

            first_activation = store.activate_position_risk_alert_if_new(
                "EXAMPLE-USDT-SWAP",
                "stop_near",
            )
            repeated_activation = store.activate_position_risk_alert_if_new(
                "EXAMPLE-USDT-SWAP",
                "stop_near",
            )
            store.clear_position_risk_alert(
                "EXAMPLE-USDT-SWAP",
                "stop_near",
            )
            rearmed_activation = store.activate_position_risk_alert_if_new(
                "EXAMPLE-USDT-SWAP",
                "stop_near",
            )

        self.assertTrue(first_activation)
        self.assertFalse(repeated_activation)
        self.assertTrue(rearmed_activation)


if __name__ == "__main__":
    unittest.main()
