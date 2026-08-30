"""Progress reporting.

The pipeline emits real stage transitions through a callback so the Streamlit
UI can show genuine progress. There is deliberately no fake token streaming:
if a stage is slow, the UI says the stage is running, and nothing more.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from ..models import StageEvent, StageName, StageStatus

logger = logging.getLogger(__name__)

#: (ticket_key, StageEvent) -> None
ProgressCallback = Callable[[str, StageEvent], None]


class ProgressReporter:
    """Tracks stage state for one run and forwards it to an optional sink."""

    def __init__(self, callback: ProgressCallback | None = None):
        self._callback = callback

    def _emit(self, ticket_key: str, event: StageEvent) -> None:
        if self._callback is None:
            return
        try:
            self._callback(ticket_key, event)
        except Exception:  # noqa: BLE001 - a broken UI sink must not kill a run
            logger.debug("progress callback raised", exc_info=True)

    def start(self, ticket_key: str, event: StageEvent, message: str = "") -> StageEvent:
        event.status = StageStatus.RUNNING
        event.started_at = datetime.now()
        event.message = message
        self._emit(ticket_key, event)
        return event

    def finish(
        self,
        ticket_key: str,
        event: StageEvent,
        status: StageStatus = StageStatus.COMPLETED,
        message: str = "",
    ) -> StageEvent:
        event.status = status
        event.finished_at = datetime.now()
        if message:
            event.message = message
        self._emit(ticket_key, event)
        return event

    def fail(self, ticket_key: str, event: StageEvent, message: str) -> StageEvent:
        return self.finish(ticket_key, event, StageStatus.FAILED, message)


def new_stage_set() -> list[StageEvent]:
    """The six stages every ticket goes through, in display order."""
    return [StageEvent(stage=name) for name in StageName]
