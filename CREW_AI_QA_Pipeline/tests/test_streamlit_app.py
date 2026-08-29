"""Streamlit surface tests via streamlit.testing.v1.AppTest.

These render the real app. No Jira call and no LLM call happens, because the
button is never pressed and configuration is deliberately incomplete or the
pipeline is stubbed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JIRA_QA_CREW_SKIP_DOTENV", "1")  # ignore any local .env
    for key in list(os.environ):
        if key.startswith(("JIRA_", "LLM_", "PIPELINE_", "DEMO_", "APP_", "OUTPUT_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("APP_NAME", "Jira QA Crew")


def _run(**env):
    os.environ["JIRA_QA_CREW_SKIP_DOTENV"] = "1"
    for key, value in env.items():
        os.environ[key] = value
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    return app


def test_initial_render_has_no_exception():
    app = _run()
    assert not app.exception
    assert any("Jira QA Crew" in str(m.value) for m in app.markdown)


def test_the_run_button_is_disabled_until_configuration_is_complete():
    app = _run()
    button = next(b for b in app.button if "Analyze" in b.label)
    assert button.disabled


def test_missing_configuration_is_explained_rather_than_hidden():
    app = _run()
    errors = " ".join(str(e.value) for e in app.sidebar.error)
    assert "LLM is not configured" in errors


def test_configured_app_reports_ready():
    app = _run(
        LLM_MODEL="deepseek/deepseek-v4-flash",
        LLM_API_KEY="sk-test-0123456789",
        JIRA_URL="https://example.atlassian.net",
        JIRA_EMAIL="qa@example.com",
        JIRA_API_TOKEN="token-0123456789",
    )
    assert not app.exception
    assert any("Ready to run" in str(s.value) for s in app.sidebar.success)


def test_invalid_ticket_input_is_rejected_before_any_run():
    app = _run(
        LLM_MODEL="deepseek/deepseek-v4-flash",
        LLM_API_KEY="sk-test-0123456789",
        JIRA_URL="https://example.atlassian.net",
        JIRA_EMAIL="qa@example.com",
        JIRA_API_TOKEN="token-0123456789",
    )
    app.text_area[0].set_value("not-a-ticket").run()

    assert not app.exception
    assert any("No valid Jira ticket IDs" in str(e.value) for e in app.error)
    assert next(b for b in app.button if "Analyze" in b.label).disabled


def test_duplicate_and_over_limit_input_is_reported():
    app = _run(
        LLM_MODEL="deepseek/deepseek-v4-flash",
        LLM_API_KEY="sk-test-0123456789",
        JIRA_URL="https://example.atlassian.net",
        JIRA_EMAIL="qa@example.com",
        JIRA_API_TOKEN="token-0123456789",
        PIPELINE_MAX_TICKETS="1",
    )
    app.text_area[0].set_value("VWO-48, VWO-48, VWO-49").run()

    infos = " ".join(str(i.value) for i in app.info)
    warnings = " ".join(str(w.value) for w in app.warning)
    assert "duplicate" in infos.lower()
    assert "VWO-49" in warnings


def test_secrets_are_never_rendered_in_the_ui():
    token = "super-secret-token-value"
    app = _run(
        LLM_MODEL="deepseek/deepseek-v4-flash",
        LLM_API_KEY=token,
        JIRA_URL="https://example.atlassian.net",
        JIRA_EMAIL="qa@example.com",
        JIRA_API_TOKEN=token,
    )
    rendered = " ".join(
        str(getattr(element, "value", "")) for element in (*app.markdown, *app.caption, *app.info)
    )
    assert token not in rendered


def test_results_render_from_a_fixture_run(run_summary):
    """Render the whole results area from a prepared run, with no pipeline call."""
    app = _run(
        LLM_MODEL="deepseek/deepseek-v4-flash",
        LLM_API_KEY="sk-test-0123456789",
        JIRA_URL="https://example.atlassian.net",
        JIRA_EMAIL="qa@example.com",
        JIRA_API_TOKEN="token-0123456789",
    )
    app.session_state["qa_run_summary"] = run_summary
    app.run()

    assert not app.exception

    labels = [b.label for b in app.button] + [
        getattr(d, "label", "") for d in app.get("download_button")
    ]
    assert any("Download all artifacts" in label for label in labels)

    metric_labels = [m.label for m in app.get("metric")]
    assert "Run ID" in metric_labels
    assert "Completed" in metric_labels

    tab_labels = [t.label for t in app.get("tab")]
    assert any("VWO-48" in label for label in tab_labels)
    assert "Requirements Analysis" in tab_labels
    assert "Playwright" in tab_labels
    assert "Traceability" in tab_labels


def test_a_failed_run_says_nothing_was_generated(run_summary):
    from jira_qa_crew.models import RunSummary, TicketResult, TicketStatus

    failed = RunSummary(
        run_id="RUN-20260829-130000",
        requested_keys=["VWO-99"],
        results=[TicketResult(ticket_key="VWO-99", status=TicketStatus.FAILED, error="jira 401")],
    )
    app = _run(
        LLM_MODEL="deepseek/deepseek-v4-flash",
        LLM_API_KEY="sk-test-0123456789",
        JIRA_URL="https://example.atlassian.net",
        JIRA_EMAIL="qa@example.com",
        JIRA_API_TOKEN="token-0123456789",
    )
    app.session_state["qa_run_summary"] = failed
    app.run()

    assert not app.exception
    errors = " ".join(str(e.value) for e in app.error)
    assert "No ticket completed" in errors
    assert "jira 401" in errors
