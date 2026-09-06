import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ma_alert_bot.models import Candle
from ma_alert_bot.state_store import AlertStateStore
from ma_alert_bot.telegram_commands import TelegramCommandPoller, normalize_okx_instrument_id


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


class FakeMarketDataClient:
    def get_candles(self, instrument_id: str, interval: str) -> list[Candle]:
        return [
            Candle(
                opening_timestamp_ms=1,
                opening_price=100.0,
                highest_price=101.0,
                lowest_price=99.0,
                closing_price=100.0,
                is_confirmed=True,
            )
        ]


class InstrumentNormalizationTests(unittest.TestCase):
    def test_compact_symbol_becomes_okx_perpetual_instrument(self) -> None:
        self.assertEqual(
            normalize_okx_instrument_id("btcusdt"), "BTC-USDT-SWAP"
        )

    def test_spot_style_symbol_becomes_okx_perpetual_instrument(self) -> None:
        self.assertEqual(
            normalize_okx_instrument_id("ETH-USDT"), "ETH-USDT-SWAP"
        )

    def test_complete_okx_instrument_is_preserved(self) -> None:
        self.assertEqual(
            normalize_okx_instrument_id("SOL-USDT-SWAP"), "SOL-USDT-SWAP"
        )

    def test_non_usdt_symbol_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_okx_instrument_id("BTC-EUR")


class LongWatchStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_store = AlertStateStore(
            Path(self.temporary_directory.name) / "state.sqlite3"
        )
        self.notifier = FakeNotifier()
        self.poller = TelegramCommandPoller(
            bot_token="token",
            allowed_chat_id="1",
            market_data_client=FakeMarketDataClient(),
            notifier=self.notifier,
            state_store=self.state_store,
            enabled=True,
            minimum_normalized_histogram_slope=0.001,
        )

    @staticmethod
    def assessment(timestamp: int, one_hour_slope: float) -> SimpleNamespace:
        return SimpleNamespace(
            instrument_id="BTC-USDT-SWAP",
            timeframe_assessments=tuple(
                SimpleNamespace(
                    timeframe=timeframe,
                    candle_timestamp_ms=timestamp,
                    normalized_histogram_slope=(
                        one_hour_slope if timeframe == "1H" else 0.01
                    ),
                )
                for timeframe in ("1H", "2H", "4H", "1D")
            ),
        )

    def test_alerts_only_when_new_candle_starts_falling(self) -> None:
        self.assertEqual(self.poller._update_long_watch_state(self.assessment(1, 0.01)), ())
        self.assertEqual(
            self.poller._update_long_watch_state(self.assessment(2, -0.01)),
            ("1H",),
        )
        self.assertEqual(self.poller._update_long_watch_state(self.assessment(3, -0.02)), ())
        self.assertEqual(self.poller._update_long_watch_state(self.assessment(4, 0.01)), ())
        self.assertEqual(
            self.poller._update_long_watch_state(self.assessment(5, -0.01)),
            ("1H",),
        )

    def test_dynamic_instrument_is_active_without_restart(self) -> None:
        self.poller._add_dynamic_instrument("BCH-USDT-SWAP")

        self.assertEqual(
            self.poller.get_active_instrument_ids(("BTC-USDT-SWAP",)),
            ("BTC-USDT-SWAP", "BCH-USDT-SWAP"),
        )
        self.assertIn("bez restartu", self.notifier.messages[-1])


if __name__ == "__main__":
    unittest.main()
