"""Jira QA Crew - Streamlit entry point.

This module is presentation only. Orchestration lives in
``jira_qa_crew.services.pipeline`` and provider logic in
``jira_qa_crew.jira``, so the UI can be replaced without touching either.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import streamlit as st

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:  # keeps `streamlit run app.py` working without an install
    sys.path.insert(0, str(SRC))

from jira_qa_crew.config import Settings  # noqa: E402
from jira_qa_crew.exceptions import ConfigurationError, TicketInputError  # noqa: E402
from jira_qa_crew.models import StageEvent  # noqa: E402
from jira_qa_crew.services.pipeline import QAPipeline, new_run_id  # noqa: E402
from jira_qa_crew.services.tickets import parse_ticket_input  # noqa: E402
from jira_qa_crew.ui import results as results_ui  # noqa: E402
from jira_qa_crew.ui.components import (  # noqa: E402
    inject_theme,
    render_config_panel,
    render_header,
    render_input_area,
    render_parse_feedback,
    render_stage_list,
)
from jira_qa_crew.ui.state import (  # noqa: E402
    clear_run,
    get_run,
    get_settings,
    init_state,
    set_run,
)


def _hydrate_secrets() -> None:
    """Copy ``st.secrets`` into the environment before settings are read.

    Streamlit Community Cloud has no ``.env``; secrets arrive through
    ``st.secrets``. Existing environment variables win, so a local ``.env``
    still overrides during development.
    """
    try:
        secrets = st.secrets
    except Exception:  # noqa: BLE001 - no secrets file is a normal local setup
        return
    try:
        items = dict(secrets).items()
    except Exception:  # noqa: BLE001
        return
    for key, value in items:
        if isinstance(value, (str, int, float, bool)) and not os.getenv(key):
            os.environ[key] = str(value)


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def main() -> None:
    st.set_page_config(
        page_title="Jira QA Crew",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _hydrate_secrets()
    init_state()
    inject_theme()

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        st.error(f"Configuration error: {exc}")
        st.stop()
        return

    _configure_logging(settings)
    render_header(settings)
    render_config_panel(settings)

    if st.sidebar.button("Reload configuration"):
        get_settings(reload=True)
        st.rerun()
    if st.sidebar.button("Clear results"):
        clear_run()
        st.rerun()

    inputs = render_input_area(settings)

    try:
        parsed = parse_ticket_input(
            inputs["tickets"] or "",
            key_pattern=settings.jira_key_pattern,
            max_tickets=settings.pipeline_max_tickets,
            max_chars=settings.pipeline_max_input_chars,
        )
    except TicketInputError as exc:
        st.error(str(exc))
        st.stop()
        return

    render_parse_feedback(parsed, settings)

    blocking = settings.blocking_problems()
    start = st.button(
        "Analyze & Generate QA Pack",
        type="primary",
        disabled=not parsed.has_valid or bool(blocking),
    )
    if not parsed.has_valid and (inputs["tickets"] or "").strip():
        st.error("No valid Jira ticket IDs were found in the input.")
    if blocking:
        st.info("Configuration must be completed before a run can start. See the sidebar.")

    if start:
        _execute(settings, parsed, inputs["mode"])

    run = get_run()
    if run is not None:
        st.divider()
        results_ui.render_run(run)


def _execute(settings: Settings, parsed, mode) -> None:
    """Run the pipeline synchronously while streaming genuine stage progress."""
    st.divider()
    st.subheader("Pipeline")

    total = len(parsed.valid)
    progress_bar = st.progress(0.0, text=f"Starting {total} ticket(s)")
    current_label = st.empty()
    stage_area = st.container()
    stage_slots = {key: stage_area.empty() for key in parsed.valid}
    stage_state: dict[str, dict[str, dict]] = {key: {} for key in parsed.valid}
    done = {"count": 0}

    def on_progress(ticket_key: str, event: StageEvent) -> None:
        stage_state.setdefault(ticket_key, {})[event.stage.value] = {
            "status": event.status.value,
            "message": event.message,
        }
        with stage_slots.get(ticket_key, st.empty()).container():
            st.markdown(f"**{ticket_key}**")
            render_stage_list(stage_state[ticket_key])
        current_label.caption(f"{ticket_key} — {event.stage.value}: {event.status.value}")
        finished = done["count"] + (1 if event.stage.value == "Artifacts" else 0)
        progress_bar.progress(
            min(1.0, (finished + 0.5) / max(total, 1)),
            text=f"{ticket_key}: {event.stage.value}",
        )

    pipeline = QAPipeline(settings, progress=on_progress)
    run_id = new_run_id()

    with st.spinner("Running the QA crew. This calls the LLM once per stage."):
        run = pipeline.run(
            parsed.valid,
            mode=mode,
            invalid_inputs=parsed.invalid,
            duplicates=parsed.duplicates,
            run_id=run_id,
        )

    progress_bar.progress(1.0, text="Finished")
    current_label.caption(
        f"{len(run.completed)} completed, {len(run.completed_with_warnings)} with "
        f"warnings, {len(run.failed)} failed"
    )
    set_run(run)


# Streamlit executes this file top to bottom on every rerun, so main() is
# called unconditionally rather than guarded by __name__.
main()
