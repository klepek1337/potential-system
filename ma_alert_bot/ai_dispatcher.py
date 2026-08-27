import logging
import queue
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ma_alert_bot.ai_coordinator import AiReportCoordinator
from ma_alert_bot.models import Candle


LOGGER = logging.getLogger(__name__)
AI_REPORT_QUEUE_MAXIMUM_SIZE = 20
AI_REPORT_WORKER_NAME = "ai-report-worker"


class AiTaskType(StrEnum):
    DAILY_IF_DUE = "daily_if_due"
    MARKET_EVENT = "market_event"


@dataclass(frozen=True)
class AiReportTask:
    task_type: AiTaskType
    candles_by_instrument: dict[str, Sequence[Candle]] | None = None
    instrument_id: str | None = None
    candles: Sequence[Candle] | None = None
    market_events: list[str] | None = None


class AiReportDispatcher:
    def __init__(self, coordinator: AiReportCoordinator) -> None:
        self._coordinator = coordinator
        self._task_queue: queue.Queue[AiReportTask | None] = queue.Queue(
            maxsize=AI_REPORT_QUEUE_MAXIMUM_SIZE
        )
        self._daily_task_pending = False
        self._daily_task_lock = threading.Lock()
        self._worker_thread = threading.Thread(
            target=self._run_worker,
            name=AI_REPORT_WORKER_NAME,
            daemon=True,
        )
        self._worker_thread.start()

    def submit_daily_report_if_due(
        self,
        candles_by_instrument: dict[str, Sequence[Candle]],
    ) -> None:
        with self._daily_task_lock:
            if self._daily_task_pending:
                return
            self._daily_task_pending = True
        task_was_queued = self._submit_task(
            AiReportTask(
                task_type=AiTaskType.DAILY_IF_DUE,
                candles_by_instrument=dict(candles_by_instrument),
            )
        )
        if not task_was_queued:
            with self._daily_task_lock:
                self._daily_task_pending = False

    def submit_event_report(
        self,
        instrument_id: str,
        candles: Sequence[Candle],
        market_events: list[str],
    ) -> None:
        self._submit_task(
            AiReportTask(
                task_type=AiTaskType.MARKET_EVENT,
                instrument_id=instrument_id,
                candles=list(candles),
                market_events=list(market_events),
            )
        )

    def close(self) -> None:
        self._task_queue.join()
        self._task_queue.put(None)
        self._worker_thread.join()

    def _submit_task(self, task: AiReportTask) -> bool:
        try:
            self._task_queue.put_nowait(task)
            return True
        except queue.Full:
            LOGGER.error("AI report queue is full; dropping %s", task.task_type.value)
            return False

    def _run_worker(self) -> None:
        while True:
            task = self._task_queue.get()
            try:
                if task is None:
                    return
                self._execute_task(task)
            except Exception:
                LOGGER.exception("AI report task failed")
            finally:
                if task is not None and task.task_type is AiTaskType.DAILY_IF_DUE:
                    with self._daily_task_lock:
                        self._daily_task_pending = False
                self._task_queue.task_done()

    def _execute_task(self, task: AiReportTask) -> None:
        if task.task_type is AiTaskType.DAILY_IF_DUE:
            self._coordinator.send_daily_report_if_due(
                task.candles_by_instrument or {}
            )
            return
        if task.instrument_id is None or task.candles is None:
            raise ValueError("AI market-event task is incomplete")
        self._coordinator.send_event_report(
            instrument_id=task.instrument_id,
            candles=task.candles,
            market_events=task.market_events or [],
        )
