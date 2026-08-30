"""Opt-in tests that use real credentials.

These are skipped unless ``RUN_INTEGRATION_TESTS=1``. They cost money (LLM)
and need network access (Jira), so CI never runs them.

    RUN_INTEGRATION_TESTS=1 LIVE_JIRA_KEY=VWO-48 pytest tests/test_integration_live.py -v
"""

from __future__ import annotations

import os

import pytest

from jira_qa_crew.config import Settings
from jira_qa_crew.jira.gateway import JiraGateway
from jira_qa_crew.services.pipeline import QAPipeline

pytestmark = pytest.mark.integration

RUN_LIVE = os.getenv("RUN_INTEGRATION_TESTS") == "1"
skip_unless_live = pytest.mark.skipif(
    not RUN_LIVE, reason="set RUN_INTEGRATION_TESTS=1 to run live tests"
)


@pytest.fixture
def live_settings() -> Settings:
    settings = Settings.load()
    if not settings.rest_ready() and not settings.mcp_ready():
        pytest.skip("no live Jira configuration available")
    return settings


@skip_unless_live
def test_provider_health_against_the_real_endpoints(live_settings):
    health = JiraGateway(live_settings).health()
    assert health, "the gateway should report on at least one provider"
    for name, (ok, detail) in health.items():
        print(f"{name}: {'OK' if ok else 'FAILED'} - {detail}")
    assert any(ok for ok, _ in health.values()), "no provider is reachable"


@skip_unless_live
def test_fetch_a_real_ticket(live_settings):
    key = os.getenv("LIVE_JIRA_KEY", "VWO-48")
    issue = JiraGateway(live_settings).fetch_issue(key)
    assert issue.key.upper() == key.upper()
    assert issue.summary
    print(f"fetched {issue.key} via {issue.source.value}")


@skip_unless_live
def test_full_pipeline_against_a_real_ticket_and_a_real_llm(live_settings):
    if not live_settings.llm_ready():
        pytest.skip("no LLM configured")
    key = os.getenv("LIVE_JIRA_KEY", "VWO-48")

    run = QAPipeline(live_settings).run([key])

    assert run.successful, run.results[0].error
    result = run.results[0]
    assert result.analysis and result.analysis.requirements
    assert result.test_plan and len(result.test_plan.sections) == 12
    assert result.test_cases and result.test_cases.test_cases
    assert result.playwright and result.playwright.files
    assert result.coverage is not None
