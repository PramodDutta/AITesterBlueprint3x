"""Renderers, artifact paths, manifests, ZIP generation and secret redaction."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from jira_qa_crew.models import RunSummary, TicketResult, TicketStatus
from jira_qa_crew.services import artifacts as art


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def test_requirements_markdown_has_structure_and_provenance(analysis, issue):
    md = art.render_requirements_md(analysis, issue)
    assert md.startswith("# Requirements Analysis — VWO-48")
    assert "## Requirements" in md
    assert "## Acceptance Criteria" in md
    assert "## Missing Information" in md
    assert "REQ-001" in md and "AC-001" in md
    assert "EXPLICIT" in md


def test_requirements_markdown_says_so_when_nothing_was_invented(analysis):
    empty = analysis.model_copy(update={"acceptance_criteria": []})
    md = art.render_requirements_md(empty)
    assert "None were invented" in md


def test_markdown_table_cells_cannot_break_the_table(analysis):
    dirty = analysis.model_copy(
        update={
            "requirements": [
                analysis.requirements[0].model_copy(
                    update={"text": "a | b\nnew line"}
                )
            ]
        }
    )
    md = art.render_requirements_md(dirty)
    assert "a \\| b new line" in md


def test_test_plan_markdown_numbers_all_twelve_sections(test_plan):
    md = art.render_test_plan_md(test_plan)
    for number in range(1, 13):
        assert f"## {number}." in md


def test_test_cases_markdown_includes_steps_and_automation(test_cases):
    md = art.render_test_cases_md(test_cases)
    assert "## VWO-48-TC-001" in md
    assert "**Automation candidate:** Yes" in md
    assert "| 1 | Seed a cart" in md


def test_playwright_markdown_is_honest_about_readiness(playwright_bundle):
    md = art.render_playwright_md(playwright_bundle)
    assert "NEEDS_CONFIGURATION" in md
    assert "not** execution-ready" in md or "not execution-ready" in md
    assert "```typescript" in md
    assert "## Missing Information" in md


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def test_test_cases_csv_is_parseable_and_complete(test_cases):
    rows = list(csv.DictReader(io.StringIO(art.render_test_cases_csv(test_cases))))
    assert len(rows) == 2
    assert rows[0]["test_case_id"] == "VWO-48-TC-001"
    assert rows[0]["automation_candidate"] == "Yes"
    assert "1. Seed a cart" in rows[0]["steps"]


def test_traceability_csv_has_one_row_per_matrix_row(ticket_result):
    rows = list(csv.DictReader(io.StringIO(art.render_traceability_csv(ticket_result.coverage))))
    assert len(rows) == len(ticket_result.coverage.rows)
    assert {"requirement_id", "coverage_status", "reason"} <= set(rows[0])


# --------------------------------------------------------------------------
# Manifests
# --------------------------------------------------------------------------
def test_ticket_manifest_reports_counts_and_readiness(ticket_result):
    manifest = art.build_ticket_manifest(ticket_result)
    assert manifest["ticket_key"] == "VWO-48"
    assert manifest["source"] == "REST"
    assert manifest["counts"]["requirements"] == 2
    assert manifest["counts"]["test_cases"] == 2
    assert manifest["automation_readiness"] == "NEEDS_CONFIGURATION"
    assert manifest["coverage"]["requirement_coverage_pct"] >= 0


def test_run_manifest_is_json_serialisable(run_summary):
    payload = json.dumps(art.build_run_manifest(run_summary))
    assert "RUN-20260829-120000" in payload


# --------------------------------------------------------------------------
# Writing to disk
# --------------------------------------------------------------------------
def test_writes_the_documented_artifact_layout(ticket_result, tmp_path):
    run_dir = tmp_path / "RUN-1"
    art.write_ticket_artifacts(ticket_result, run_dir)

    ticket_dir = run_dir / "VWO-48"
    for name in (
        "requirements_analysis.md",
        "requirements_analysis.json",
        "test_plan.md",
        "test_cases.md",
        "test_cases.csv",
        "traceability_matrix.csv",
        "playwright_tests.md",
        "manifest.json",
    ):
        assert (ticket_dir / name).exists(), name
    assert (ticket_dir / "playwright" / "tests" / "vwo-48.spec.ts").exists()
    assert (ticket_dir / "playwright" / "pages").is_dir()
    assert (ticket_dir / "playwright" / "fixtures").is_dir()


def test_a_hostile_ticket_key_cannot_escape_the_run_directory(ticket_result, tmp_path):
    run_dir = tmp_path / "RUN-1"
    hostile = ticket_result.model_copy(update={"ticket_key": "../../escaped"})
    art.write_ticket_artifacts(hostile, run_dir)

    assert not (tmp_path.parent / "escaped").exists()
    written = [p for p in run_dir.rglob("*") if p.is_file()]
    assert written, "artifacts should still be written, just sandboxed"
    for path in written:
        assert run_dir.resolve() in path.resolve().parents


def test_run_artifacts_include_summary_and_manifest(run_summary, tmp_path):
    run_dir = art.write_run_artifacts(run_summary, tmp_path)
    assert (run_dir / "run_summary.md").exists()
    assert (run_dir / "manifest.json").exists()
    assert "Run Summary" in (run_dir / "run_summary.md").read_text()


# --------------------------------------------------------------------------
# ZIP
# --------------------------------------------------------------------------
def test_zip_contains_every_artifact_for_the_run(run_summary):
    with zipfile.ZipFile(io.BytesIO(art.build_zip(run_summary))) as archive:
        names = archive.namelist()
        assert "RUN-20260829-120000/run_summary.md" in names
        assert "RUN-20260829-120000/manifest.json" in names
        assert "RUN-20260829-120000/VWO-48/test_cases.csv" in names
        assert "RUN-20260829-120000/VWO-48/playwright/tests/vwo-48.spec.ts" in names
        assert archive.testzip() is None


def test_zip_can_be_scoped_to_one_ticket(run_summary):
    with zipfile.ZipFile(io.BytesIO(art.build_zip(run_summary, ["VWO-48"]))) as archive:
        assert any("VWO-48" in n for n in archive.namelist())
    with zipfile.ZipFile(io.BytesIO(art.build_zip(run_summary, ["NOPE-1"]))) as archive:
        assert not any("VWO-48" in n for n in archive.namelist())


def test_a_failed_ticket_with_nothing_generated_is_skipped_in_the_zip(run_summary):
    failed = TicketResult(ticket_key="VWO-99", status=TicketStatus.FAILED, error="boom")
    run = RunSummary(run_id="RUN-2", results=[failed])
    with zipfile.ZipFile(io.BytesIO(art.build_zip(run))) as archive:
        assert not any("VWO-99/" in n for n in archive.namelist())
        assert "RUN-2/run_summary.md" in archive.namelist()


def test_run_summary_markdown_lists_failures_and_warnings(ticket_result):
    failed = TicketResult(ticket_key="VWO-99", status=TicketStatus.FAILED, error="jira 401")
    run = RunSummary(run_id="RUN-3", requested_keys=["VWO-48", "VWO-99"],
                     results=[ticket_result, failed])
    md = art.render_run_summary_md(run)
    assert "## Failures" in md and "jira 401" in md
    assert "## Warnings" in md
    assert "VWO-48" in md and "VWO-99" in md


# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------
def test_settings_redacts_every_known_secret(settings):
    message = (
        f"call failed with token {settings.jira_api_token} and key {settings.llm_api_key}"
    )
    cleaned = settings.redact(message)
    assert settings.jira_api_token not in cleaned
    assert settings.llm_api_key not in cleaned
    assert cleaned.count("***REDACTED***") == 2


def test_redaction_strips_authorization_headers(settings):
    cleaned = settings.redact("Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==")
    assert "dXNlcjpwYXNzd29yZDEyMw==" not in cleaned
    assert "Basic ***REDACTED***" in cleaned


def test_status_never_exposes_a_secret(settings):
    blob = json.dumps(settings.status(), ensure_ascii=False)
    assert settings.jira_api_token not in blob
    assert settings.llm_api_key not in blob
    assert "set (…" in blob  # only the masked tail is ever shown


def test_redaction_handles_empty_input(settings):
    assert settings.redact("") == ""


def test_artifacts_directory_paths_are_relative(ticket_result, tmp_path):
    written = art.write_ticket_artifacts(ticket_result, tmp_path / "RUN-1")
    for value in written.values():
        assert not Path(value).is_absolute()
