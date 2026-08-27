import json
import unittest

from ma_alert_bot.ai_analysis import (
    AiDecision,
    format_ai_report_for_telegram,
    parse_ai_report,
)


def build_valid_report() -> dict[str, object]:
    return {
        "report_title": "Testowy raport AI",
        "market_regime": "Mieszany",
        "facts": [
            {
                "statement": "Cena pochodzi ze snapshotu.",
                "source_title": "OKX_API_SNAPSHOT",
                "source_url": "OKX_API_SNAPSHOT",
            },
            {
                "statement": "Testowy fakt z internetu.",
                "source_title": "Primary source",
                "source_url": "https://example.com/source",
            },
        ],
        "inferences": ["Brak jednoznacznej przewagi."],
        "long_case": ["Long wymaga potwierdzenia."],
        "short_case": ["Short wymaga utraty wsparcia."],
        "position_decisions": [
            {
                "instrument_id": "EXAMPLE-USDT-SWAP",
                "decision": AiDecision.HOLD_DO_NOT_ADD.value,
                "rationale": "Teza pozostaje aktywna.",
                "do_not_add_reason": "Brak potwierdzenia.",
                "primary_danger": "Wzrost zmienności.",
                "invalidation_condition": "Zamknięcie H4 pod wsparciem.",
            }
        ],
        "what_changed": ["Cena przetestowała wsparcie."],
        "strongest_signal": "Obrona wsparcia.",
        "biggest_risk": "Słabość BTC.",
        "no_action_condition": "Brak potwierdzonego wybicia.",
        "data_gaps_or_conflicts": [],
    }


class AiAnalysisTests(unittest.TestCase):
    def test_parses_valid_structured_report(self) -> None:
        report = parse_ai_report(json.dumps(build_valid_report()))

        self.assertEqual(
            report["position_decisions"][0]["decision"],
            AiDecision.HOLD_DO_NOT_ADD.value,
        )

    def test_rejects_unknown_decision(self) -> None:
        report = build_valid_report()
        report["position_decisions"][0]["decision"] = "BUY_MORE"

        with self.assertRaises(ValueError):
            parse_ai_report(json.dumps(report))

    def test_formats_source_url_and_both_market_scenarios(self) -> None:
        message = format_ai_report_for_telegram(build_valid_report())

        self.assertIn("SCENARIUSZ LONG", message)
        self.assertIn("SCENARIUSZ SHORT", message)
        self.assertIn("https://example.com/source", message)
        self.assertIn("HOLD_DO_NOT_ADD", message)


if __name__ == "__main__":
    unittest.main()
