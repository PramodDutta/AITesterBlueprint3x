"""Loader for the YAML prompt files.

Prompts live in ``jira_qa_crew/prompts`` so they can be edited without
touching orchestration or UI code.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import ConfigurationError

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@functools.lru_cache(maxsize=4)
def load_prompts(name: str) -> dict[str, Any]:
    """Load and cache ``prompts/<name>.yaml``."""
    path = PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise ConfigurationError(f"Prompt file not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigurationError(f"Prompt file {path.name} must contain a mapping")
    return data


def agent_prompt(key: str) -> dict[str, str]:
    prompts = load_prompts("agents")
    if key not in prompts:
        raise ConfigurationError(f"No agent prompt named {key!r} in agents.yaml")
    entry = prompts[key]
    missing = {"role", "goal", "backstory"} - set(entry)
    if missing:
        raise ConfigurationError(f"Agent prompt {key!r} is missing: {sorted(missing)}")
    return {k: str(v).strip() for k, v in entry.items()}


def task_prompt(key: str) -> dict[str, str]:
    prompts = load_prompts("tasks")
    if key not in prompts:
        raise ConfigurationError(f"No task prompt named {key!r} in tasks.yaml")
    entry = prompts[key]
    missing = {"description", "expected_output"} - set(entry)
    if missing:
        raise ConfigurationError(f"Task prompt {key!r} is missing: {sorted(missing)}")
    return {k: str(v) for k, v in entry.items()}
