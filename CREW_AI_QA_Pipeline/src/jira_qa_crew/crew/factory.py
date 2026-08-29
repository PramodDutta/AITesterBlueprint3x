"""Builds one isolated crew per ticket.

A fresh Crew, fresh Agents and fresh Tasks are constructed for every ticket.
Nothing is shared between tickets, so requirement ids or context from one
ticket cannot leak into another.
"""

from __future__ import annotations

from dataclasses import dataclass

from crewai import Crew, Process, Task

from ..config import Settings
from ..jira.gateway import JiraGateway
from ..models import JiraIssue
from ..tools.jira_tool import FetchJiraIssueTool
from .agents import (
    build_jira_analyst,
    build_playwright_coder,
    build_test_case_writer,
    build_test_plan_writer,
)
from .tasks import (
    build_analysis_task,
    build_playwright_task,
    build_test_cases_task,
    build_test_plan_task,
)


@dataclass
class TicketCrew:
    """A crew plus the individual tasks, so stage outputs stay addressable."""

    crew: Crew
    analysis_task: Task
    plan_task: Task
    cases_task: Task
    playwright_task: Task

    @property
    def tasks(self) -> list[Task]:
        return [self.analysis_task, self.plan_task, self.cases_task, self.playwright_task]


def build_ticket_crew(
    settings: Settings,
    issue: JiraIssue,
    gateway: JiraGateway | None = None,
    requirement_ids: list[str] | None = None,
    acceptance_criteria_ids: list[str] | None = None,
) -> TicketCrew:
    """Assemble the four-agent sequential crew for exactly one ticket.

    ``requirement_ids`` / ``acceptance_criteria_ids`` are unknown until the
    analysis stage has run. They are passed as hints when a caller re-builds a
    crew for a later stage; on a fresh full run they are empty and the task
    prompt says so.
    """
    jira_tool = (
        FetchJiraIssueTool(gateway=gateway, allowed_keys={issue.key}) if gateway else None
    )

    analyst = build_jira_analyst(settings, jira_tool)
    plan_writer = build_test_plan_writer(settings)
    case_writer = build_test_case_writer(settings)
    coder = build_playwright_coder(settings)

    analysis_task = build_analysis_task(analyst, issue)
    plan_task = build_test_plan_task(plan_writer, issue.key, [analysis_task])
    cases_task = build_test_cases_task(
        case_writer,
        issue.key,
        [analysis_task, plan_task],
        requirement_ids or [],
        acceptance_criteria_ids or [],
    )
    playwright_task = build_playwright_task(
        coder, issue.key, [analysis_task, plan_task, cases_task]
    )

    crew = Crew(
        agents=[analyst, plan_writer, case_writer, coder],
        tasks=[analysis_task, plan_task, cases_task, playwright_task],
        process=Process.sequential,  # each stage needs the validated one before it
        verbose=False,
        memory=False,  # no cross-ticket memory, by design
    )
    return TicketCrew(crew, analysis_task, plan_task, cases_task, playwright_task)
