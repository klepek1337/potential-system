import json
from pathlib import Path

from ma_alert_bot.models import ManualPosition, PositionSide


class PositionStore:
    """User-managed position registry. It never talks to a trading API."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def list_positions(self) -> list[ManualPosition]:
        if not self._file_path.exists():
            return []
        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Positions file must contain a JSON array")
        return [self._deserialize(item) for item in payload]

    def get(self, instrument_id: str) -> ManualPosition | None:
        normalized_id = instrument_id.upper()
        return next(
            (p for p in self.list_positions() if p.instrument_id == normalized_id),
            None,
        )

    def set(self, position: ManualPosition) -> None:
        if position.position_value_usd is not None and position.position_value_usd <= 0:
            raise ValueError("Position value must be positive")
        positions = [
            item
            for item in self.list_positions()
            if item.instrument_id != position.instrument_id
        ]
        positions.append(position)
        positions.sort(key=lambda item: item.instrument_id)
        self._write(positions)

    def remove(self, instrument_id: str) -> bool:
        positions = self.list_positions()
        normalized_id = instrument_id.upper()
        remaining = [p for p in positions if p.instrument_id != normalized_id]
        if len(remaining) == len(positions):
            return False
        self._write(remaining)
        return True

    def _write(self, positions: list[ManualPosition]) -> None:
        payload = [
            {
                "instrument_id": p.instrument_id,
                "side": p.side.value,
                "entry_price": p.entry_price,
                "stop_price": p.stop_price,
                "position_value_usd": p.position_value_usd,
                "leverage": p.leverage,
            }
            for p in positions
        ]
        temporary_path = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self._file_path)

    @staticmethod
    def _deserialize(payload: object) -> ManualPosition:
        if not isinstance(payload, dict):
            raise ValueError("Each position must be a JSON object")
        instrument_id = str(payload["instrument_id"]).upper()
        side = PositionSide(str(payload["side"]).lower())
        entry_price = float(payload["entry_price"])
        stop_price = float(payload["stop_price"])
        position_value_usd = payload.get("position_value_usd")
        leverage = payload.get("leverage")
        if entry_price <= 0 or stop_price <= 0:
            raise ValueError("Entry and stop prices must be positive")
        if side is PositionSide.LONG and stop_price >= entry_price:
            raise ValueError("A long position stop must be below entry")
        if side is PositionSide.SHORT and stop_price <= entry_price:
            raise ValueError("A short position stop must be above entry")
        if position_value_usd is not None and float(position_value_usd) <= 0:
            raise ValueError("Position value must be positive")
        return ManualPosition(
            instrument_id=instrument_id,
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            position_value_usd=(
                float(position_value_usd) if position_value_usd is not None else None
            ),
            leverage=float(leverage) if leverage is not None else None,
        )
