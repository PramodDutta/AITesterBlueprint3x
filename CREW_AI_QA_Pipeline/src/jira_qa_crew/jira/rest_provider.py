"""Jira Cloud REST provider (the fallback path).

Uses ``GET /rest/api/{version}/issue/{issueIdOrKey}``, parses ADF, and maps
HTTP failures onto typed exceptions so the gateway can decide what is
retryable and what is terminal.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from ..config import AuthMode, Settings
from ..exceptions import (
    ConfigurationError,
    JiraAuthError,
    JiraError,
    JiraMalformedResponseError,
    JiraNotFoundError,
    JiraRateLimitError,
    JiraTimeoutError,
)
from ..models import JiraIssue, JiraSource
from .adf import normalize_text
from .base import JiraProvider

logger = logging.getLogger(__name__)

#: Only these are worth a second attempt; auth and 404 never are.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_FIELDS = (
    "summary,description,issuetype,status,priority,labels,components,"
    "parent,subtasks,issuelinks,comment"
)


class JiraRestProvider(JiraProvider):
    source = JiraSource.REST

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    def _base(self) -> str:
        if not self.settings.jira_url:
            raise ConfigurationError("JIRA_URL is not set")
        return f"{self.settings.jira_url}/rest/api/{self.settings.jira_api_version}"

    def _auth_kwargs(self) -> dict[str, Any]:
        settings = self.settings
        if settings.jira_auth_mode is AuthMode.BEARER:
            if not settings.jira_bearer_token:
                raise ConfigurationError("JIRA_BEARER_TOKEN is not set")
            return {"headers": {"Authorization": f"Bearer {settings.jira_bearer_token}"}}
        if not (settings.jira_email and settings.jira_api_token):
            raise ConfigurationError("JIRA_EMAIL and JIRA_API_TOKEN are required for basic auth")
        return {"auth": (settings.jira_email, settings.jira_api_token)}

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET with limited retries for transient failures only."""
        auth = self._auth_kwargs()
        headers = {"Accept": "application/json", **auth.pop("headers", {})}
        url = f"{self._base()}{path}"
        attempts = max(1, self.settings.pipeline_max_retries)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.settings.jira_timeout_seconds,
                    **auth,
                )
            except requests.Timeout:
                last_error = JiraTimeoutError(
                    f"Jira REST timed out after {self.settings.jira_timeout_seconds}s"
                )
                logger.warning("jira rest timeout (attempt %s/%s)", attempt, attempts)
            except requests.RequestException as exc:
                last_error = JiraError(
                    self.settings.redact(f"Jira REST connection failed: {exc}")
                )
                logger.warning("jira rest connection error (attempt %s/%s)", attempt, attempts)
            else:
                if response.status_code in (401, 403):
                    raise JiraAuthError(
                        "Jira rejected the credentials (HTTP "
                        f"{response.status_code}). Check JIRA_EMAIL/JIRA_API_TOKEN "
                        "and that the account can view this project."
                    )
                if response.status_code == 404:
                    raise JiraNotFoundError(
                        "Issue not found, or this account cannot see it (HTTP 404)."
                    )
                if response.status_code == 429:
                    last_error = JiraRateLimitError("Jira rate limited the request (HTTP 429)")
                elif response.status_code >= 400:
                    if response.status_code not in _RETRYABLE_STATUS:
                        raise JiraError(
                            self.settings.redact(
                                f"Jira REST returned HTTP {response.status_code}: "
                                f"{response.text[:300]}"
                            )
                        )
                    last_error = JiraError(f"Jira REST returned HTTP {response.status_code}")
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise JiraMalformedResponseError(
                            "Jira REST returned a body that is not JSON"
                        ) from exc

            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))  # exponential backoff, capped

        raise last_error or JiraError("Jira REST failed for an unknown reason")

    # ------------------------------------------------------------------
    def health_check(self) -> tuple[bool, str]:
        if not self.settings.rest_ready():
            return False, "REST is not configured (need JIRA_URL and credentials)"
        try:
            self._request("/myself")
        except JiraError as exc:
            return False, self.settings.redact(str(exc))
        return True, f"REST reachable at {self.settings.jira_url}"

    # ------------------------------------------------------------------
    def fetch_issue(self, issue_key: str) -> JiraIssue:
        params: dict[str, Any] = {"fields": _FIELDS}
        if self.settings.jira_acceptance_criteria_field:
            params["fields"] = f"{_FIELDS},{self.settings.jira_acceptance_criteria_field}"

        payload = self._request(f"/issue/{issue_key}", params=params)
        if not isinstance(payload, dict) or "fields" not in payload:
            raise JiraMalformedResponseError(
                f"Jira REST response for {issue_key} has no 'fields' object"
            )
        return build_issue_from_rest(payload, self.settings, JiraSource.REST)


def build_issue_from_rest(
    payload: dict[str, Any], settings: Settings, source: JiraSource
) -> JiraIssue:
    """Map a Jira REST issue payload onto :class:`JiraIssue`.

    Shared with the MCP provider, because a well behaved Jira MCP server
    returns the same issue shape.
    """
    fields = payload.get("fields") or {}
    key = payload.get("key") or ""
    if not key:
        raise JiraMalformedResponseError("Issue payload has no 'key'")

    def _name(container: Any) -> str:
        if isinstance(container, dict):
            return str(container.get("name") or container.get("displayName") or "")
        return ""

    links: list[str] = []
    for link in fields.get("issuelinks") or []:
        if not isinstance(link, dict):
            continue
        link_type = (link.get("type") or {}).get("name", "relates to")
        for direction in ("inwardIssue", "outwardIssue"):
            target = link.get(direction)
            if isinstance(target, dict) and target.get("key"):
                links.append(f"{link_type}: {target['key']}")

    comments: list[str] = []
    if settings.jira_include_comments:
        raw_comments = ((fields.get("comment") or {}).get("comments")) or []
        for comment in raw_comments[: settings.jira_max_comments]:
            author = _name(comment.get("author")) or "unknown"
            body = normalize_text(comment.get("body"))
            if body:
                comments.append(f"{author}: {body}")

    acceptance = ""
    if settings.jira_acceptance_criteria_field:
        acceptance = normalize_text(fields.get(settings.jira_acceptance_criteria_field))

    parent = fields.get("parent")
    base_url = settings.jira_url or ""

    return JiraIssue(
        key=key,
        summary=str(fields.get("summary") or ""),
        description=normalize_text(fields.get("description")),
        issue_type=_name(fields.get("issuetype")),
        status=_name(fields.get("status")),
        priority=_name(fields.get("priority")),
        labels=[str(x) for x in (fields.get("labels") or [])],
        components=[_name(c) for c in (fields.get("components") or []) if _name(c)],
        parent=(parent or {}).get("key") if isinstance(parent, dict) else None,
        subtasks=[
            str(s.get("key"))
            for s in (fields.get("subtasks") or [])
            if isinstance(s, dict) and s.get("key")
        ],
        linked_issues=links,
        acceptance_criteria_raw=acceptance,
        comments=comments,
        url=f"{base_url}/browse/{key}" if base_url else "",
        source=source,
        raw_fields={
            k: v
            for k, v in fields.items()
            if k in {"summary", "issuetype", "status", "priority", "labels"}
        },
    )
