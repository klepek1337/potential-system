import json
import sys
import types
import unittest
from unittest.mock import patch

from ma_alert_bot.ai_analysis import AiReportType
from ma_alert_bot.openai_research import OpenAiResearchClient
from tests.test_ai_analysis import build_valid_report


class FakeResponsesApi:
    def __init__(self) -> None:
        self.last_request = None
        self.output_text = json.dumps(build_valid_report())

    def create(self, **request):
        self.last_request = request
        response = types.SimpleNamespace(
            output_text=self.output_text,
        )
        response.model_dump = lambda: {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [{"url": "https://example.com/source"}]
                    },
                }
            ]
        }
        return response


class FakeOpenAiSdkClient:
    def __init__(self, **configuration) -> None:
        self.configuration = configuration
        self.responses = FakeResponsesApi()


class OpenAiResearchClientTests(unittest.TestCase):
    def test_requires_web_search_and_strict_json_schema(self) -> None:
        created_clients = []

        def create_fake_client(**configuration):
            client = FakeOpenAiSdkClient(**configuration)
            created_clients.append(client)
            return client

        fake_openai_module = types.SimpleNamespace(OpenAI=create_fake_client)
        with patch.dict(sys.modules, {"openai": fake_openai_module}):
            research_client = OpenAiResearchClient(
                api_key="test-key",
                model="test-model",
                reasoning_effort="high",
            )
            report = research_client.create_report(
                report_type=AiReportType.DAILY,
                snapshots=[],
                market_events=[],
                previous_report=None,
            )

        request = created_clients[0].responses.last_request
        self.assertEqual(request["tools"], [{"type": "web_search"}])
        self.assertEqual(request["tool_choice"], "required")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertFalse(request["store"])

    def test_accepts_source_url_with_fragment_from_model(self) -> None:
        client = object.__new__(OpenAiResearchClient)
        fake_openai_client = FakeOpenAiSdkClient()
        fake_openai_client.responses.output_text = (
            fake_openai_client.responses.output_text.replace(
                "https://example.com/source",
                "https://example.com/source#section",
            )
        )
        client._client = fake_openai_client
        client._model = "example-model"
        client._reasoning_effort = "high"

        report = client.create_report(
            report_type=AiReportType.DAILY,
            snapshots=[],
            market_events=[],
            previous_report=None,
        )

        self.assertEqual(
            report["facts"][1]["source_url"],
            "https://example.com/source#section",
        )
        self.assertEqual(report["report_title"], "Testowy raport AI")


if __name__ == "__main__":
    unittest.main()
