import unittest
from unittest.mock import patch

from ma_alert_bot.okx_account import OkxReadOnlyAccountClient
from ma_alert_bot.positions import PositionDirection


class OkxReadOnlyAccountClientTests(unittest.TestCase):
    @patch("ma_alert_bot.okx_account.get_json")
    def test_fetches_and_parses_long_and_net_short_positions(self, get_json) -> None:
        get_json.return_value = {
            "code": "0",
            "data": [
                {
                    "instId": "EXAMPLE-LONG-USDT-SWAP",
                    "posSide": "long",
                    "pos": "1",
                    "avgPx": "100",
                    "lever": "2",
                    "liqPx": "60",
                    "upl": "5",
                },
                {
                    "instId": "EXAMPLE-SHORT-USDT-SWAP",
                    "posSide": "net",
                    "pos": "-2",
                    "avgPx": "100",
                    "lever": "3",
                    "liqPx": "140",
                    "upl": "-2",
                },
                {"instId": "EXAMPLE-FLAT-USDT-SWAP", "pos": "0"},
            ],
        }
        client = OkxReadOnlyAccountClient(
            api_base_url="https://www.okx.com",
            api_key="key",
            api_secret="secret",
            api_passphrase="passphrase",
        )

        positions = client.get_open_positions()

        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0].direction, PositionDirection.LONG)
        self.assertEqual(positions[0].position_size, 1.0)
        self.assertEqual(positions[1].direction, PositionDirection.SHORT)
        self.assertEqual(positions[1].position_size, 2.0)
        request_headers = get_json.call_args.kwargs["additional_headers"]
        self.assertEqual(request_headers["OK-ACCESS-KEY"], "key")
        self.assertTrue(request_headers["OK-ACCESS-SIGN"])
        self.assertTrue(request_headers["OK-ACCESS-TIMESTAMP"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
