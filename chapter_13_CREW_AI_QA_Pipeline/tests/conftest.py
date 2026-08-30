"""Shared fixtures.

Nothing in the default test suite touches a real Jira instance or a paid LLM.
Anything that would is marked ``@pytest.mark.integration`` and skipped unless
``RUN_INTEGRATION_TESTS=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from jira_qa_crew.config import Settings
from jira_qa_crew.models import (
    TEST_PLAN_SECTIONS,
    AcceptanceCriterion,
    AutomatedTestTrace,
    AutomationCandidate,
    AutomationReadiness,
    JiraIssue,
    JiraSource,
    PlaywrightBundle,
    PlaywrightFile,
    Priority,
    Provenance,
    Requirement,
    RequirementAnalysis,
    RunSummary,
    StageEvent,
    StageName,
    StageStatus,
    TestCase,
    TestCaseSuite,
    TestPlan,
    TestPlanSection,
    TestScenario,
    TestStep,
    TestType,
    TicketResult,
    TicketStatus,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    """A fully configured Settings that points at nothing real."""
    monkeypatch.setenv("JIRA_QA_CREW_SKIP_DOTENV", "1")  # ignore any local .env
    for key in list(os.environ):
        if key.startswith(("JIRA_", "LLM_", "PIPELINE_", "DEMO_", "APP_", "OUTPUT_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token-abcdef123456")
    monkeypatch.setenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-0123456789")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JIRA_MCP_URL", "https://mcp.example.com/mcp")
    return Settings.load(env_file=os.devnull)


@pytest.fixture
def rest_payload(fixtures_dir) -> dict:
    return json.loads((fixtures_dir / "VWO-48.json").read_text())


@pytest.fixture
def issue(settings, rest_payload) -> JiraIssue:
    from jira_qa_crew.jira.rest_provider import build_issue_from_rest

    return build_issue_from_rest(rest_payload, settings, JiraSource.REST)


@pytest.fixture
def analysis() -> RequirementAnalysis:
    return RequirementAnalysis(
        ticket_key="VWO-48",
        summary="Shopping cart total shows $0.00 after applying discount code",
        issue_type="Bug",
        status="To Do",
        priority="Medium",
        labels=["checkout"],
        components=["Shopping Cart"],
        description_summary="The cart total renders as $0.00 for carts of three or more items.",
        requirements=[
            Requirement(
                id="REQ-001",
                text="The cart total must equal subtotal minus 20% when SAVE20 is applied.",
                provenance=Provenance.EXPLICIT,
                source_quote="Expected Result: cart total shows the original subtotal minus 20%",
            ),
            Requirement(
                id="REQ-002",
                text="The displayed total must match the discountedTotal returned by the API.",
                provenance=Provenance.EXPLICIT,
                source_quote="The API response contains the correct discounted amount.",
            ),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                text="Applying SAVE20 to a cart with 3+ items shows subtotal minus 20%.",
                requirement_ids=["REQ-001"],
            ),
            AcceptanceCriterion(
                id="AC-002",
                text="The cart total is never $0.00 while the cart is non-empty.",
                requirement_ids=["REQ-002"],
            ),
        ],
        missing_information=["The production cart URL and the cart total test id are unknown."],
        source=JiraSource.REST,
    )


@pytest.fixture
def test_plan() -> TestPlan:
    return TestPlan(
        ticket_key="VWO-48",
        title="Test Plan — VWO-48 cart discount total",
        sections=[
            TestPlanSection(
                number=i,
                title=title,
                content=(
                    f"Content for {title}. This section is specific to the VWO-48 cart "
                    "discount defect and references REQ-001 and AC-001 where relevant."
                ),
            )
            for i, title in enumerate(TEST_PLAN_SECTIONS, start=1)
        ],
        scenarios=[
            TestScenario(
                id="SC-001",
                title="Discount applied to a three item cart",
                requirement_ids=["REQ-001"],
                acceptance_criteria_ids=["AC-001"],
                priority=Priority.P0,
            )
        ],
    )


@pytest.fixture
def test_cases() -> TestCaseSuite:
    return TestCaseSuite(
        ticket_key="VWO-48",
        test_cases=[
            TestCase(
                id="VWO-48-TC-001",
                ticket_key="VWO-48",
                title="Cart with three items shows a 20% discounted total",
                objective="Verify the discounted total for the failing boundary.",
                priority=Priority.P0,
                test_type=TestType.HAPPY_PATH,
                requirement_ids=["REQ-001"],
                acceptance_criteria_ids=["AC-001"],
                steps=[
                    TestStep(number=1, action="Seed a cart with three items of $30 each"),
                    TestStep(number=2, action="Apply SAVE20", expected="Total shows $72.00"),
                ],
                expected_result="The cart total is $72.00",
                automation_candidate=AutomationCandidate.YES,
                automation_rationale="Deterministic UI assertion against a seeded cart.",
                tags=["cart", "discount"],
            ),
            TestCase(
                id="VWO-48-TC-002",
                ticket_key="VWO-48",
                title="Cart total is never zero for a non-empty cart",
                priority=Priority.P1,
                test_type=TestType.NEGATIVE,
                requirement_ids=["REQ-002"],
                acceptance_criteria_ids=["AC-002"],
                steps=[TestStep(number=1, action="Apply SAVE20 to a five item cart")],
                expected_result="The total is greater than zero",
                automation_candidate=AutomationCandidate.NO,
                automation_rationale="Needs a production-like data set that is not available.",
            ),
        ],
    )


@pytest.fixture
def playwright_bundle() -> PlaywrightBundle:
    spec = """import { test, expect } from '@playwright/test';

// TODO: confirm the real test id with the frontend team.
const CART_TOTAL_TESTID = 'cart-total';

test.describe('VWO-48 cart discount', () => {
  test('VWO-48-TC-001 discounted total for a three item cart', async ({ page }) => {
    await test.step('open the cart', async () => {
      await page.goto('/cart');
    });
    await expect(page.getByTestId(CART_TOTAL_TESTID)).toHaveText('$72.00');
  });
});
"""
    return PlaywrightBundle(
        ticket_key="VWO-48",
        files=[PlaywrightFile(path="tests/vwo-48.spec.ts", content=spec, kind="spec")],
        traces=[
            AutomatedTestTrace(
                test_name="VWO-48-TC-001 discounted total for a three item cart",
                test_case_id="VWO-48-TC-001",
                ticket_key="VWO-48",
                requirement_ids=["REQ-001"],
                acceptance_criteria_ids=["AC-001"],
                spec_path="tests/vwo-48.spec.ts",
            )
        ],
        readiness=AutomationReadiness.NEEDS_CONFIGURATION,
        setup_notes="npm i -D @playwright/test && npx playwright test",
        missing_information=["Confirmed data-testid for the cart total element"],
    )


@pytest.fixture
def ticket_result(issue, analysis, test_plan, test_cases, playwright_bundle) -> TicketResult:
    from jira_qa_crew.services.traceability import build_coverage

    result = TicketResult(
        ticket_key="VWO-48",
        status=TicketStatus.COMPLETED_WITH_WARNINGS,
        source=JiraSource.REST,
        issue=issue,
        analysis=analysis,
        test_plan=test_plan,
        test_cases=test_cases,
        playwright=playwright_bundle,
        warnings=["[Coverage] Example warning"],
        stages=[
            StageEvent(stage=name, status=StageStatus.COMPLETED, message="ok")
            for name in StageName
        ],
    )
    result.coverage = build_coverage(analysis, test_cases, playwright_bundle)
    return result


@pytest.fixture
def run_summary(ticket_result) -> RunSummary:
    return RunSummary(
        run_id="RUN-20260829-120000",
        requested_keys=["VWO-48"],
        results=[ticket_result],
    )


def requires_integration() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS") == "1"


integration = pytest.mark.skipif(
    not requires_integration(),
    reason="set RUN_INTEGRATION_TESTS=1 to run tests that need real credentials",
)
