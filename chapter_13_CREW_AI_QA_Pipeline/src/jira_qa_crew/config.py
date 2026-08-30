"""Application configuration.

Everything is read from the environment (or ``st.secrets``, which the UI
copies into the environment before this module is used). Nothing here is
collected from ordinary UI text fields, and nothing secret is ever returned
by :meth:`Settings.status`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .exceptions import ConfigurationError

# Minimum length before a value is worth redacting; shorter values are noise.
_MIN_SECRET_LENGTH = 8


class IntegrationMode(StrEnum):
    """Which Jira provider(s) the gateway is allowed to use."""

    AUTO = "auto"
    MCP = "mcp"
    REST = "rest"


class AuthMode(StrEnum):
    BASIC = "basic"
    BEARER = "bearer"


class StructuredOutputMode(StrEnum):
    """How the LLM is asked to return structured data.

    ``auto``   detect from the provider's own error, then remember
    ``schema``  always ask the provider to enforce the JSON schema
    ``prompt``  never ask; put the schema in the prompt and validate here
    """

    AUTO = "auto"
    SCHEMA = "schema"
    PROMPT = "prompt"


class MCPTransport(StrEnum):
    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"
    STDIO = "stdio"


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer, got {raw!r}") from exc


def _env_float(key: str, default: float) -> float:
    raw = _env(key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number, got {raw!r}") from exc


def _env_json(key: str, default: Any) -> Any:
    raw = _env(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{key} must be valid JSON, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the environment.

    Build it with :meth:`load`; never mutate it. The pipeline receives one
    instance so a run cannot be reconfigured halfway through.
    """

    # app
    app_name: str = "Jira QA Crew"
    app_env: str = "development"
    output_dir: Path = Path("outputs")
    log_level: str = "INFO"
    demo_mode: bool = False

    # llm
    llm_model: str = "deepseek/deepseek-v4-flash"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 8000
    llm_structured_output: StructuredOutputMode = StructuredOutputMode.AUTO

    # jira (shared)
    jira_integration_mode: IntegrationMode = IntegrationMode.AUTO
    jira_url: str = ""
    jira_auth_mode: AuthMode = AuthMode.BASIC
    jira_email: str = ""
    jira_api_token: str = ""
    jira_bearer_token: str = ""
    jira_api_version: str = "3"
    jira_acceptance_criteria_field: str = ""
    jira_include_comments: bool = False
    jira_max_comments: int = 20
    jira_timeout_seconds: int = 30
    jira_key_pattern: str = r"^[A-Z][A-Z0-9_]+-\d+$"

    # jira mcp
    jira_mcp_transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    jira_mcp_url: str = ""
    jira_mcp_command: str = ""
    jira_mcp_args: list[str] = field(default_factory=list)
    jira_mcp_headers: dict[str, str] = field(default_factory=dict)
    jira_mcp_get_issue_tool: str = ""
    jira_mcp_issue_key_arg: str = "issueIdOrKey"
    jira_mcp_extra_args: dict[str, Any] = field(default_factory=dict)
    jira_mcp_timeout_seconds: int = 20
    jira_mcp_allowed_tools: list[str] = field(default_factory=list)

    # pipeline
    pipeline_max_tickets: int = 20
    pipeline_max_retries: int = 2
    pipeline_ticket_timeout_seconds: int = 600
    pipeline_max_input_chars: int = 4000

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, env_file: str | os.PathLike[str] | None = None) -> Settings:
        """Read the environment into a Settings instance.

        Raises :class:`ConfigurationError` only for values that are present
        but unusable. Missing credentials are NOT fatal here: the UI shows a
        readiness panel instead, so the app can start and be inspected
        without secrets.
        """
        # Set JIRA_QA_CREW_SKIP_DOTENV=1 to read the environment only. Tests
        # rely on this so a developer's local .env cannot change their result,
        # and containers can use it to keep configuration explicit.
        if os.getenv("JIRA_QA_CREW_SKIP_DOTENV") == "1":
            pass
        elif env_file:
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(override=False)

        def _enum(enum_cls, key: str, default):
            raw = _env(key)
            if not raw:
                return default
            try:
                return enum_cls(raw.lower())
            except ValueError as exc:
                allowed = ", ".join(m.value for m in enum_cls)
                raise ConfigurationError(
                    f"{key} must be one of: {allowed}. Got {raw!r}"
                ) from exc

        mcp_args = _env_json("JIRA_MCP_ARGS_JSON", [])
        if not isinstance(mcp_args, list):
            raise ConfigurationError("JIRA_MCP_ARGS_JSON must be a JSON array")
        mcp_headers = _env_json("JIRA_MCP_HEADERS_JSON", {})
        if not isinstance(mcp_headers, dict):
            raise ConfigurationError("JIRA_MCP_HEADERS_JSON must be a JSON object")
        mcp_extra = _env_json("JIRA_MCP_EXTRA_ARGS_JSON", {})
        if not isinstance(mcp_extra, dict):
            raise ConfigurationError("JIRA_MCP_EXTRA_ARGS_JSON must be a JSON object")
        allowed_tools = _env_json("JIRA_MCP_ALLOWED_TOOLS_JSON", [])
        if not isinstance(allowed_tools, list):
            raise ConfigurationError("JIRA_MCP_ALLOWED_TOOLS_JSON must be a JSON array")

        temperature = _env_float("LLM_TEMPERATURE", 0.1)
        if not 0.0 <= temperature <= 2.0:
            raise ConfigurationError("LLM_TEMPERATURE must be between 0.0 and 2.0")

        max_tickets = _env_int("PIPELINE_MAX_TICKETS", 20)
        if max_tickets < 1:
            raise ConfigurationError("PIPELINE_MAX_TICKETS must be >= 1")

        pattern = _env("JIRA_KEY_PATTERN", r"^[A-Z][A-Z0-9_]+-\d+$")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigurationError(f"JIRA_KEY_PATTERN is not a valid regex: {exc}") from exc

        return cls(
            app_name=_env("APP_NAME", "Jira QA Crew"),
            app_env=_env("APP_ENV", "development"),
            output_dir=Path(_env("OUTPUT_DIR", "outputs")),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            demo_mode=_env_bool("DEMO_MODE", False),
            llm_model=_env("LLM_MODEL", "deepseek/deepseek-v4-flash"),
            llm_api_key=_env("LLM_API_KEY") or _env("DEEPSEEK_API_KEY"),
            llm_base_url=_env("LLM_BASE_URL") or _env("DEEPSEEK_BASE_URL"),
            llm_temperature=temperature,
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", 8000),
            llm_structured_output=_enum(
                StructuredOutputMode, "LLM_STRUCTURED_OUTPUT", StructuredOutputMode.AUTO
            ),
            jira_integration_mode=_enum(
                IntegrationMode, "JIRA_INTEGRATION_MODE", IntegrationMode.AUTO
            ),
            jira_url=_env("JIRA_URL").rstrip("/"),
            jira_auth_mode=_enum(AuthMode, "JIRA_AUTH_MODE", AuthMode.BASIC),
            jira_email=_env("JIRA_EMAIL"),
            jira_api_token=_env("JIRA_API_TOKEN"),
            jira_bearer_token=_env("JIRA_BEARER_TOKEN"),
            jira_api_version=_env("JIRA_API_VERSION", "3"),
            jira_acceptance_criteria_field=_env("JIRA_ACCEPTANCE_CRITERIA_FIELD"),
            jira_include_comments=_env_bool("JIRA_INCLUDE_COMMENTS", False),
            jira_max_comments=_env_int("JIRA_MAX_COMMENTS", 20),
            jira_timeout_seconds=_env_int("JIRA_TIMEOUT_SECONDS", 30),
            jira_key_pattern=pattern,
            jira_mcp_transport=_enum(
                MCPTransport, "JIRA_MCP_TRANSPORT", MCPTransport.STREAMABLE_HTTP
            ),
            jira_mcp_url=_env("JIRA_MCP_URL"),
            jira_mcp_command=_env("JIRA_MCP_COMMAND"),
            jira_mcp_args=[str(a) for a in mcp_args],
            jira_mcp_headers={str(k): str(v) for k, v in mcp_headers.items()},
            jira_mcp_get_issue_tool=_env("JIRA_MCP_GET_ISSUE_TOOL"),
            jira_mcp_issue_key_arg=_env("JIRA_MCP_ISSUE_KEY_ARG", "issueIdOrKey"),
            jira_mcp_extra_args=mcp_extra,
            jira_mcp_timeout_seconds=_env_int("JIRA_MCP_TIMEOUT_SECONDS", 20),
            jira_mcp_allowed_tools=[str(t) for t in allowed_tools],
            pipeline_max_tickets=max_tickets,
            pipeline_max_retries=_env_int("PIPELINE_MAX_RETRIES", 2),
            pipeline_ticket_timeout_seconds=_env_int("PIPELINE_TICKET_TIMEOUT_SECONDS", 600),
            pipeline_max_input_chars=_env_int("PIPELINE_MAX_INPUT_CHARS", 4000),
        )

    # ------------------------------------------------------------------
    @property
    def secrets(self) -> tuple[str, ...]:
        """Every value that must never appear in a log, error, or artifact."""
        candidates = (
            self.llm_api_key,
            self.jira_api_token,
            self.jira_bearer_token,
            *self.jira_mcp_headers.values(),
        )
        return tuple(c for c in candidates if c and len(c) >= _MIN_SECRET_LENGTH)

    def redact(self, text: str) -> str:
        """Replace every known secret in ``text`` with a marker.

        Applied to all log lines and all error messages that reach the UI.
        """
        if not text:
            return text
        cleaned = text
        for secret in self.secrets:
            cleaned = cleaned.replace(secret, "***REDACTED***")
        # Basic-auth headers embed base64 credentials; drop the payload.
        cleaned = re.sub(
            r"(Basic|Bearer)\s+[A-Za-z0-9+/=_\-.]{8,}", r"\1 ***REDACTED***", cleaned
        )
        return cleaned

    # ------------------------------------------------------------------
    def llm_ready(self) -> bool:
        return bool(self.llm_model and self.llm_api_key)

    def rest_ready(self) -> bool:
        if not self.jira_url:
            return False
        if self.jira_auth_mode is AuthMode.BASIC:
            return bool(self.jira_email and self.jira_api_token)
        return bool(self.jira_bearer_token)

    def mcp_ready(self) -> bool:
        if self.jira_mcp_transport is MCPTransport.STDIO:
            return bool(self.jira_mcp_command)
        return bool(self.jira_mcp_url)

    def status(self) -> dict[str, dict[str, Any]]:
        """Redacted readiness report for the UI. Contains no secret values."""

        def mask(value: str) -> str:
            if not value:
                return "not set"
            if len(value) <= 4:
                return "set"
            return f"set (…{value[-4:]})"

        return {
            "llm": {
                "ready": self.llm_ready(),
                "model": self.llm_model or "not set",
                "api_key": mask(self.llm_api_key),
                "temperature": self.llm_temperature,
                "structured_output": self.llm_structured_output.value,
            },
            "jira_rest": {
                "ready": self.rest_ready(),
                "url": self.jira_url or "not set",
                "auth_mode": self.jira_auth_mode.value,
                "email": self.jira_email or "not set",
                "token": mask(self.jira_api_token or self.jira_bearer_token),
            },
            "jira_mcp": {
                "ready": self.mcp_ready(),
                "transport": self.jira_mcp_transport.value,
                "endpoint": self.jira_mcp_url or self.jira_mcp_command or "not set",
                "get_issue_tool": self.jira_mcp_get_issue_tool or "auto-detect",
            },
            "pipeline": {
                "ready": True,
                "mode": self.jira_integration_mode.value,
                "max_tickets": self.pipeline_max_tickets,
                "demo_mode": self.demo_mode,
                "output_dir": str(self.output_dir),
            },
        }

    def blocking_problems(self) -> list[str]:
        """Reasons a real run cannot start yet, in plain language."""
        problems: list[str] = []
        if self.demo_mode:
            return problems
        if not self.llm_ready():
            problems.append(
                "LLM is not configured. Set LLM_MODEL and LLM_API_KEY "
                "(or DEEPSEEK_API_KEY)."
            )
        mode = self.jira_integration_mode
        if mode is IntegrationMode.REST and not self.rest_ready():
            problems.append(
                "Integration mode is 'rest' but the Jira REST settings are "
                "incomplete (JIRA_URL plus credentials)."
            )
        elif mode is IntegrationMode.MCP and not self.mcp_ready():
            problems.append(
                "Integration mode is 'mcp' but no MCP endpoint is configured "
                "(JIRA_MCP_URL or JIRA_MCP_COMMAND)."
            )
        elif mode is IntegrationMode.AUTO and not (self.rest_ready() or self.mcp_ready()):
            problems.append(
                "Integration mode is 'auto' but neither MCP nor REST is "
                "configured, so no ticket can be fetched."
            )
        return problems
