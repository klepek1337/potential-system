from dataclasses import dataclass

from ma_alert_bot.http_json import get_json
from ma_alert_bot.models import Candle

OKX_CANDLES_PATH = "/api/v5/market/candles"
OKX_INSTRUMENTS_PATH = "/api/v5/public/instruments"
OKX_TICKERS_PATH = "/api/v5/market/tickers"
OKX_SUCCESS_CODE = "0"
OKX_CANDLE_INTERVAL = "4H"
OKX_CANDLE_LIMIT = 300
OKX_CONFIRMED_CANDLE_VALUE = "1"
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "okx-ma-telegram-alerts/0.1"


@dataclass(frozen=True)
class PerpetualInstrument:
    instrument_id: str
    listing_timestamp_ms: int


@dataclass(frozen=True)
class PerpetualTicker:
    instrument_id: str
    last_price: float
    best_bid_price: float
    best_ask_price: float
    base_volume_24h: float

    @property
    def quote_notional_24h(self) -> float:
        return self.last_price * self.base_volume_24h

    @property
    def spread_ratio(self) -> float:
        midpoint = (self.best_bid_price + self.best_ask_price) / 2.0
        if midpoint <= 0:
            return float("inf")
        return (self.best_ask_price - self.best_bid_price) / midpoint


class OkxMarketDataClient:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url

    def close(self) -> None:
        return None

    def get_four_hour_candles(self, instrument_id: str) -> list[Candle]:
        return self.get_candles(instrument_id, OKX_CANDLE_INTERVAL)

    def get_live_usdt_perpetuals(self) -> tuple[PerpetualInstrument, ...]:
        response_payload = get_json(
            base_url=self._api_base_url,
            path=OKX_INSTRUMENTS_PATH,
            query_parameters={"instType": "SWAP"},
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
        )
        self._raise_for_api_error(response_payload)
        instruments = []
        for raw_instrument in response_payload["data"]:
            instrument_id = str(raw_instrument.get("instId", ""))
            if (
                raw_instrument.get("state") != "live"
                or raw_instrument.get("settleCcy") != "USDT"
                or not instrument_id.endswith("-USDT-SWAP")
            ):
                continue
            listing_timestamp = str(raw_instrument.get("listTime", ""))
            if not listing_timestamp.isdigit():
                continue
            instruments.append(
                PerpetualInstrument(instrument_id, int(listing_timestamp))
            )
        return tuple(sorted(instruments, key=lambda item: item.instrument_id))

    def get_swap_tickers(self) -> dict[str, PerpetualTicker]:
        response_payload = get_json(
            base_url=self._api_base_url,
            path=OKX_TICKERS_PATH,
            query_parameters={"instType": "SWAP"},
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
        )
        self._raise_for_api_error(response_payload)
        tickers: dict[str, PerpetualTicker] = {}
        for raw_ticker in response_payload["data"]:
            instrument_id = str(raw_ticker.get("instId", ""))
            try:
                ticker = PerpetualTicker(
                    instrument_id=instrument_id,
                    last_price=float(raw_ticker["last"]),
                    best_bid_price=float(raw_ticker["bidPx"]),
                    best_ask_price=float(raw_ticker["askPx"]),
                    base_volume_24h=float(raw_ticker["volCcy24h"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            tickers[instrument_id] = ticker
        return tickers

    def get_candles(self, instrument_id: str, interval: str) -> list[Candle]:
        response_payload = get_json(
            base_url=self._api_base_url,
            path=OKX_CANDLES_PATH,
            query_parameters={
                "instId": instrument_id,
                "bar": interval,
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
