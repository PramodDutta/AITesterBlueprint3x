"""Jira MCP provider (the primary path).

Design note - why ``MCPServerAdapter`` and not the ``mcps`` DSL:
the ``mcps`` DSL attaches an MCP server to an agent and lets the *model*
decide when to call it. Our fallback contract requires the MCP attempt, its
failure detection, and the switch to REST to be deterministic application
logic, so we drive a contained MCP client ourselves and hand the Jira Analyst
a single narrow tool. That also lets us enforce the read-only allow-list,
which an agent-attached server cannot guarantee.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config import MCPTransport, Settings
from ..exceptions import (
    JiraMalformedResponseError,
    JiraNotFoundError,
    MCPUnavailableError,
)
from ..models import JiraIssue, JiraSource
from .adf import normalize_text
from .base import JiraProvider
from .rest_provider import build_issue_from_rest

logger = logging.getLogger(__name__)

#: Tool names we are willing to call, in preference order, when the server's
#: issue-fetch tool is not pinned via JIRA_MCP_GET_ISSUE_TOOL.
_GET_ISSUE_TOOL_CANDIDATES = (
    "getJiraIssue",
    "jira_get_issue",
    "get_issue",
    "getIssue",
    "jira.getIssue",
    "atlassian_get_issue",
)

#: Hard read-only allow-list. Anything whose name suggests a mutation is
#: refused before the tool is ever exposed, regardless of configuration.
_WRITE_TOOL_MARKERS = (
    "create",
    "update",
    "edit",
    "delete",
    "remove",
    "transition",
    "assign",
    "comment",
    "worklog",
    "admin",
    "set",
    "move",
    "archive",
    "restore",
    "link",
)


def is_read_only_tool_name(name: str) -> bool:
    """True when a tool name contains no mutation verb.

    Conservative on purpose: a false negative costs us a tool we could have
    used, a false positive could let an agent modify Jira.
    """
    lowered = name.lower()
    return not any(marker in lowered for marker in _WRITE_TOOL_MARKERS)


class JiraMCPProvider(JiraProvider):
    source = JiraSource.MCP

    def __init__(self, settings: Settings, adapter_factory: Any | None = None):
        self.settings = settings
        # Injected in tests; defaults to the real crewai_tools adapter.
        self._adapter_factory = adapter_factory or _default_adapter_factory

    # ------------------------------------------------------------------
    def _server_params(self) -> dict[str, Any]:
        settings = self.settings
        transport = settings.jira_mcp_transport
        if transport is MCPTransport.STDIO:
            if not settings.jira_mcp_command:
                raise MCPUnavailableError("JIRA_MCP_COMMAND is not set for stdio transport")
            return {
                "command": settings.jira_mcp_command,
                "args": list(settings.jira_mcp_args),
                "env": {},
            }
        if not settings.jira_mcp_url:
            raise MCPUnavailableError(
                f"JIRA_MCP_URL is not set for {transport.value} transport"
            )
        params: dict[str, Any] = {
            "url": settings.jira_mcp_url,
            "transport": (
                "streamable-http"
                if transport is MCPTransport.STREAMABLE_HTTP
                else "sse"
            ),
        }
        if settings.jira_mcp_headers:
            params["headers"] = dict(settings.jira_mcp_headers)
        return params

    def _select_tool(self, tools: Any) -> Any:
        """Pick the issue-fetch tool, honouring config then the candidate list."""
        by_name = {getattr(t, "name", ""): t for t in tools}
        available = [n for n in by_name if n]
        if not available:
            raise MCPUnavailableError("The MCP server exposed no tools")

        allow = self.settings.jira_mcp_allowed_tools
        pinned = self.settings.jira_mcp_get_issue_tool

        if pinned:
            if pinned not in by_name:
                raise MCPUnavailableError(
                    f"Configured JIRA_MCP_GET_ISSUE_TOOL={pinned!r} is not exposed by "
                    f"the server. Available: {', '.join(sorted(available))}"
                )
            chosen = pinned
        else:
            chosen = next(
                (name for name in _GET_ISSUE_TOOL_CANDIDATES if name in by_name), ""
            )
            if not chosen:
                chosen = next(
                    (
                        name
                        for name in available
                        if "issue" in name.lower() and "get" in name.lower()
                    ),
                    "",
                )
            if not chosen:
                raise MCPUnavailableError(
                    "Could not identify an issue-fetch tool on the MCP server. Set "
                    "JIRA_MCP_GET_ISSUE_TOOL explicitly. Available: "
                    + ", ".join(sorted(available))
                )

        if allow and chosen not in allow:
            raise MCPUnavailableError(
                f"Tool {chosen!r} is not in JIRA_MCP_ALLOWED_TOOLS_JSON"
            )
        if not is_read_only_tool_name(chosen):
            raise MCPUnavailableError(
                f"Refusing to use MCP tool {chosen!r}: the name suggests it can "
                "modify Jira, and this application is strictly read-only."
            )
        return by_name[chosen]

    def _tool_arguments(self, issue_key: str) -> dict[str, Any]:
        args: dict[str, Any] = {self.settings.jira_mcp_issue_key_arg: issue_key}
        args.update(self.settings.jira_mcp_extra_args)
        return args

    # ------------------------------------------------------------------
    def health_check(self) -> tuple[bool, str]:
        if not self.settings.mcp_ready():
            return False, "MCP is not configured (need JIRA_MCP_URL or JIRA_MCP_COMMAND)"
        try:
            adapter = self._adapter_factory(
                self._server_params(), self.settings.jira_mcp_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - any startup failure is unavailability
            return False, self.settings.redact(f"MCP server did not start: {exc}")
        try:
            adapter.start()
            tool = self._select_tool(adapter.tools)
            return True, f"MCP reachable, issue tool: {getattr(tool, 'name', '?')}"
        except Exception as exc:  # noqa: BLE001
            return False, self.settings.redact(str(exc))
        finally:
            _safe_stop(adapter)

    # ------------------------------------------------------------------
    def fetch_issue(self, issue_key: str) -> JiraIssue:
        try:
            adapter = self._adapter_factory(
                self._server_params(), self.settings.jira_mcp_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001
            raise MCPUnavailableError(
                self.settings.redact(f"Could not create the MCP client: {exc}")
            ) from exc

        try:
            adapter.start()
        except Exception as exc:  # noqa: BLE001
            _safe_stop(adapter)
            raise MCPUnavailableError(
                self.settings.redact(f"MCP server did not start: {exc}")
            ) from exc

        try:
            tool = self._select_tool(adapter.tools)
            raw = tool.run(**self._tool_arguments(issue_key))
            return parse_mcp_issue_payload(raw, issue_key, self.settings)
        except (JiraMalformedResponseError, JiraNotFoundError, MCPUnavailableError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise MCPUnavailableError(
                self.settings.redact(f"MCP issue fetch failed: {exc}")
            ) from exc
        finally:
            _safe_stop(adapter)


def _default_adapter_factory(server_params: dict[str, Any], timeout: int) -> Any:
    from crewai_tools import MCPServerAdapter  # imported lazily: optional extra

    return MCPServerAdapter(server_params, connect_timeout=timeout)


def _safe_stop(adapter: Any) -> None:
    try:
        adapter.stop()
    except Exception:  # noqa: BLE001 - never let cleanup mask the real error
        logger.debug("MCP adapter stop() failed", exc_info=True)


def parse_mcp_issue_payload(raw: Any, issue_key: str, settings: Settings) -> JiraIssue:
    """Normalize whatever the MCP server returned into a :class:`JiraIssue`.

    Servers differ: some return the Jira REST issue verbatim, some wrap it in
    ``{"issues": {"nodes": [...]}}``, some return a JSON string, some return
    prose. Anything we cannot map to a real issue is a malformed response, not
    a silent empty result.
    """
    payload = raw
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise JiraMalformedResponseError(f"MCP returned an empty response for {issue_key}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Prose is not an issue. Refuse it rather than guessing.
            raise JiraMalformedResponseError(
                f"MCP returned non-JSON text for {issue_key}; cannot extract issue fields"
            ) from None

    payload = _unwrap_issue(payload)
    if not isinstance(payload, dict):
        raise JiraMalformedResponseError(
            f"MCP response for {issue_key} is not an issue object"
        )

    if "fields" in payload and isinstance(payload["fields"], dict):
        payload.setdefault("key", issue_key)
        return build_issue_from_rest(payload, settings, JiraSource.MCP)

    # Flat shape: {key, summary, description, ...}
    if not payload.get("key") and not payload.get("summary"):
        raise JiraMalformedResponseError(
            f"MCP response for {issue_key} has neither 'fields' nor 'summary'"
        )
    base_url = settings.jira_url or ""
    key = str(payload.get("key") or issue_key)
    return JiraIssue(
        key=key,
        summary=str(payload.get("summary") or ""),
        description=normalize_text(payload.get("description")),
        issue_type=str(payload.get("issueType") or payload.get("issue_type") or ""),
        status=str(payload.get("status") or ""),
        priority=str(payload.get("priority") or ""),
        labels=[str(x) for x in (payload.get("labels") or [])],
        components=[str(x) for x in (payload.get("components") or [])],
        parent=payload.get("parent"),
        subtasks=[str(x) for x in (payload.get("subtasks") or [])],
        linked_issues=[str(x) for x in (payload.get("linkedIssues") or [])],
        acceptance_criteria_raw=normalize_text(payload.get("acceptanceCriteria")),
        url=str(payload.get("url") or (f"{base_url}/browse/{key}" if base_url else "")),
        source=JiraSource.MCP,
    )


def _unwrap_issue(payload: Any) -> Any:
    """Dig the issue object out of the common MCP envelope shapes."""
    seen = 0
    while isinstance(payload, dict) and seen < 5:
        seen += 1
        if "fields" in payload or "summary" in payload:
            return payload
        for wrapper in ("issue", "result", "data", "content"):
            inner = payload.get(wrapper)
            if isinstance(inner, (dict, list)):
                payload = inner
                break
        else:
            nodes = (payload.get("issues") or {})
            if isinstance(nodes, dict) and isinstance(nodes.get("nodes"), list):
                payload = nodes["nodes"]
                break
            return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and ("fields" in item or "summary" in item):
                return item
        return payload[0] if payload else None
    return payload
