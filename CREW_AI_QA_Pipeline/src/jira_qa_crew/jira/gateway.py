"""Deterministic provider selection.

The MCP-then-REST decision is application logic, never an LLM decision. The
gateway is the only place that decides, and it records which provider actually
answered so the UI can show a truthful source badge.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import IntegrationMode, Settings
from ..exceptions import (
    AllProvidersFailedError,
    ConfigurationError,
    JiraError,
    JiraNotFoundError,
)
from ..models import JiraIssue, JiraSource
from .base import JiraProvider
from .mcp_provider import JiraMCPProvider
from .rest_provider import JiraRestProvider

logger = logging.getLogger(__name__)


class JiraGateway:
    """Fetches issues according to the configured integration mode.

    ``auto``  -> try MCP, then REST
    ``mcp``   -> MCP only
    ``rest``  -> REST only

    Demo mode reads local fixtures, and is only ever reached when
    ``DEMO_MODE=true`` is set explicitly. It is never used as a fallback for a
    failed live integration.
    """

    def __init__(
        self,
        settings: Settings,
        mcp_provider: JiraProvider | None = None,
        rest_provider: JiraProvider | None = None,
        fixtures_dir: Path | None = None,
    ):
        self.settings = settings
        self._mcp = mcp_provider or JiraMCPProvider(settings)
        self._rest = rest_provider or JiraRestProvider(settings)
        self._fixtures_dir = fixtures_dir or Path(__file__).resolve().parents[3] / "fixtures"

    # ------------------------------------------------------------------
    def providers_for(self, mode: IntegrationMode | None = None) -> list[JiraProvider]:
        """Ordered provider list for the effective mode."""
        effective = mode or self.settings.jira_integration_mode
        if effective is IntegrationMode.MCP:
            return [self._mcp]
        if effective is IntegrationMode.REST:
            return [self._rest]
        return [self._mcp, self._rest]

    # ------------------------------------------------------------------
    def health(self, mode: IntegrationMode | None = None) -> dict[str, tuple[bool, str]]:
        return {p.name: p.health_check() for p in self.providers_for(mode)}

    # ------------------------------------------------------------------
    def fetch_issue(
        self, issue_key: str, mode: IntegrationMode | None = None
    ) -> JiraIssue:
        """Fetch one issue, or raise :class:`AllProvidersFailedError`."""
        if self.settings.demo_mode:
            return self._fetch_fixture(issue_key)

        errors: dict[str, str] = {}
        for provider in self.providers_for(mode):
            try:
                issue = provider.fetch_issue(issue_key)
            except JiraNotFoundError as exc:
                # A 404 from a reachable provider is a real answer about this
                # ticket, but another provider may still see it (different
                # auth), so keep going and report it if everything fails.
                errors[provider.name] = self.settings.redact(str(exc))
                logger.info("%s: %s not found", provider.name, issue_key)
                continue
            except JiraError as exc:
                errors[provider.name] = self.settings.redact(str(exc))
                logger.warning(
                    "%s failed for %s: %s", provider.name, issue_key, errors[provider.name]
                )
                continue
            except Exception as exc:  # noqa: BLE001 - provider bugs must not kill the run
                errors[provider.name] = self.settings.redact(
                    f"unexpected {type(exc).__name__}: {exc}"
                )
                logger.exception("%s raised unexpectedly for %s", provider.name, issue_key)
                continue

            if not issue.summary and not issue.description:
                errors[provider.name] = "returned an issue with no summary and no description"
                continue

            logger.info("fetched %s via %s", issue_key, provider.source.value)
            return issue

        raise AllProvidersFailedError(
            f"Could not fetch {issue_key} from any configured provider.", errors
        )

    # ------------------------------------------------------------------
    def _fetch_fixture(self, issue_key: str) -> JiraIssue:
        """Load a local fixture. Only reachable when DEMO_MODE is enabled."""
        safe = issue_key.replace("/", "_").replace("..", "_")
        path = self._fixtures_dir / f"{safe}.json"
        if not path.exists():
            raise AllProvidersFailedError(
                f"DEMO_MODE is on but no fixture exists at {path.name}.",
                {"demo": "missing fixture"},
            )
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Fixture {path.name} is not valid JSON") from exc

        from .rest_provider import build_issue_from_rest

        issue = build_issue_from_rest(payload, self.settings, JiraSource.DEMO_FIXTURE)
        logger.warning("DEMO MODE: %s loaded from fixture, not from Jira", issue_key)
        return issue
