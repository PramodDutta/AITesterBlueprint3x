"""Deterministic coverage and traceability calculations."""

from __future__ import annotations

from jira_qa_crew.models import (
    AcceptanceCriterion,
    AutomationCandidate,
    CoverageStatus,
    Requirement,
    TestCase,
    TestCaseSuite,
    TestStep,
)
from jira_qa_crew.services.traceability import build_coverage


def _case(case_id, req=(), acs=(), automation=AutomationCandidate.NO):
    return TestCase(
        id=case_id,
        ticket_key="VWO-48",
        title=case_id,
        requirement_ids=list(req),
        acceptance_criteria_ids=list(acs),
        steps=[TestStep(number=1, action="do the thing")],
        automation_candidate=automation,
        automation_rationale="because",
    )


def test_full_coverage_when_every_item_has_a_case(analysis, test_cases, playwright_bundle):
    coverage = build_coverage(analysis, test_cases, playwright_bundle)
    assert coverage.total_requirements == 2
    assert coverage.total_acceptance_criteria == 2
    assert coverage.total_test_cases == 2
    assert coverage.covered_acceptance_criteria == 2
    assert not coverage.orphan_requirement_ids
    assert not coverage.orphan_test_case_ids


def test_a_requirement_with_no_test_case_is_uncovered_and_orphaned(analysis):
    suite = TestCaseSuite(
        ticket_key="VWO-48", test_cases=[_case("VWO-48-TC-001", req=["REQ-001"], acs=["AC-001"])]
    )
    coverage = build_coverage(analysis, suite, None)
    assert coverage.orphan_requirement_ids == ["REQ-002"]
    assert coverage.uncovered_requirements == 1
    uncovered = [r for r in coverage.rows if r.requirement_id == "REQ-002"]
    assert uncovered and uncovered[0].coverage_status is CoverageStatus.UNCOVERED
    assert "No test case" in uncovered[0].reason


def test_an_automation_candidate_without_a_generated_test_is_partial(analysis, playwright_bundle):
    suite = TestCaseSuite(
        ticket_key="VWO-48",
        test_cases=[
            _case("VWO-48-TC-001", req=["REQ-001"], acs=["AC-001"],
                  automation=AutomationCandidate.YES),
            _case("VWO-48-TC-003", req=["REQ-002"], acs=["AC-002"],
                  automation=AutomationCandidate.YES),
        ],
    )
    coverage = build_coverage(analysis, suite, playwright_bundle)
    row = next(r for r in coverage.rows if r.requirement_id == "REQ-002")
    assert row.coverage_status is CoverageStatus.PARTIAL
    assert "VWO-48-TC-003" in row.reason


def test_manual_only_coverage_still_counts_as_covered(analysis):
    suite = TestCaseSuite(
        ticket_key="VWO-48",
        test_cases=[
            _case("VWO-48-TC-001", req=["REQ-001"], acs=["AC-001"]),
            _case("VWO-48-TC-002", req=["REQ-002"], acs=["AC-002"]),
        ],
    )
    coverage = build_coverage(analysis, suite, None)
    assert coverage.covered_requirements == 2
    assert coverage.requirement_coverage_pct == 100.0
    assert all(r.coverage_status is CoverageStatus.COVERED for r in coverage.rows)


def test_a_case_referencing_an_unknown_id_is_recorded_not_silently_dropped(analysis):
    suite = TestCaseSuite(
        ticket_key="VWO-48",
        test_cases=[_case("VWO-48-TC-001", req=["REQ-404"], acs=["AC-404"])],
    )
    coverage = build_coverage(analysis, suite, None)
    assert coverage.unknown_reference_ids == ["AC-404", "REQ-404"]
    assert coverage.orphan_test_case_ids == ["VWO-48-TC-001"]


def test_an_acceptance_criterion_with_no_requirement_still_gets_a_row(analysis):
    unlinked = analysis.model_copy(
        update={
            "acceptance_criteria": [
                *analysis.acceptance_criteria,
                AcceptanceCriterion(id="AC-003", text="floating", requirement_ids=[]),
            ]
        }
    )
    suite = TestCaseSuite(
        ticket_key="VWO-48", test_cases=[_case("VWO-48-TC-001", acs=["AC-003"])]
    )
    coverage = build_coverage(unlinked, suite, None)
    row = next(r for r in coverage.rows if r.acceptance_criterion_id == "AC-003")
    assert row.requirement_id == "(unlinked)"
    assert row.test_case_ids == ["VWO-48-TC-001"]


def test_automation_percentage_is_computed_from_real_traces(analysis, test_cases, playwright_bundle):
    coverage = build_coverage(analysis, test_cases, playwright_bundle)
    assert coverage.automated_test_cases == 1
    assert coverage.automation_pct == 50.0


def test_empty_inputs_do_not_divide_by_zero():
    empty_analysis = type(analysis_stub())(
        ticket_key="X-1", summary="s", requirements=[], acceptance_criteria=[]
    )
    coverage = build_coverage(empty_analysis, None, None)
    assert coverage.requirement_coverage_pct == 0.0
    assert coverage.automation_pct == 0.0


def analysis_stub():
    from jira_qa_crew.models import RequirementAnalysis

    return RequirementAnalysis(ticket_key="X-1", summary="s")


def test_requirement_inherits_coverage_from_its_acceptance_criterion(analysis):
    """A case that only names AC-001 still covers REQ-001, which AC-001 verifies."""
    suite = TestCaseSuite(
        ticket_key="VWO-48", test_cases=[_case("VWO-48-TC-001", acs=["AC-001"])]
    )
    coverage = build_coverage(analysis, suite, None)
    row = next(r for r in coverage.rows if r.requirement_id == "REQ-001")
    assert row.coverage_status is CoverageStatus.COVERED
    assert Requirement  # imported for the reader's benefit
