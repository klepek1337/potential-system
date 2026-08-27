import unittest
from unittest.mock import patch

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

    @patch("ma_alert_bot.okx_client.get_json")
    def test_reads_public_derivative_metrics(self, get_json) -> None:
        get_json.side_effect = [
            {
                "code": "0",
                "data": [
                    {
                        "last": "102",
                        "open24h": "100",
                        "high24h": "103",
                        "low24h": "99",
                        "volCcy24h": "5000",
                    }
                ],
            },
            {"code": "0", "data": [{"markPx": "101.9"}]},
            {"code": "0", "data": [{"oi": "1000", "oiCcy": "10"}]},
            {
                "code": "0",
                "data": [
                    {
                        "fundingRate": "0.0001",
                        "nextFundingRate": "0.0002",
                        "nextFundingTime": "2000",
                    }
                ],
            },
        ]

        metrics = OkxMarketDataClient(
            "https://www.okx.com"
        ).get_derivative_metrics("EXAMPLE-USDT-SWAP")

        self.assertEqual(metrics.last_price, 102.0)
        self.assertEqual(metrics.mark_price, 101.9)
        self.assertEqual(metrics.open_interest_contracts, 1000.0)
        self.assertEqual(metrics.funding_rate, 0.0001)


if __name__ == "__main__":
    unittest.main()
