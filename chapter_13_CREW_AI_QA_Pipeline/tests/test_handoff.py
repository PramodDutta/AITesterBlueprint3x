"""Compact stage-to-stage handoffs.

These replace CrewAI's raw ``Task.context`` text. The tests below pin the two
properties that matter: the handoff is much smaller than the raw output, and
it still carries everything the next stage is allowed to reference.
"""

from __future__ import annotations

from jira_qa_crew.models import AutomationCandidate
from jira_qa_crew.services.handoff import analysis_handoff, cases_handoff, plan_handoff


# --------------------------------------------------------------------------
# Analysis -> plan / cases
# --------------------------------------------------------------------------
def test_analysis_handoff_carries_every_id(analysis):
    text = analysis_handoff(analysis)
    for requirement in analysis.requirements:
        assert requirement.id in text
    for criterion in analysis.acceptance_criteria:
        assert criterion.id in text
    assert "REQ-001" in text and "AC-001" in text


def test_analysis_handoff_shows_which_requirement_an_ac_verifies(analysis):
    assert "AC-001 (verifies REQ-001)" in analysis_handoff(analysis)


def test_analysis_handoff_marks_provenance(analysis):
    assert "[EXPLICIT]" in analysis_handoff(analysis)


def test_analysis_handoff_forwards_missing_information(analysis):
    text = analysis_handoff(analysis)
    assert "Missing information" in text
    assert "do not fill these in with guesses" in text
    assert analysis.missing_information[0][:30] in text


def test_analysis_handoff_says_so_when_there_are_no_acceptance_criteria(analysis):
    empty = analysis.model_copy(update={"acceptance_criteria": []})
    assert "do not invent any" in analysis_handoff(empty)


def test_analysis_handoff_is_much_smaller_than_the_raw_output(analysis):
    assert len(analysis_handoff(analysis)) < len(analysis.model_dump_json())


# --------------------------------------------------------------------------
# Plan -> cases
# --------------------------------------------------------------------------
def test_plan_handoff_keeps_scope_and_scenarios_not_the_whole_plan(test_plan):
    text = plan_handoff(test_plan)
    assert "SC-001" in text
    assert "traces to REQ-001, AC-001" in text
    # scope (3), out of scope (4), strategy (6) and scenarios (9) are kept
    assert "3. In Scope" in text
    assert "9. High-Level Test Scenarios" in text
    # reporting detail is not
    assert "12. Execution" not in text
    assert len(text) < len(test_plan.model_dump_json()) // 2


# --------------------------------------------------------------------------
# Cases -> Playwright
# --------------------------------------------------------------------------
def test_cases_handoff_sends_only_the_automatable_cases(test_cases):
    text = cases_handoff(test_cases)
    assert "VWO-48-TC-001" in text          # automation_candidate = Yes
    assert "Automate ONLY these" in text
    assert "Do NOT automate (marked No): VWO-48-TC-002" in text
    # the manual case's steps must not be handed over as if they were work
    assert "Apply SAVE20 to a five item cart" not in text


def test_cases_handoff_carries_steps_and_traces(test_cases):
    text = cases_handoff(test_cases)
    assert "Seed a cart with three items" in text
    assert "traces to: REQ-001, AC-001" in text
    assert "Total shows $72.00" in text


def test_cases_handoff_handles_a_suite_with_nothing_to_automate(test_cases):
    manual_only = test_cases.model_copy(
        update={
            "test_cases": [
                case.model_copy(update={"automation_candidate": AutomationCandidate.NO})
                for case in test_cases.test_cases
            ]
        }
    )
    text = cases_handoff(manual_only)
    assert "no test case was marked Yes or Partial" in text


def test_long_values_are_clipped_so_one_field_cannot_swamp_the_prompt(analysis):
    huge = analysis.model_copy(
        update={
            "requirements": [
                analysis.requirements[0].model_copy(update={"text": "x" * 5000})
            ]
        }
    )
    text = analysis_handoff(huge)
    assert len(text) < 2000
    assert "…" in text


def test_handoffs_are_deterministic(analysis, test_plan, test_cases):
    """Same object in, same text out: no randomness, no timestamps."""
    assert analysis_handoff(analysis) == analysis_handoff(analysis)
    assert plan_handoff(test_plan) == plan_handoff(test_plan)
    assert cases_handoff(test_cases) == cases_handoff(test_cases)
