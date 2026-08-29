"""Compact stage-to-stage handoffs.

Why this exists: CrewAI's ``Task.context`` forwards the *raw text* of every
upstream task. In a four-stage pipeline that compounds, and by stage three the
prompt carries the full JSON of the analysis and the plan, source quotes and
all. Large models cope; several do not, and return truncated or empty
completions.

So the pipeline hands each stage a deterministic summary rendered from the
*validated* upstream object instead. That is strictly better than the raw
text: it is smaller, it cannot contain anything the schema rejected, and it
carries exactly the fields the next stage is allowed to reference.
"""

from __future__ import annotations

from ..models import (
    AutomationCandidate,
    RequirementAnalysis,
    TestCaseSuite,
    TestPlan,
)

#: Keep a single list from swamping the prompt on a very large ticket.
_MAX_ITEMS = 40
_MAX_CHARS = 240


def _clip(text: str, limit: int = _MAX_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _bullets(title: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"{title}:", *[f"- {_clip(v)}" for v in values[:_MAX_ITEMS]]]


def analysis_handoff(analysis: RequirementAnalysis) -> str:
    """What the plan writer and the case writer need from stage 1."""
    lines = [
        "## VALIDATED REQUIREMENT ANALYSIS (from the previous task)",
        f"Ticket: {analysis.ticket_key} — {_clip(analysis.summary)}",
    ]
    if analysis.description_summary:
        lines.append(f"Summary: {_clip(analysis.description_summary, 400)}")

    lines.append("")
    lines.append("Requirements (use these ids exactly, never invent one):")
    for req in analysis.requirements[:_MAX_ITEMS]:
        lines.append(f"- {req.id} [{req.provenance.value}] {_clip(req.text)}")
    if not analysis.requirements:
        lines.append("- (none extracted)")

    lines.append("")
    lines.append("Acceptance criteria (use these ids exactly):")
    for criterion in analysis.acceptance_criteria[:_MAX_ITEMS]:
        verifies = ", ".join(criterion.requirement_ids) or "unlinked"
        lines.append(f"- {criterion.id} (verifies {verifies}) {_clip(criterion.text)}")
    if not analysis.acceptance_criteria:
        lines.append("- (the ticket states none; do not invent any)")

    for title, values in (
        ("Business rules", analysis.business_rules),
        ("Non-functional requirements", analysis.non_functional_requirements),
        ("Constraints", analysis.constraints),
        ("Risks", analysis.risks),
        ("Missing information (do not fill these in with guesses)",
         analysis.missing_information),
    ):
        block = _bullets(title, values)
        if block:
            lines.extend(["", *block])
    return "\n".join(lines)


def plan_handoff(plan: TestPlan) -> str:
    """What the case writer needs from stage 2: scope and scenarios, not prose."""
    lines = [
        "## VALIDATED TEST PLAN (from the previous task)",
        f"Title: {_clip(plan.title)}",
        "",
        "Section highlights:",
    ]
    # Scope and strategy steer the test cases; the rest is reporting detail.
    for section in plan.sections:
        if section.number in (3, 4, 6, 9):
            lines.append(f"- {section.number}. {section.title}: {_clip(section.content, 320)}")

    if plan.scenarios:
        lines += ["", "Scenarios to expand into test cases:"]
        for scenario in plan.scenarios[:_MAX_ITEMS]:
            refs = ", ".join([*scenario.requirement_ids, *scenario.acceptance_criteria_ids])
            lines.append(
                f"- {scenario.id} [{scenario.priority.value}] {_clip(scenario.title)} "
                f"(traces to {refs})"
            )
    return "\n".join(lines)


def cases_handoff(suite: TestCaseSuite) -> str:
    """What the Playwright coder needs from stage 3.

    Only the automatable cases. Sending the manual-only ones would just invite
    the coder to automate something a human already judged un-automatable.
    """
    automatable = [
        case
        for case in suite.test_cases
        if case.automation_candidate in (AutomationCandidate.YES, AutomationCandidate.PARTIAL)
    ]
    manual = [c.id for c in suite.test_cases if c not in automatable]

    lines = [
        "## VALIDATED TEST CASES (from the previous task)",
        f"{len(suite.test_cases)} test cases, {len(automatable)} marked for automation.",
        "",
        "Automate ONLY these:",
    ]
    if not automatable:
        lines.append("- (none: no test case was marked Yes or Partial)")

    for case in automatable[:_MAX_ITEMS]:
        refs = ", ".join([*case.requirement_ids, *case.acceptance_criteria_ids])
        lines += [
            "",
            f"### {case.id} [{case.automation_candidate.value}, {case.priority.value}, "
            f"{case.test_type.value}] {_clip(case.title)}",
            f"traces to: {refs}",
        ]
        if case.preconditions:
            lines.append(f"preconditions: {_clip('; '.join(case.preconditions))}")
        if case.test_data:
            lines.append(f"test data: {_clip('; '.join(case.test_data))}")
        for step in case.steps[:15]:
            expected = f" -> {_clip(step.expected, 120)}" if step.expected else ""
            lines.append(f"  {step.number}. {_clip(step.action, 160)}{expected}")
        if case.expected_result:
            lines.append(f"expected result: {_clip(case.expected_result)}")
        if case.assumptions_or_blockers:
            lines.append(
                f"blockers: {_clip('; '.join(case.assumptions_or_blockers))}"
            )

    if manual:
        lines += ["", f"Do NOT automate (marked No): {', '.join(manual[:_MAX_ITEMS])}"]
    return "\n".join(lines)
