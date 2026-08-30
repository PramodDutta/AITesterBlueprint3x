"""Reusable Streamlit widgets: header, configuration panel, input, progress."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ..config import IntegrationMode, Settings
from ..models import StageName, StageStatus, TicketResult, TicketStatus

STATUS_ICON = {
    StageStatus.PENDING.value: "⚪",
    StageStatus.RUNNING.value: "🔵",
    StageStatus.COMPLETED.value: "🟢",
    StageStatus.WARNING.value: "🟡",
    StageStatus.FAILED.value: "🔴",
}

TICKET_BADGE = {
    TicketStatus.COMPLETED: ("Completed", "🟢"),
    TicketStatus.COMPLETED_WITH_WARNINGS: ("Completed with warnings", "🟡"),
    TicketStatus.FAILED: ("Failed", "🔴"),
    TicketStatus.RUNNING: ("Running", "🔵"),
    TicketStatus.PENDING: ("Pending", "⚪"),
}


def inject_theme() -> None:
    """Blue QA-automation theme, applied on top of the Streamlit config."""
    st.markdown(
        """
        <style>
        .qa-hero {
            background: linear-gradient(135deg, #0b3a75 0%, #1668c1 55%, #2f8fe0 100%);
            padding: 1.6rem 1.9rem; border-radius: 14px; color: #ffffff;
            margin-bottom: 1.2rem;
        }
        .qa-hero h1 { color:#fff; margin:0 0 .35rem 0; font-size:2.05rem; letter-spacing:-.5px; }
        .qa-hero p  { color:#dbeafe; margin:0; font-size:1.02rem; }
        .qa-badge {
            display:inline-block; padding:.16rem .6rem; border-radius:999px;
            font-size:.76rem; font-weight:600; letter-spacing:.3px;
            border:1px solid rgba(255,255,255,.35); margin-right:.4rem;
        }
        .qa-badge-mcp  { background:#0e7490; color:#fff; }
        .qa-badge-rest { background:#1d4ed8; color:#fff; }
        .qa-badge-demo { background:#b45309; color:#fff; }
        .qa-badge-ready{ background:#15803d; color:#fff; }
        .qa-badge-needs{ background:#b45309; color:#fff; }
        .qa-stage {
            border-left:3px solid #1668c1; padding:.28rem .7rem; margin:.18rem 0;
            background:rgba(22,104,193,.06); border-radius:0 6px 6px 0; font-size:.9rem;
        }
        div[data-testid="stMetricValue"] { font-size:1.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(settings: Settings) -> None:
    st.markdown(
        f"""
        <div class="qa-hero">
          <h1>{settings.app_name}</h1>
          <p>Generate test plans, test cases, traceability, and Playwright
             automation directly from Jira.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_config_panel(settings: Settings) -> None:
    """Redacted readiness only. No secret is ever displayed or collected here."""
    status = settings.status()

    st.sidebar.subheader("Configuration")
    for label, key in (
        ("LLM", "llm"),
        ("Jira REST", "jira_rest"),
        ("Jira MCP", "jira_mcp"),
    ):
        block = status[key]
        icon = "🟢" if block["ready"] else "🔴"
        with st.sidebar.expander(f"{icon} {label}", expanded=not block["ready"]):
            for name, value in block.items():
                if name == "ready":
                    continue
                st.caption(f"**{name}**: {value}")

    pipeline = status["pipeline"]
    st.sidebar.caption(
        f"Mode `{pipeline['mode']}` · max {pipeline['max_tickets']} tickets · "
        f"output `{pipeline['output_dir']}`"
    )
    if settings.demo_mode:
        st.sidebar.warning(
            "DEMO MODE is on. Tickets are read from local fixtures, not from Jira."
        )

    problems = settings.blocking_problems()
    if problems:
        st.sidebar.error("Not ready to run:\n\n" + "\n\n".join(f"- {p}" for p in problems))
    else:
        st.sidebar.success("Ready to run.")

    st.sidebar.caption(
        "Secrets come from environment variables or `.streamlit/secrets.toml`. "
        "They are never entered in the UI and never displayed."
    )


def render_input_area(settings: Settings) -> dict[str, Any]:
    """The ticket input, mode selector and advanced settings."""
    left, right = st.columns([3, 2], gap="large")

    with left:
        tickets = st.text_area(
            "Jira ticket IDs",
            key="ticket_input",
            height=132,
            placeholder="VWO-48\nVWO-49, VWO-50",
            help=(
                "Separate with commas, spaces, semicolons or new lines. "
                "Duplicates are removed and keys are upper-cased."
            ),
        )

    with right:
        mode_label = st.radio(
            "Jira integration mode",
            options=["Auto (MCP → REST)", "MCP only", "REST only"],
            index={
                IntegrationMode.AUTO: 0,
                IntegrationMode.MCP: 1,
                IntegrationMode.REST: 2,
            }[settings.jira_integration_mode],
            help="Auto tries MCP first and falls back to the REST API.",
        )
        mode = {
            "Auto (MCP → REST)": IntegrationMode.AUTO,
            "MCP only": IntegrationMode.MCP,
            "REST only": IntegrationMode.REST,
        }[mode_label]

    with st.expander("Advanced settings"):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.caption(f"Model: `{settings.llm_model}`")
            st.caption(f"Temperature: `{settings.llm_temperature}`")
        with col_b:
            st.caption(f"Max tickets: `{settings.pipeline_max_tickets}`")
            st.caption("Retries per stage: `1 repair attempt`")
        with col_c:
            st.caption(f"Ticket timeout: `{settings.pipeline_ticket_timeout_seconds}s`")
            st.caption(f"Output dir: `{settings.output_dir}`")
        st.caption(
            "These come from the environment. Change them in `.env` or "
            "`.streamlit/secrets.toml` and restart."
        )

    return {"tickets": tickets, "mode": mode}


def render_parse_feedback(parsed: Any, settings: Settings) -> None:
    if parsed.duplicates:
        st.info(f"Removed {len(parsed.duplicates)} duplicate(s): {', '.join(parsed.duplicates)}")
    if parsed.invalid:
        st.warning(
            f"Ignored {len(parsed.invalid)} entry that does not look like a Jira key: "
            + ", ".join(parsed.invalid)
        )
    if parsed.dropped_over_limit:
        st.warning(
            f"Only the first {settings.pipeline_max_tickets} tickets are processed. "
            f"Dropped: {', '.join(parsed.dropped_over_limit)}"
        )


def source_badge(result: TicketResult) -> str:
    if not result.source:
        return ""
    css = {
        "MCP": "qa-badge-mcp",
        "REST": "qa-badge-rest",
        "DEMO_FIXTURE": "qa-badge-demo",
    }.get(result.source.value, "qa-badge-rest")
    return f'<span class="qa-badge {css}">Source: {result.source.value}</span>'


def readiness_badge(result: TicketResult) -> str:
    if not result.playwright:
        return ""
    value = result.playwright.readiness.value
    css = "qa-badge-ready" if value == "READY" else "qa-badge-needs"
    return f'<span class="qa-badge {css}">Automation: {value}</span>'


def render_stage_list(stages: dict[str, dict[str, Any]]) -> None:
    """Render the visible agent stages for one ticket during a run."""
    for stage in StageName:
        info = stages.get(stage.value, {})
        status = info.get("status", StageStatus.PENDING.value)
        message = info.get("message", "")
        icon = STATUS_ICON.get(status, "⚪")
        detail = f" — {message}" if message else ""
        st.markdown(
            f'<div class="qa-stage">{icon} <strong>{stage.value}</strong>{detail}</div>',
            unsafe_allow_html=True,
        )
