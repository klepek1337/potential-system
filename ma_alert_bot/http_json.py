import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HTTP_GET_METHOD = "GET"
HTTP_POST_METHOD = "POST"
JSON_CONTENT_TYPE = "application/json"


def get_json(
    base_url: str,
    path: str,
    query_parameters: Mapping[str, str],
    timeout_seconds: float,
    user_agent: str,
    additional_headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    encoded_query = urlencode(query_parameters)
    request_url = f"{base_url.rstrip('/')}{path}"
    if encoded_query:
        request_url = f"{request_url}?{encoded_query}"
    request_headers = {"User-Agent": user_agent}
    if additional_headers is not None:
        request_headers.update(additional_headers)
    request = Request(
        request_url,
        method=HTTP_GET_METHOD,
        headers=request_headers,
    )
    return execute_json_request(request, timeout_seconds)


def post_json(
    base_url: str,
    path: str,
    request_payload: Mapping[str, object],
    timeout_seconds: float,
    user_agent: str,
) -> dict[str, Any]:
    request_url = f"{base_url.rstrip('/')}{path}"
    encoded_payload = json.dumps(request_payload).encode("utf-8")
    request = Request(
        request_url,
        data=encoded_payload,
        method=HTTP_POST_METHOD,
        headers={
            "Content-Type": JSON_CONTENT_TYPE,
            "User-Agent": user_agent,
        },
    )
    return execute_json_request(request, timeout_seconds)


def execute_json_request(request: Request, timeout_seconds: float) -> dict[str, Any]:
    with urlopen(request, timeout=timeout_seconds) as response:
        response_body = response.read().decode("utf-8")
    parsed_response = json.loads(response_body)
    if not isinstance(parsed_response, dict):
        raise ValueError("Expected a JSON object response")
    return parsed_response
