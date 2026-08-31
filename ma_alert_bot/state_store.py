import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ma_alert_bot.models import ApproachSide, MovingAverageTest, UnresolvedTest


class AlertStateStore:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = database_path
        self._create_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moving_average_tests (
                    instrument_id TEXT NOT NULL,
                    moving_average_period INTEGER NOT NULL,
                    candle_opening_timestamp_ms INTEGER NOT NULL,
                    approach_side TEXT NOT NULL,
                    moving_average_value_at_detection REAL NOT NULL,
                    price_at_detection REAL NOT NULL,
                    resolution TEXT,
                    PRIMARY KEY (
                        instrument_id,
                        moving_average_period,
                        candle_opening_timestamp_ms
                    )
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS position_stop_anchors (
                    instrument_id TEXT PRIMARY KEY,
                    stop_anchor REAL NOT NULL,
                    timeframe TEXT NOT NULL,
                    ema_period INTEGER NOT NULL,
                    score REAL NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profit_protection_state (
                    instrument_id TEXT PRIMARY KEY,
                    highest_notified_stage INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS minute_sma_tilt_state (
                    instrument_id TEXT PRIMARY KEY,
                    last_candle_timestamp_ms INTEGER NOT NULL,
                    last_alert_timestamp_ms INTEGER,
                    last_alert_direction TEXT,
                    last_alert_tilt_atr REAL
                )
                """
            )

    def get_minute_sma_tilt_state(
        self, instrument_id: str
    ) -> tuple[int, int | None, str | None, float | None] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT last_candle_timestamp_ms, last_alert_timestamp_ms,
                       last_alert_direction, last_alert_tilt_atr
                FROM minute_sma_tilt_state
                WHERE instrument_id = ?
                """,
                (instrument_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            int(row[0]),
            int(row[1]) if row[1] is not None else None,
            str(row[2]) if row[2] is not None else None,
            float(row[3]) if row[3] is not None else None,
        )

    def save_minute_sma_tilt_state(
        self,
        instrument_id: str,
        candle_timestamp_ms: int,
        alert_timestamp_ms: int | None,
        alert_direction: str | None,
        alert_tilt_atr: float | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO minute_sma_tilt_state (
                    instrument_id, last_candle_timestamp_ms, last_alert_timestamp_ms,
                    last_alert_direction, last_alert_tilt_atr
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    last_candle_timestamp_ms=excluded.last_candle_timestamp_ms,
                    last_alert_timestamp_ms=COALESCE(
                        excluded.last_alert_timestamp_ms,
                        minute_sma_tilt_state.last_alert_timestamp_ms
                    ),
                    last_alert_direction=COALESCE(
                        excluded.last_alert_direction,
                        minute_sma_tilt_state.last_alert_direction
                    ),
                    last_alert_tilt_atr=COALESCE(
                        excluded.last_alert_tilt_atr,
                        minute_sma_tilt_state.last_alert_tilt_atr
                    )
                """,
                (
                    instrument_id,
                    candle_timestamp_ms,
                    alert_timestamp_ms,
                    alert_direction,
                    alert_tilt_atr,
                ),
            )

    def get_stop_anchor(self, instrument_id: str) -> float | None:
        state = self.get_dominant_ema_state(instrument_id)
        return state[0] if state else None

    def get_dominant_ema_state(
        self, instrument_id: str
    ) -> tuple[float, str, int, float] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT stop_anchor, timeframe, ema_period, score
                FROM position_stop_anchors
                WHERE instrument_id = ?
                """,
                (instrument_id,),
            ).fetchone()
        if row is None:
            return None
        return float(row[0]), str(row[1]), int(row[2]), float(row[3])

    def save_stop_anchor(
        self, instrument_id: str, stop_anchor: float, timeframe: str, ema_period: int, score: float
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO position_stop_anchors (
                    instrument_id, stop_anchor, timeframe, ema_period, score
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    stop_anchor=excluded.stop_anchor,
                    timeframe=excluded.timeframe,
                    ema_period=excluded.ema_period,
                    score=excluded.score,
                    updated_at=unixepoch()
                """,
                (instrument_id, stop_anchor, timeframe, ema_period, score),
            )

    def get_profit_protection_stage(self, instrument_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT highest_notified_stage FROM profit_protection_state WHERE instrument_id = ?",
                (instrument_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def save_profit_protection_stage(self, instrument_id: str, stage: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO profit_protection_state (instrument_id, highest_notified_stage)
                VALUES (?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    highest_notified_stage = MAX(highest_notified_stage, excluded.highest_notified_stage)
                """,
                (instrument_id, stage),
            )

    def reset_position_risk_state(self, instrument_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM position_stop_anchors WHERE instrument_id = ?",
                (instrument_id.upper(),),
            )
            connection.execute(
                "DELETE FROM profit_protection_state WHERE instrument_id = ?",
                (instrument_id.upper(),),
            )

    def register_test_if_new(self, moving_average_test: MovingAverageTest) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO moving_average_tests (
                    instrument_id,
                    moving_average_period,
                    candle_opening_timestamp_ms,
                    approach_side,
                    moving_average_value_at_detection,
                    price_at_detection
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    moving_average_test.instrument_id,
                    moving_average_test.moving_average_period,
                    moving_average_test.candle_opening_timestamp_ms,
                    moving_average_test.approach_side.value,
                    moving_average_test.moving_average_value_at_detection,
                    moving_average_test.price_at_detection,
                ),
            )
            return cursor.rowcount == 1

    def get_unresolved_tests(self, instrument_id: str) -> list[UnresolvedTest]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    instrument_id,
                    moving_average_period,
                    candle_opening_timestamp_ms,
                    approach_side
                FROM moving_average_tests
                WHERE instrument_id = ? AND resolution IS NULL
                """,
                (instrument_id,),
            ).fetchall()

        return [
            UnresolvedTest(
                instrument_id=row[0],
                moving_average_period=row[1],
                candle_opening_timestamp_ms=row[2],
                approach_side=ApproachSide(row[3]),
            )
            for row in rows
        ]

    def mark_test_resolved(
        self,
        unresolved_test: UnresolvedTest,
        resolution: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE moving_average_tests
                SET resolution = ?
                WHERE instrument_id = ?
                    AND moving_average_period = ?
                    AND candle_opening_timestamp_ms = ?
                    AND resolution IS NULL
                """,
                (
                    resolution,
                    unresolved_test.instrument_id,
                    unresolved_test.moving_average_period,
                    unresolved_test.candle_opening_timestamp_ms,
                ),
            )
