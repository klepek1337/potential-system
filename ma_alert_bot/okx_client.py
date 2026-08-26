from ma_alert_bot.http_json import get_json
from ma_alert_bot.models import Candle


OKX_CANDLES_PATH = "/api/v5/market/candles"
OKX_SUCCESS_CODE = "0"
OKX_CANDLE_INTERVAL = "4H"
OKX_CANDLE_LIMIT = 300
OKX_CONFIRMED_CANDLE_VALUE = "1"
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "okx-ma-telegram-alerts/0.1"


class OkxMarketDataClient:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url

    def close(self) -> None:
        return None

    def get_four_hour_candles(self, instrument_id: str) -> list[Candle]:
        response_payload = get_json(
            base_url=self._api_base_url,
            path=OKX_CANDLES_PATH,
            query_parameters={
                "instId": instrument_id,
                "bar": OKX_CANDLE_INTERVAL,
                "limit": str(OKX_CANDLE_LIMIT),
            },
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
        )
        self._raise_for_api_error(response_payload)

        candles = [self._parse_candle(raw_candle) for raw_candle in response_payload["data"]]
        candles.sort(key=lambda candle: candle.opening_timestamp_ms)
        return candles

    @staticmethod
    def _raise_for_api_error(response_payload: dict[str, object]) -> None:
        response_code = str(response_payload.get("code", ""))
        if response_code != OKX_SUCCESS_CODE:
            error_message = str(response_payload.get("msg", "Unknown OKX API error"))
            raise RuntimeError(f"OKX API error {response_code}: {error_message}")

    @staticmethod
    def _parse_candle(raw_candle: list[str]) -> Candle:
        minimum_expected_fields = 9
        if len(raw_candle) < minimum_expected_fields:
            raise ValueError(f"Unexpected OKX candle payload: {raw_candle!r}")

        return Candle(
            opening_timestamp_ms=int(raw_candle[0]),
            opening_price=float(raw_candle[1]),
            highest_price=float(raw_candle[2]),
            lowest_price=float(raw_candle[3]),
            closing_price=float(raw_candle[4]),
            is_confirmed=raw_candle[8] == OKX_CONFIRMED_CANDLE_VALUE,
        )
