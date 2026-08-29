"""Results rendering: one tab per ticket, six tabs inside each."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..models import AutomationCandidate, RunSummary, TicketResult, TicketStatus
from ..services import artifacts as artifacts_service
from .components import TICKET_BADGE, readiness_badge, source_badge
from .state import cached_zip


def render_run(run: RunSummary) -> None:
    _render_run_header(run)

    if not run.results:
        st.info("No tickets were processed.")
        return

    labels = [
        f"{TICKET_BADGE[r.status][1]} {r.ticket_key}" for r in run.results
    ]
    for tab, result in zip(st.tabs(labels), run.results, strict=True):
        with tab:
            _render_ticket(run, result)


# --------------------------------------------------------------------------
def _render_run_header(run: RunSummary) -> None:
    st.subheader("Run summary")
    cols = st.columns(5)
    cols[0].metric("Run ID", run.run_id.replace("RUN-", ""))
    cols[1].metric("Tickets", len(run.results))
    cols[2].metric("Completed", len(run.completed))
    cols[3].metric("With warnings", len(run.completed_with_warnings))
    cols[4].metric("Failed", len(run.failed))

    rows = [
        {
            "Ticket": r.ticket_key,
            "Status": TICKET_BADGE[r.status][0],
            "Source": r.source.value if r.source else "—",
            "Automation": r.playwright.readiness.value if r.playwright else "—",
            "Requirements": r.coverage.total_requirements if r.coverage else 0,
            "Test cases": r.coverage.total_test_cases if r.coverage else 0,
            "Req coverage %": r.coverage.requirement_coverage_pct if r.coverage else 0.0,
            "Duration (s)": r.duration_seconds or 0.0,
        }
        for r in run.results
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if not run.successful:
        st.error("No ticket completed. Nothing was generated for this run.")

    zip_bytes = cached_zip(f"{run.run_id}::all", lambda: artifacts_service.build_zip(run))
    st.download_button(
        "Download all artifacts (ZIP)",
        data=zip_bytes,
        file_name=f"{run.run_id}_qa_artifacts.zip",
        mime="application/zip",
        type="primary",
    )
    st.caption(f"Artifacts on disk: `{run.output_dir}`")


# --------------------------------------------------------------------------
def _render_ticket(run: RunSummary, result: TicketResult) -> None:
    label, icon = TICKET_BADGE[result.status]
    st.markdown(
        f"### {icon} {result.ticket_key} — {label}<br>"
        f"{source_badge(result)}{readiness_badge(result)}",
        unsafe_allow_html=True,
    )

    if result.status is TicketStatus.FAILED:
        st.error(result.error or "This ticket failed for an unknown reason.")

    if result.warnings:
        with st.expander(f"{len(result.warnings)} warning(s)", expanded=False):
            for warning in result.warnings:
                st.warning(warning)

    tabs = st.tabs(
        [
            "Requirements Analysis",
            "Test Plan",
            "Test Cases",
            "Playwright",
            "Traceability",
            "Run Details",
        ]
    )
    with tabs[0]:
        _render_requirements(result)
    with tabs[1]:
        _render_test_plan(result)
    with tabs[2]:
        _render_test_cases(result)
    with tabs[3]:
        _render_playwright(result)
    with tabs[4]:
        _render_traceability(result)
    with tabs[5]:
        _render_run_details(run, result)


def _render_requirements(result: TicketResult) -> None:
    if not result.analysis:
        st.info("No requirement analysis was produced for this ticket.")
        return
    analysis = result.analysis
    cols = st.columns(4)
    cols[0].metric("Requirements", len(analysis.requirements))
    cols[1].metric("Acceptance criteria", len(analysis.acceptance_criteria))
    cols[2].metric("Missing info items", len(analysis.missing_information))
    cols[3].metric("Open questions", len(analysis.open_questions))

    if analysis.missing_information:
        st.warning(
            "**Missing information** (nothing was invented to fill these):\n\n"
            + "\n".join(f"- {m}" for m in analysis.missing_information)
        )
    st.markdown(artifacts_service.render_requirements_md(analysis, result.issue))
    _download(
        "Download requirements_analysis.md",
        artifacts_service.render_requirements_md(analysis, result.issue),
        f"{result.ticket_key}_requirements_analysis.md",
        "text/markdown",
    )
    _download(
        "Download requirements_analysis.json",
        json.dumps(analysis.model_dump(mode="json"), indent=2),
        f"{result.ticket_key}_requirements_analysis.json",
        "application/json",
    )


def _render_test_plan(result: TicketResult) -> None:
    if not result.test_plan:
        st.info("No test plan was produced for this ticket.")
        return
    markdown = artifacts_service.render_test_plan_md(result.test_plan)
    st.markdown(markdown)
    _download(
        "Download test_plan.md", markdown, f"{result.ticket_key}_test_plan.md", "text/markdown"
    )


def _render_test_cases(result: TicketResult) -> None:
    suite = result.test_cases
    if not suite:
        st.info("No test cases were produced for this ticket.")
        return

    frame = pd.DataFrame(
        [
            {
                "ID": c.id,
                "Title": c.title,
                "Priority": c.priority.value,
                "Type": c.test_type.value,
                "Automation": c.automation_candidate.value,
                "Requirements": ", ".join(c.requirement_ids),
                "Acceptance criteria": ", ".join(c.acceptance_criteria_ids),
                "Tags": ", ".join(c.tags),
                "Steps": len(c.steps),
                "Expected result": c.expected_result,
            }
            for c in suite.test_cases
        ]
    )

    filters = st.columns(5)
    search = filters[0].text_input("Search", key=f"search_{result.ticket_key}")
    priority = filters[1].multiselect(
        "Priority", sorted(frame["Priority"].unique()), key=f"prio_{result.ticket_key}"
    )
    test_type = filters[2].multiselect(
        "Type", sorted(frame["Type"].unique()), key=f"type_{result.ticket_key}"
    )
    automation = filters[3].multiselect(
        "Automation", sorted(frame["Automation"].unique()), key=f"auto_{result.ticket_key}"
    )
    requirement_options = sorted(
        {r for c in suite.test_cases for r in (*c.requirement_ids, *c.acceptance_criteria_ids)}
    )
    requirement = filters[4].multiselect(
        "Requirement / AC", requirement_options, key=f"req_{result.ticket_key}"
    )

    view = frame
    if search:
        needle = search.lower()
        view = view[
            view.apply(lambda row: needle in " ".join(map(str, row.values)).lower(), axis=1)
        ]
    if priority:
        view = view[view["Priority"].isin(priority)]
    if test_type:
        view = view[view["Type"].isin(test_type)]
    if automation:
        view = view[view["Automation"].isin(automation)]
    if requirement:
        view = view[
            view.apply(
                lambda row: any(
                    r in f"{row['Requirements']}, {row['Acceptance criteria']}"
                    for r in requirement
                ),
                axis=1,
            )
        ]

    st.caption(f"Showing {len(view)} of {len(frame)} test cases")
    st.dataframe(view, width="stretch", hide_index=True)

    with st.expander("Full test case detail (Markdown)"):
        st.markdown(artifacts_service.render_test_cases_md(suite))

    _download(
        "Download test_cases.md",
        artifacts_service.render_test_cases_md(suite),
        f"{result.ticket_key}_test_cases.md",
        "text/markdown",
    )
    _download(
        "Download test_cases.csv",
        artifacts_service.render_test_cases_csv(suite),
        f"{result.ticket_key}_test_cases.csv",
        "text/csv",
    )


def _render_playwright(result: TicketResult) -> None:
    bundle = result.playwright
    if not bundle:
        st.info("No Playwright automation was produced for this ticket.")
        return

    if bundle.readiness.value == "READY":
        st.success("Automation readiness: READY — no placeholders remain.")
    else:
        st.warning(
            f"Automation readiness: {bundle.readiness.value} — this code compiles "
            "but is not execution-ready."
        )
    if bundle.missing_information:
        st.error(
            "**Required before this suite can run:**\n\n"
            + "\n".join(f"- {m}" for m in bundle.missing_information)
        )
    if bundle.assumptions:
        st.info("**Assumptions:**\n\n" + "\n".join(f"- {a}" for a in bundle.assumptions))
    if bundle.setup_notes:
        with st.expander("Setup notes", expanded=False):
            st.markdown(bundle.setup_notes)

    for file in bundle.files:
        st.markdown(f"**`{file.path}`**")
        st.code(file.content, language="typescript")
        st.download_button(
            f"Download {file.path.split('/')[-1]}",
            data=file.content,
            file_name=file.path.split("/")[-1],
            mime="text/plain",
            key=f"dl_{result.ticket_key}_{file.path}",
        )

    _download(
        "Download playwright_tests.md",
        artifacts_service.render_playwright_md(bundle),
        f"{result.ticket_key}_playwright_tests.md",
        "text/markdown",
    )


def _render_traceability(result: TicketResult) -> None:
    coverage = result.coverage
    if not coverage:
        st.info("No traceability matrix was produced for this ticket.")
        return

    cols = st.columns(4)
    cols[0].metric("Requirement coverage", f"{coverage.requirement_coverage_pct}%")
    cols[1].metric("Automated test cases", f"{coverage.automation_pct}%")
    cols[2].metric("Covered ACs", f"{coverage.covered_acceptance_criteria}/{coverage.total_acceptance_criteria}")
    cols[3].metric("Uncovered requirements", coverage.uncovered_requirements)

    frame = pd.DataFrame(
        [
            {
                "Requirement": row.requirement_id,
                "Acceptance criterion": row.acceptance_criterion_id or "—",
                "Test cases": ", ".join(row.test_case_ids) or "—",
                "Automated": ", ".join(row.automated_test_case_ids) or "—",
                "Coverage": row.coverage_status.value,
                "Reason": row.reason,
            }
            for row in coverage.rows
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)

    for label, values in (
        ("Requirements with no test case", coverage.orphan_requirement_ids),
        ("Acceptance criteria with no test case", coverage.orphan_acceptance_criteria_ids),
        ("Test cases that trace to nothing", coverage.orphan_test_case_ids),
        ("References to ids that do not exist", coverage.unknown_reference_ids),
    ):
        if values:
            st.warning(f"**{label}:** {', '.join(values)}")

    _download(
        "Download traceability_matrix.csv",
        artifacts_service.render_traceability_csv(coverage),
        f"{result.ticket_key}_traceability_matrix.csv",
        "text/csv",
    )


def _render_run_details(run: RunSummary, result: TicketResult) -> None:
    cols = st.columns(3)
    cols[0].metric("Source", result.source.value if result.source else "—")
    cols[1].metric("Duration", f"{result.duration_seconds or 0}s")
    cols[2].metric("Status", TICKET_BADGE[result.status][0])

    if result.issue and result.issue.url:
        st.markdown(f"[Open {result.ticket_key} in Jira]({result.issue.url})")

    st.markdown("**Stages**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Stage": s.stage.value,
                    "Status": s.status.value,
                    "Message": s.message,
                    "Started": s.started_at.strftime("%H:%M:%S") if s.started_at else "—",
                    "Duration (s)": s.duration_seconds if s.duration_seconds is not None else "—",
                }
                for s in result.stages
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    manifest = artifacts_service.build_ticket_manifest(result)
    with st.expander("manifest.json"):
        st.json(manifest)
    _download(
        "Download manifest.json",
        json.dumps(manifest, indent=2),
        f"{result.ticket_key}_manifest.json",
        "application/json",
    )

    if result.status is not TicketStatus.FAILED:
        zip_bytes = cached_zip(
            f"{run.run_id}::{result.ticket_key}",
            lambda: artifacts_service.build_zip(run, [result.ticket_key]),
        )
        st.download_button(
            f"Download {result.ticket_key} artifacts (ZIP)",
            data=zip_bytes,
            file_name=f"{run.run_id}_{result.ticket_key}.zip",
            mime="application/zip",
            key=f"zip_{result.ticket_key}",
        )

    if result.test_cases and any(
        c.automation_candidate is AutomationCandidate.NO for c in result.test_cases.test_cases
    ):
        manual = [
            c.id
            for c in result.test_cases.test_cases
            if c.automation_candidate is AutomationCandidate.NO
        ]
        st.caption(f"Manual-only test cases: {', '.join(manual)}")


def _download(label: str, data: str, filename: str, mime: str) -> None:
    st.download_button(label, data=data, file_name=filename, mime=mime, key=f"dl_{filename}")
