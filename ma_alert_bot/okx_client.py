from ma_alert_bot.ai_analysis import OkxDerivativeMetrics
from ma_alert_bot.http_json import get_json
from ma_alert_bot.models import Candle


OKX_CANDLES_PATH = "/api/v5/market/candles"
OKX_TICKER_PATH = "/api/v5/market/ticker"
OKX_MARK_PRICE_PATH = "/api/v5/public/mark-price"
OKX_OPEN_INTEREST_PATH = "/api/v5/public/open-interest"
OKX_FUNDING_RATE_PATH = "/api/v5/public/funding-rate"
OKX_SUCCESS_CODE = "0"
OKX_CANDLE_INTERVAL = "4H"
OKX_CANDLE_LIMIT = 300
OKX_CONFIRMED_CANDLE_VALUE = "1"
OKX_SWAP_INSTRUMENT_TYPE = "SWAP"
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

    def get_derivative_metrics(self, instrument_id: str) -> OkxDerivativeMetrics:
        ticker = self._get_first_data_object(
            path=OKX_TICKER_PATH,
            query_parameters={"instId": instrument_id},
        )
        if not instrument_id.endswith("-SWAP"):
            return OkxDerivativeMetrics(
                last_price=self._optional_float(ticker.get("last")),
                mark_price=None,
                open_interest_contracts=None,
                open_interest_currency=None,
                funding_rate=None,
                next_funding_rate=None,
                next_funding_timestamp_ms=None,
                twenty_four_hour_open_price=self._optional_float(ticker.get("open24h")),
                twenty_four_hour_high_price=self._optional_float(ticker.get("high24h")),
                twenty_four_hour_low_price=self._optional_float(ticker.get("low24h")),
                twenty_four_hour_volume_currency=self._optional_float(
                    ticker.get("volCcy24h")
                ),
            )

        mark_price = self._get_first_data_object(
            path=OKX_MARK_PRICE_PATH,
            query_parameters={
                "instType": OKX_SWAP_INSTRUMENT_TYPE,
                "instId": instrument_id,
            },
        )
        open_interest = self._get_first_data_object(
            path=OKX_OPEN_INTEREST_PATH,
            query_parameters={
                "instType": OKX_SWAP_INSTRUMENT_TYPE,
                "instId": instrument_id,
            },
        )
        funding_rate = self._get_first_data_object(
            path=OKX_FUNDING_RATE_PATH,
            query_parameters={"instId": instrument_id},
        )
        return OkxDerivativeMetrics(
            last_price=self._optional_float(ticker.get("last")),
            mark_price=self._optional_float(mark_price.get("markPx")),
            open_interest_contracts=self._optional_float(open_interest.get("oi")),
            open_interest_currency=self._optional_float(open_interest.get("oiCcy")),
            funding_rate=self._optional_float(funding_rate.get("fundingRate")),
            next_funding_rate=self._optional_float(funding_rate.get("nextFundingRate")),
            next_funding_timestamp_ms=self._optional_integer(
                funding_rate.get("nextFundingTime")
            ),
            twenty_four_hour_open_price=self._optional_float(ticker.get("open24h")),
            twenty_four_hour_high_price=self._optional_float(ticker.get("high24h")),
            twenty_four_hour_low_price=self._optional_float(ticker.get("low24h")),
            twenty_four_hour_volume_currency=self._optional_float(
                ticker.get("volCcy24h")
            ),
        )

    def _get_first_data_object(
        self,
        path: str,
        query_parameters: dict[str, str],
    ) -> dict[str, object]:
        response_payload = get_json(
            base_url=self._api_base_url,
            path=path,
            query_parameters=query_parameters,
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
        )
        self._raise_for_api_error(response_payload)
        response_data = response_payload.get("data")
        if not isinstance(response_data, list) or not response_data:
            raise ValueError(f"OKX returned no data for {path}")
        first_data_item = response_data[0]
        if not isinstance(first_data_item, dict):
            raise ValueError(f"Unexpected OKX response for {path}: {first_data_item!r}")
        return first_data_item

    @staticmethod
    def _optional_float(raw_value: object) -> float | None:
        if raw_value in (None, ""):
            return None
        return float(raw_value)

    @staticmethod
    def _optional_integer(raw_value: object) -> int | None:
        if raw_value in (None, ""):
            return None
        return int(str(raw_value))

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
