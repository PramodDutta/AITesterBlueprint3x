"""Typed exceptions for the Jira QA Crew pipeline.

Every failure surfaced to the UI is one of these. They carry a user-safe
message (``str(exc)``) that is guaranteed to have secrets redacted by the
callers in :mod:`jira_qa_crew.config`.
"""

from __future__ import annotations


class JiraQAError(Exception):
    """Base class for every error raised by this application."""


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
class ConfigurationError(JiraQAError):
    """Configuration is missing or internally inconsistent."""


# --------------------------------------------------------------------------
# Jira
# --------------------------------------------------------------------------
class JiraError(JiraQAError):
    """Base class for Jira provider failures."""


class JiraAuthError(JiraError):
    """401/403: credentials rejected or insufficient permissions."""


class JiraNotFoundError(JiraError):
    """404: the issue does not exist or is not visible to this account."""


class JiraRateLimitError(JiraError):
    """429: Jira asked us to slow down."""


class JiraTimeoutError(JiraError):
    """The provider did not answer inside the configured timeout."""


class JiraMalformedResponseError(JiraError):
    """The provider answered, but the payload is not a usable issue."""


class MCPUnavailableError(JiraError):
    """The MCP server could not be reached, started, or has no usable tool."""


class AllProvidersFailedError(JiraError):
    """Every provider allowed by the current mode failed.

    Carries the individual provider errors so the UI can explain both.
    """

    def __init__(self, message: str, provider_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.provider_errors = provider_errors or {}


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
class PipelineError(JiraQAError):
    """A stage of the per-ticket pipeline failed."""


class StructuredOutputError(PipelineError):
    """An agent returned output that does not satisfy its Pydantic schema."""


class ValidationFailure(PipelineError):
    """Deterministic post-stage validation rejected an otherwise valid object."""


class TicketInputError(JiraQAError):
    """The submitted ticket input could not be parsed into valid Jira keys."""
