"""Task construction.

Each task declares its Pydantic output type via ``output_pydantic`` and
receives the earlier tasks as explicit ``context``, so CrewAI passes validated
upstream output forward instead of the agents re-deriving it.
"""

from __future__ import annotations

from crewai import Agent, Task

from ..models import (
    TEST_PLAN_SECTIONS,
    JiraIssue,
    PlaywrightBundle,
    RequirementAnalysis,
    TestCaseSuite,
    TestPlan,
)
from .prompts import task_prompt


def _spec_filename(ticket_key: str) -> str:
    return f"{ticket_key.lower().replace('_', '-')}.spec.ts"


def build_analysis_task(agent: Agent, issue: JiraIssue) -> Task:
    prompt = task_prompt("analysis")
    return Task(
        description=prompt["description"].format(
            ticket_key=issue.key,
            source=issue.source.value,
            issue_text=issue.to_prompt_text(),
        ),
        expected_output=prompt["expected_output"].format(ticket_key=issue.key),
        agent=agent,
        output_pydantic=RequirementAnalysis,
    )


def build_test_plan_task(agent: Agent, ticket_key: str, context: list[Task]) -> Task:
    prompt = task_prompt("test_plan")
    sections = "\n".join(
        f"    {i}. {title}" for i, title in enumerate(TEST_PLAN_SECTIONS, start=1)
    )
    return Task(
        description=prompt["description"].format(
            ticket_key=ticket_key, section_list=sections
        ),
        expected_output=prompt["expected_output"].format(ticket_key=ticket_key),
        agent=agent,
        context=context,
        output_pydantic=TestPlan,
    )


def build_test_cases_task(
    agent: Agent,
    ticket_key: str,
    context: list[Task],
    requirement_ids: list[str],
    acceptance_criteria_ids: list[str],
) -> Task:
    prompt = task_prompt("test_cases")
    return Task(
        description=prompt["description"].format(
            ticket_key=ticket_key,
            requirement_ids=", ".join(requirement_ids) or "(none extracted)",
            acceptance_criteria_ids=(
                ", ".join(acceptance_criteria_ids) or "(none stated in the ticket)"
            ),
        ),
        expected_output=prompt["expected_output"].format(ticket_key=ticket_key),
        agent=agent,
        context=context,
        output_pydantic=TestCaseSuite,
    )


def build_playwright_task(agent: Agent, ticket_key: str, context: list[Task]) -> Task:
    prompt = task_prompt("playwright")
    return Task(
        description=prompt["description"].format(
            ticket_key=ticket_key, spec_filename=_spec_filename(ticket_key)
        ),
        expected_output=prompt["expected_output"].format(ticket_key=ticket_key),
        agent=agent,
        context=context,
        output_pydantic=PlaywrightBundle,
    )
