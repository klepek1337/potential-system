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
                CREATE TABLE IF NOT EXISTS daily_decision_reports (
                    instrument_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    PRIMARY KEY (instrument_id, local_date)
                )
                """
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

    def was_daily_report_sent(self, instrument_id: str, local_date: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM daily_decision_reports
                WHERE instrument_id = ? AND local_date = ?
                """,
                (instrument_id, local_date),
            ).fetchone()
        return row is not None

    def mark_daily_report_sent(self, instrument_id: str, local_date: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_decision_reports (instrument_id, local_date)
                VALUES (?, ?)
                """,
                (instrument_id, local_date),
            )
