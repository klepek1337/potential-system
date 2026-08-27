from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ma_alert_bot.ai_analysis import (
    AI_ANALYST_INSTRUCTIONS,
    AI_REPORT_JSON_SCHEMA,
    AiReportType,
    InstrumentMarketSnapshot,
    build_ai_request_payload,
    parse_ai_report,
)


OPENAI_REQUEST_TIMEOUT_SECONDS = 180.0
WEB_SEARCH_TOOL_TYPE = "web_search"
OPENAI_REPORT_SCHEMA_NAME = "cryptostrata_decision_report"
HTTPS_URL_PREFIX = "https://"


def _normalize_source_url(source_url: str) -> str:
    parsed_url = urlsplit(source_url)
    normalized_path = parsed_url.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed_url.scheme.lower(),
            parsed_url.netloc.lower(),
            normalized_path,
            parsed_url.query,
            "",
        )
    )


def _collect_https_urls(value: object) -> set[str]:
    collected_urls: set[str] = set()
    if isinstance(value, dict):
        for nested_value in value.values():
            collected_urls.update(_collect_https_urls(nested_value))
    elif isinstance(value, list):
        for nested_value in value:
            collected_urls.update(_collect_https_urls(nested_value))
    elif isinstance(value, str) and value.startswith(HTTPS_URL_PREFIX):
        collected_urls.add(_normalize_source_url(value))
    return collected_urls


def _validate_report_sources(
    report: dict[str, Any],
    response_source_urls: set[str],
) -> None:
    report_source_urls = {
        _normalize_source_url(fact["source_url"])
        for fact in report["facts"]
        if fact["source_url"] != "OKX_API_SNAPSHOT"
    }
    if not report_source_urls:
        raise ValueError("AI report contains no cited web source")
    unsupported_urls = report_source_urls.difference(response_source_urls)
    if unsupported_urls:
        raise ValueError(
            "AI report cites URLs absent from web-search sources: "
            + ", ".join(sorted(unsupported_urls))
        )


class OpenAiResearchClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        reasoning_effort: str,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "AI analysis requires the official openai package from requirements.txt"
            ) from error

        self._client = OpenAI(
            api_key=api_key,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        )
        self._model = model
        self._reasoning_effort = reasoning_effort

    def create_report(
        self,
        report_type: AiReportType,
        snapshots: list[InstrumentMarketSnapshot],
        market_events: list[str],
        previous_report: dict[str, Any] | None,
    ) -> dict[str, Any]:
        response = self._client.responses.create(
            model=self._model,
            reasoning={"effort": self._reasoning_effort},
            tools=[{"type": WEB_SEARCH_TOOL_TYPE}],
            tool_choice="required",
            instructions=AI_ANALYST_INSTRUCTIONS,
            input=build_ai_request_payload(
                report_type=report_type,
                snapshots=snapshots,
                market_events=market_events,
                previous_report=previous_report,
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": OPENAI_REPORT_SCHEMA_NAME,
                    "strict": True,
                    "schema": AI_REPORT_JSON_SCHEMA,
                }
            },
            include=["web_search_call.action.sources"],
            store=False,
        )
        response_text = response.output_text
        if not response_text:
            raise RuntimeError("OpenAI returned no report text")
        report = parse_ai_report(response_text)
        response_payload = response.model_dump()
        response_source_urls = _collect_https_urls(response_payload)
        _validate_report_sources(report, response_source_urls)
        return report
