import unittest

from ma_alert_bot.okx_client import OkxMarketDataClient


class OkxCandleParsingTests(unittest.TestCase):
    def test_parses_documented_okx_candle_shape(self) -> None:
        raw_candle = [
            "1597026383085",
            "3.721",
            "3.743",
            "3.677",
            "3.708",
            "8422410",
            "22698348.04828491",
            "12698348.04828491",
            "1",
        ]

        candle = OkxMarketDataClient._parse_candle(raw_candle)

        self.assertEqual(candle.opening_timestamp_ms, 1597026383085)
        self.assertEqual(candle.opening_price, 3.721)
        self.assertEqual(candle.highest_price, 3.743)
        self.assertEqual(candle.lowest_price, 3.677)
        self.assertEqual(candle.closing_price, 3.708)
        self.assertTrue(candle.is_confirmed)


if __name__ == "__main__":
    unittest.main()

