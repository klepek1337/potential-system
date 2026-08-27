import base64
import hashlib
import hmac
from datetime import UTC, datetime

from ma_alert_bot.http_json import get_json
from ma_alert_bot.positions import PositionDirection, PositionSnapshot


OKX_POSITIONS_PATH = "/api/v5/account/positions"
OKX_SUCCESS_CODE = "0"
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_USER_AGENT = "okx-ma-telegram-alerts/0.2"
HTTP_GET_METHOD = "GET"


def _optional_float(raw_value: object) -> float | None:
    if raw_value in (None, ""):
        return None
    return float(raw_value)


class OkxReadOnlyAccountClient:
    """Authenticated OKX client deliberately limited to private GET requests."""

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
    ) -> None:
        self._api_base_url = api_base_url
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase

    def get_open_positions(self) -> list[PositionSnapshot]:
        timestamp = (
            datetime.now(tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        signature_payload = f"{timestamp}{HTTP_GET_METHOD}{OKX_POSITIONS_PATH}"
        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode("utf-8"),
                signature_payload.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        response_payload = get_json(
            base_url=self._api_base_url,
            path=OKX_POSITIONS_PATH,
            query_parameters={},
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
            user_agent=HTTP_USER_AGENT,
            additional_headers={
                "OK-ACCESS-KEY": self._api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self._api_passphrase,
            },
        )
        self._raise_for_api_error(response_payload)
        return [
            parsed_position
            for raw_position in response_payload.get("data", [])
            if (parsed_position := self._parse_position(raw_position)) is not None
        ]

    @staticmethod
    def _raise_for_api_error(response_payload: dict[str, object]) -> None:
        response_code = str(response_payload.get("code", ""))
        if response_code != OKX_SUCCESS_CODE:
            error_message = str(response_payload.get("msg", "Unknown OKX API error"))
            raise RuntimeError(f"OKX API error {response_code}: {error_message}")

    @staticmethod
    def _parse_position(raw_position: object) -> PositionSnapshot | None:
        if not isinstance(raw_position, dict):
            raise ValueError(f"Unexpected OKX position payload: {raw_position!r}")
        signed_position_size = float(raw_position.get("pos", "0") or "0")
        if signed_position_size == 0:
            return None

        position_side = str(raw_position.get("posSide", "net"))
        if position_side == PositionDirection.LONG.value:
            direction = PositionDirection.LONG
        elif position_side == PositionDirection.SHORT.value:
            direction = PositionDirection.SHORT
        else:
            direction = (
                PositionDirection.LONG
                if signed_position_size > 0
                else PositionDirection.SHORT
            )

        entry_price = _optional_float(raw_position.get("avgPx"))
        if entry_price is None or entry_price <= 0:
            raise ValueError("Open OKX position has no valid avgPx")
        return PositionSnapshot(
            instrument_id=str(raw_position["instId"]).upper(),
            direction=direction,
            entry_price=entry_price,
            position_size=abs(signed_position_size),
            leverage=_optional_float(raw_position.get("lever")),
            liquidation_price=_optional_float(raw_position.get("liqPx")),
            unrealized_profit=_optional_float(raw_position.get("upl")),
        )
