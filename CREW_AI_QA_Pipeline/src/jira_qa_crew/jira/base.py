"""Provider interface shared by the MCP and REST implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import JiraIssue, JiraSource


class JiraProvider(ABC):
    """Fetches one Jira issue and returns it normalized.

    Implementations must raise a subclass of
    :class:`jira_qa_crew.exceptions.JiraError` on failure. They must never
    return partial or fabricated data, and never fall back to fixtures.
    """

    #: Recorded on every issue this provider returns.
    source: JiraSource

    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Cheap reachability probe. Returns ``(ok, human readable detail)``."""

    @abstractmethod
    def fetch_issue(self, issue_key: str) -> JiraIssue:
        """Fetch and normalize a single issue, or raise a ``JiraError``."""
