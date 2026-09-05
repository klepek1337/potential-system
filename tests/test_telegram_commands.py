import unittest

from ma_alert_bot.telegram_commands import normalize_okx_instrument_id


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


if __name__ == "__main__":
    unittest.main()
