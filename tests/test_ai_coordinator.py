import tempfile
import unittest
from datetime import time
from pathlib import Path

from ma_alert_bot.ai_analysis import AiReportType, OkxDerivativeMetrics
from ma_alert_bot.ai_coordinator import AiReportCoordinator
from ma_alert_bot.models import Candle
from ma_alert_bot.state_store import AlertStateStore
from tests.test_ai_analysis import build_valid_report


class FakeResearchClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_report(
        self,
        report_type,
        snapshots,
        market_events,
        previous_report,
    ):
        self.calls.append(
            {
                "report_type": report_type,
                "snapshots": snapshots,
                "market_events": market_events,
                "previous_report": previous_report,
            }
        )
        return build_valid_report()


class FakeMarketDataClient:
    def get_derivative_metrics(self, instrument_id):
        return OkxDerivativeMetrics(
            last_price=102.0,
            mark_price=101.9,
            open_interest_contracts=1000.0,
            open_interest_currency=10.0,
            funding_rate=0.0001,
            next_funding_rate=0.0001,
            next_funding_timestamp_ms=1,
            twenty_four_hour_open_price=100.0,
            twenty_four_hour_high_price=103.0,
            twenty_four_hour_low_price=99.0,
            twenty_four_hour_volume_currency=5000.0,
        )


class FakePositionTracker:
    def get_position(self, instrument_id):
        return None


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_long(self, message: str) -> None:
        self.messages.append(message)


def build_candles() -> list[Candle]:
    return [
        Candle(1, 99.0, 101.0, 98.0, 100.0, True),
        Candle(2, 100.0, 103.0, 99.0, 102.0, True),
        Candle(3, 102.0, 103.0, 101.0, 102.0, False),
    ]


class AiCoordinatorTests(unittest.TestCase):
    def test_daily_report_is_sent_only_once_per_local_date(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            research_client = FakeResearchClient()
            notifier = FakeNotifier()
            coordinator = AiReportCoordinator(
                research_client=research_client,
                market_data_client=FakeMarketDataClient(),
                position_tracker=FakePositionTracker(),
                state_store=AlertStateStore(
                    Path(temporary_directory) / "state.sqlite3"
                ),
                notifier=notifier,
                timezone_name="Europe/Luxembourg",
                daily_report_local_time=time(hour=0, minute=0),
                event_reports_enabled=True,
            )
            candles_by_instrument = {"EXAMPLE-USDT-SWAP": build_candles()}

            coordinator.send_daily_report_if_due(candles_by_instrument)
            coordinator.send_daily_report_if_due(candles_by_instrument)

        self.assertEqual(len(research_client.calls), 1)
        self.assertEqual(
            research_client.calls[0]["report_type"],
            AiReportType.DAILY,
        )
        self.assertEqual(len(notifier.messages), 1)

    def test_event_report_receives_market_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            research_client = FakeResearchClient()
            coordinator = AiReportCoordinator(
                research_client=research_client,
                market_data_client=FakeMarketDataClient(),
                position_tracker=FakePositionTracker(),
                state_store=AlertStateStore(
                    Path(temporary_directory) / "state.sqlite3"
                ),
                notifier=FakeNotifier(),
                timezone_name="Europe/Luxembourg",
                daily_report_local_time=time(hour=0, minute=0),
                event_reports_enabled=True,
            )

            coordinator.send_event_report(
                instrument_id="EXAMPLE-USDT-SWAP",
                candles=build_candles(),
                market_events=["Potwierdzone zamknięcie pod SMA 50."],
            )

        self.assertEqual(len(research_client.calls), 1)
        self.assertEqual(
            research_client.calls[0]["market_events"],
            ["Potwierdzone zamknięcie pod SMA 50."],
        )


if __name__ == "__main__":
    unittest.main()
