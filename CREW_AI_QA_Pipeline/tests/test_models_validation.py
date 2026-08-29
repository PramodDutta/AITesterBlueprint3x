"""Pydantic contracts and the deterministic post-stage validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jira_qa_crew.models import (
    TEST_PLAN_SECTIONS,
    AcceptanceCriterion,
    AutomationCandidate,
    AutomationReadiness,
    PlaywrightBundle,
    PlaywrightFile,
    Requirement,
    TestCase,
    TestCaseSuite,
    TestPlan,
    TestPlanSection,
    TestScenario,
    TestStep,
)
from jira_qa_crew.services.validation import (
    validate_analysis,
    validate_playwright,
    validate_test_cases,
    validate_test_plan,
)


# --------------------------------------------------------------------------
# Schema level
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad_id", ["R-1", "REQ1", "REQ-1", "req-abc", ""])
def test_requirement_ids_must_match_the_convention(bad_id):
    with pytest.raises(ValidationError):
        Requirement(id=bad_id, text="x")


def test_requirement_id_is_upper_cased():
    assert Requirement(id="req-001", text="x").id == "REQ-001"


@pytest.mark.parametrize("bad_id", ["TC-001", "VWO-48-001", "VWO48-TC-001"])
def test_test_case_ids_must_match_the_convention(bad_id):
    with pytest.raises(ValidationError):
        TestCase(id=bad_id, ticket_key="VWO-48", title="t",
                 steps=[TestStep(number=1, action="a")], requirement_ids=["REQ-001"])


def test_a_test_case_needs_steps_and_a_trace():
    with pytest.raises(ValidationError, match="no steps"):
        TestCase(id="VWO-48-TC-001", ticket_key="VWO-48", title="t",
                 requirement_ids=["REQ-001"], steps=[])
    with pytest.raises(ValidationError, match="trace to at least one"):
        TestCase(id="VWO-48-TC-001", ticket_key="VWO-48", title="t",
                 steps=[TestStep(number=1, action="a")])


def test_a_scenario_must_reference_something():
    with pytest.raises(ValidationError, match="at least one REQ"):
        TestScenario(id="SC-1", title="t")


def test_duplicate_test_case_ids_are_rejected_by_the_schema():
    case = TestCase(id="VWO-48-TC-001", ticket_key="VWO-48", title="t",
                    requirement_ids=["REQ-001"], steps=[TestStep(number=1, action="a")])
    with pytest.raises(ValidationError, match="Duplicate test case ids"):
        TestCaseSuite(ticket_key="VWO-48", test_cases=[case, case.model_copy()])


def test_an_empty_suite_is_rejected():
    with pytest.raises(ValidationError, match="at least one test case"):
        TestCaseSuite(ticket_key="VWO-48", test_cases=[])


def test_the_plan_must_have_exactly_twelve_ordered_sections():
    sections = [TestPlanSection(number=i, title=t, content="x" * 60)
                for i, t in enumerate(TEST_PLAN_SECTIONS, start=1)]
    assert len(TestPlan(ticket_key="V-1", title="t", sections=sections).sections) == 12

    with pytest.raises(ValidationError, match="exactly 12 sections"):
        TestPlan(ticket_key="V-1", title="t", sections=sections[:11])


def test_plan_sections_cannot_repeat_a_number():
    sections = [TestPlanSection(number=1, title=t, content="x" * 60)
                for t in TEST_PLAN_SECTIONS]
    with pytest.raises(ValidationError, match="1..12 exactly once"):
        TestPlan(ticket_key="V-1", title="t", sections=sections)


@pytest.mark.parametrize("bad_path", ["../escape.ts", "tests/../../x.ts", "notes.md", ""])
def test_playwright_file_paths_are_sandboxed(bad_path):
    with pytest.raises(ValidationError):
        PlaywrightFile(path=bad_path, content="x")


def test_ready_is_impossible_while_information_is_missing():
    with pytest.raises(ValidationError, match="READY is not allowed"):
        PlaywrightBundle(
            ticket_key="VWO-48",
            files=[PlaywrightFile(path="tests/a.spec.ts", content="x")],
            readiness=AutomationReadiness.READY,
            missing_information=["a selector"],
        )


# --------------------------------------------------------------------------
# Deterministic validation
# --------------------------------------------------------------------------
def test_analysis_for_the_wrong_ticket_is_an_error(analysis):
    assert validate_analysis(analysis, "VWO-48").ok
    assert not validate_analysis(analysis, "VWO-99").ok


def test_analysis_without_requirements_is_an_error(analysis):
    stripped = analysis.model_copy(update={"requirements": []})
    result = validate_analysis(stripped, "VWO-48")
    assert not result.ok
    assert any("No requirements" in e for e in result.errors)


def test_explicit_requirement_without_a_quote_warns(analysis):
    unsupported = analysis.model_copy(
        update={
            "requirements": [
                analysis.requirements[0].model_copy(update={"source_quote": ""})
            ]
        }
    )
    result = validate_analysis(unsupported, "VWO-48")
    assert any("no source quote" in w for w in result.warnings)


def test_acceptance_criterion_pointing_at_an_unknown_requirement_warns(analysis):
    dangling = analysis.model_copy(
        update={
            "acceptance_criteria": [
                AcceptanceCriterion(id="AC-009", text="x", requirement_ids=["REQ-404"])
            ]
        }
    )
    assert any("unknown requirement" in w for w in validate_analysis(dangling, "VWO-48").warnings)


def test_a_thin_plan_section_is_an_error(test_plan, analysis):
    assert validate_test_plan(test_plan, analysis, "VWO-48").ok
    thin = test_plan.model_copy(
        update={
            "sections": [
                s.model_copy(update={"content": "too short"}) if s.number == 3 else s
                for s in test_plan.sections
            ]
        }
    )
    result = validate_test_plan(thin, analysis, "VWO-48")
    assert not result.ok
    assert any("empty or too thin" in e for e in result.errors)


def test_a_scenario_referencing_an_unknown_id_warns(test_plan, analysis):
    bad = test_plan.model_copy(
        update={
            "scenarios": [
                TestScenario(id="SC-9", title="x", requirement_ids=["REQ-404"])
            ]
        }
    )
    assert any("unknown ids" in w for w in validate_test_plan(bad, analysis, "VWO-48").warnings)


def test_test_cases_referencing_unknown_ids_is_an_error(test_cases, analysis):
    assert validate_test_cases(test_cases, analysis, "VWO-48").ok
    bad = test_cases.model_copy(
        update={
            "test_cases": [
                test_cases.test_cases[0].model_copy(update={"requirement_ids": ["REQ-404"]})
            ]
        }
    )
    result = validate_test_cases(bad, analysis, "VWO-48")
    assert not result.ok
    assert any("REQ-404" in e for e in result.errors)


def test_an_uncovered_acceptance_criterion_warns(test_cases, analysis):
    only_one = test_cases.model_copy(update={"test_cases": [test_cases.test_cases[0]]})
    result = validate_test_cases(only_one, analysis, "VWO-48")
    assert any("AC-002 has no test case" in w for w in result.warnings)


def test_forbidden_playwright_patterns_are_errors(playwright_bundle, test_cases):
    assert validate_playwright(playwright_bundle, test_cases, "VWO-48").ok

    for snippet, expected in (
        ("await page.waitForTimeout(500);", "hard wait"),
        ("page.locator('xpath=//div[1]')", "XPath"),
        ("page.locator('div:nth-child(2)')", "positional CSS"),
    ):
        bad = playwright_bundle.model_copy(
            update={
                "files": [
                    playwright_bundle.files[0].model_copy(
                        update={"content": playwright_bundle.files[0].content + snippet}
                    )
                ]
            }
        )
        result = validate_playwright(bad, test_cases, "VWO-48")
        assert not result.ok
        assert any(expected in e for e in result.errors), snippet


def test_hard_coded_secret_in_generated_code_warns(playwright_bundle, test_cases):
    leaky = playwright_bundle.model_copy(
        update={
            "files": [
                playwright_bundle.files[0].model_copy(
                    update={
                        "content": playwright_bundle.files[0].content
                        + "\nconst password = 'hunter2';"
                    }
                )
            ]
        }
    )
    result = validate_playwright(leaky, test_cases, "VWO-48")
    assert any("hard-coded password" in w for w in result.warnings)


def test_automating_a_manual_only_case_warns(playwright_bundle, test_cases):
    trace = playwright_bundle.traces[0].model_copy(update={"test_case_id": "VWO-48-TC-002"})
    bundle = playwright_bundle.model_copy(update={"traces": [trace]})
    result = validate_playwright(bundle, test_cases, "VWO-48")
    assert any("marked automation_candidate=No" in w for w in result.warnings)


def test_tracing_to_a_nonexistent_test_case_is_an_error(playwright_bundle, test_cases):
    trace = playwright_bundle.traces[0].model_copy(update={"test_case_id": "VWO-48-TC-999"})
    bundle = playwright_bundle.model_copy(update={"traces": [trace]})
    result = validate_playwright(bundle, test_cases, "VWO-48")
    assert not result.ok


def test_ready_with_a_todo_left_in_the_code_is_an_error(playwright_bundle, test_cases):
    bundle = playwright_bundle.model_copy(
        update={"readiness": AutomationReadiness.READY, "missing_information": []}
    )
    result = validate_playwright(bundle, test_cases, "VWO-48")
    assert not result.ok
    assert any("TODO/PLACEHOLDER" in e for e in result.errors)


def test_an_automation_candidate_that_was_not_automated_warns(playwright_bundle, test_cases):
    bundle = playwright_bundle.model_copy(update={"traces": []})
    result = validate_playwright(bundle, test_cases, "VWO-48")
    assert any("was not automated" in w for w in result.warnings)
    assert AutomationCandidate.YES  # sanity: enum imported and used


def test_a_spec_with_no_tests_is_rejected(playwright_bundle, test_cases):
    """Playwright refuses to collect an empty spec: "No tests found"."""
    empty_spec = playwright_bundle.files[0].model_copy(
        update={
            "content": (
                "import { test } from '@playwright/test';\n\n"
                "test.describe('VWO-48', () => {\n"
                "  // no automatable cases were identified\n"
                "});\n"
            )
        }
    )
    bundle = playwright_bundle.model_copy(update={"files": [empty_spec]})
    result = validate_playwright(bundle, test_cases, "VWO-48")

    assert not result.ok
    assert any("contains no test() calls" in e for e in result.errors)


def test_not_applicable_cannot_claim_automated_tests(playwright_bundle):
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError, match="can be no traces"):
        playwright_bundle.model_copy(
            update={"readiness": AutomationReadiness.NOT_APPLICABLE}
        ).model_validate(
            {
                **playwright_bundle.model_dump(),
                "readiness": "NOT_APPLICABLE",
            }
        )


def test_not_applicable_with_no_files_is_valid():
    """The correct shape when nothing is automatable: no files, no traces."""
    bundle = PlaywrightBundle(
        ticket_key="VWO-48",
        files=[],
        traces=[],
        readiness=AutomationReadiness.NOT_APPLICABLE,
        setup_notes="Every test case requires human judgement.",
    )
    assert bundle.files == []
