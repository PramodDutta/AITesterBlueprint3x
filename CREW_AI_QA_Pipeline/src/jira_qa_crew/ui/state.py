"""Streamlit session state.

Results are stored once, after the run completes, so ordinary Streamlit
reruns (a filter change, a tab click, a download) never re-trigger the
pipeline.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ..config import Settings
from ..models import RunSummary, StageEvent

RUN_KEY = "qa_run_summary"
RUNNING_KEY = "qa_run_in_progress"
PROGRESS_KEY = "qa_progress"
SETTINGS_KEY = "qa_settings"
ZIP_CACHE_KEY = "qa_zip_cache"


def init_state() -> None:
    st.session_state.setdefault(RUN_KEY, None)
    st.session_state.setdefault(RUNNING_KEY, False)
    st.session_state.setdefault(PROGRESS_KEY, {})
    st.session_state.setdefault(ZIP_CACHE_KEY, {})


def get_settings(reload: bool = False) -> Settings:
    """Load settings once per session unless explicitly reloaded."""
    if reload or SETTINGS_KEY not in st.session_state:
        st.session_state[SETTINGS_KEY] = Settings.load()
    return st.session_state[SETTINGS_KEY]


def set_run(run: RunSummary) -> None:
    st.session_state[RUN_KEY] = run
    st.session_state[ZIP_CACHE_KEY] = {}  # artifacts changed, drop stale ZIPs


def get_run() -> RunSummary | None:
    return st.session_state.get(RUN_KEY)


def clear_run() -> None:
    st.session_state[RUN_KEY] = None
    st.session_state[PROGRESS_KEY] = {}
    st.session_state[ZIP_CACHE_KEY] = {}


def record_progress(ticket_key: str, event: StageEvent) -> None:
    progress: dict[str, dict[str, Any]] = st.session_state.setdefault(PROGRESS_KEY, {})
    progress.setdefault(ticket_key, {})[event.stage.value] = {
        "status": event.status.value,
        "message": event.message,
        "started_at": event.started_at,
        "finished_at": event.finished_at,
    }


def cached_zip(cache_key: str, builder: Any) -> bytes:
    """Build a ZIP once per session and reuse it while the run is unchanged."""
    cache: dict[str, bytes] = st.session_state.setdefault(ZIP_CACHE_KEY, {})
    if cache_key not in cache:
        cache[cache_key] = builder()
    return cache[cache_key]
