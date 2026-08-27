import threading
import unittest

from ma_alert_bot.ai_dispatcher import AiReportDispatcher


class BlockingCoordinator:
    def __init__(self) -> None:
        self.daily_calls = 0
        self.event_calls: list[tuple[str, list[object], list[str]]] = []
        self.daily_started = threading.Event()
        self.release_daily = threading.Event()

    def send_daily_report_if_due(self, candles_by_instrument: dict) -> None:
        self.daily_calls += 1
        self.daily_started.set()
        self.release_daily.wait(timeout=2)

    def send_event_report(
        self,
        instrument_id: str,
        candles: list[object],
        market_events: list[str],
    ) -> None:
        self.event_calls.append((instrument_id, list(candles), list(market_events)))


class AiReportDispatcherTests(unittest.TestCase):
    def test_deduplicates_daily_task_while_one_is_pending(self) -> None:
        coordinator = BlockingCoordinator()
        dispatcher = AiReportDispatcher(coordinator)  # type: ignore[arg-type]

        dispatcher.submit_daily_report_if_due({"EXAMPLE-USDT-SWAP": []})
        self.assertTrue(coordinator.daily_started.wait(timeout=1))
        dispatcher.submit_daily_report_if_due({"EXAMPLE-USDT-SWAP": []})
        coordinator.release_daily.set()
        dispatcher.close()

        self.assertEqual(coordinator.daily_calls, 1)

    def test_drains_event_task_before_close(self) -> None:
        coordinator = BlockingCoordinator()
        dispatcher = AiReportDispatcher(coordinator)  # type: ignore[arg-type]

        dispatcher.submit_event_report(
            instrument_id="EXAMPLE-USDT-SWAP",
            candles=[],
            market_events=["Potwierdzone zamknięcie H4."],
        )
        dispatcher.close()

        self.assertEqual(
            coordinator.event_calls,
            [("EXAMPLE-USDT-SWAP", [], ["Potwierdzone zamknięcie H4."])],
        )


if __name__ == "__main__":
    unittest.main()
