import unittest

from ma_alert_bot.notifications import (
    build_current_levels_message,
    build_program_started_message,
    split_telegram_message,
)


class StartupNotificationTests(unittest.TestCase):
    def test_started_message_contains_configuration(self) -> None:
        message = build_program_started_message(
            instrument_ids=("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
            touch_margin_ratio=0.001,
        )

        self.assertIn("scanner uruchomiony", message)
        self.assertIn("0.1%", message)
        self.assertIn("BTC-USDT-SWAP, ETH-USDT-SWAP", message)

    def test_level_message_contains_price_and_all_averages(self) -> None:
        message = build_current_levels_message(
            instrument_id="BTC-USDT-SWAP",
            current_price=102.0,
            moving_average_levels={20: 100.0, 50: 101.0, 120: 103.0, 200: 104.0},
        )

        self.assertIn("Cena: 102", message)
        self.assertIn("SMA 20: 100", message)
        self.assertIn("SMA 50: 101", message)
        self.assertIn("SMA 120: 103", message)
        self.assertIn("SMA 200: 104", message)
        self.assertIn("nad", message)
        self.assertIn("pod", message)

    def test_long_message_is_split_without_losing_content(self) -> None:
        message = "pierwszy akapit\n\ndrugi akapit\n\ntrzeci akapit"

        message_parts = split_telegram_message(message, maximum_length=20)

        self.assertGreater(len(message_parts), 1)
        self.assertEqual("".join(message_parts).replace("\n", ""), message.replace("\n", ""))


if __name__ == "__main__":
    unittest.main()
