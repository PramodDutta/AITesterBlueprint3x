"""The four CrewAI agents.

Only the Jira Analyst receives the Jira tool. The other three work from the
validated output of the stage before them, so they have no way to reach Jira
even if a prompt injection asks them to.
"""

from __future__ import annotations

from typing import Any

from crewai import LLM, Agent

from ..config import Settings
from ..tools.jira_tool import FetchJiraIssueTool
from .prompts import agent_prompt


def build_llm(settings: Settings, max_tokens: int | None = None) -> LLM:
    """One LLM instance per agent so token budgets can differ per stage."""
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
        "temperature": settings.llm_temperature,
        "max_tokens": max_tokens or settings.llm_max_tokens,
    }
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return LLM(**kwargs)


def _agent(key: str, settings: Settings, **overrides: Any) -> Agent:
    prompt = agent_prompt(key)
    params: dict[str, Any] = {
        "role": prompt["role"],
        "goal": prompt["goal"],
        "backstory": prompt["backstory"],
        "llm": build_llm(settings),
        "verbose": False,
        "allow_delegation": False,  # sequential pipeline; nobody delegates
        "max_iter": 8,
        "max_retry_limit": 1,  # one controlled repair attempt, never a loop
    }
    params.update(overrides)
    return Agent(**params)


def build_jira_analyst(settings: Settings, jira_tool: FetchJiraIssueTool | None) -> Agent:
    return _agent(
        "jira_analyst",
        settings,
        tools=[jira_tool] if jira_tool else [],
    )


def build_test_plan_writer(settings: Settings) -> Agent:
    return _agent("test_plan_writer", settings)


def build_test_case_writer(settings: Settings) -> Agent:
    return _agent("test_case_writer", settings)


def build_playwright_coder(settings: Settings) -> Agent:
    return _agent("playwright_coder", settings)
