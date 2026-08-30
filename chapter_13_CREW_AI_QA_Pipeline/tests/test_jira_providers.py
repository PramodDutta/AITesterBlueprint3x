"""REST provider, MCP provider, and the gateway's fallback contract."""

from __future__ import annotations

import json

import pytest
import requests

from jira_qa_crew.config import AuthMode, IntegrationMode, Settings
from jira_qa_crew.exceptions import (
    AllProvidersFailedError,
    JiraAuthError,
    JiraError,
    JiraMalformedResponseError,
    JiraNotFoundError,
)
from jira_qa_crew.jira.gateway import JiraGateway
from jira_qa_crew.jira.mcp_provider import (
    JiraMCPProvider,
    is_read_only_tool_name,
    parse_mcp_issue_payload,
)
from jira_qa_crew.jira.rest_provider import JiraRestProvider
from jira_qa_crew.models import JiraIssue, JiraSource


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self._responses.pop(0) if self._responses else FakeResponse(500)
        if isinstance(item, Exception):
            raise item
        return item


class FakeTool:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self._result = result
        self._error = error
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._result


class FakeAdapter:
    def __init__(self, tools, start_error=None):
        self.tools = tools
        self._start_error = start_error
        self.started = False
        self.stopped = False

    def start(self):
        if self._start_error:
            raise self._start_error
        self.started = True

    def stop(self):
        self.stopped = True


def adapter_factory_for(adapter):
    def factory(server_params, timeout):
        return adapter

    return factory


class StubProvider:
    """Minimal JiraProvider stand-in for gateway tests."""

    def __init__(self, name, source, issue=None, error=None):
        self._name = name
        self.source = source
        self._issue = issue
        self._error = error
        self.calls = 0

    @property
    def name(self):
        return self._name

    def health_check(self):
        return (self._error is None, self._name)

    def fetch_issue(self, issue_key):
        self.calls += 1
        if self._error:
            raise self._error
        return self._issue


def make_issue(key="VWO-48", source=JiraSource.MCP):
    return JiraIssue(key=key, summary="A real summary", description="A real description",
                     source=source)


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------
def test_rest_parses_a_full_issue_including_adf(settings, rest_payload):
    session = FakeSession(FakeResponse(200, rest_payload))
    issue = JiraRestProvider(settings, session).fetch_issue("VWO-48")

    assert issue.key == "VWO-48"
    assert issue.source is JiraSource.REST
    assert issue.issue_type == "Bug"
    assert issue.status == "To Do"
    assert issue.priority == "Medium"
    assert issue.components == ["Shopping Cart"]
    assert issue.parent == "VWO-40"
    assert "relates to: VWO-49" in issue.linked_issues
    assert "SAVE20" in issue.description
    assert "Acceptance Criteria" in issue.description
    assert issue.url.endswith("/browse/VWO-48")


def test_rest_maps_401_to_auth_error_without_retrying(settings):
    session = FakeSession(FakeResponse(401, {}, "unauthorized"))
    with pytest.raises(JiraAuthError):
        JiraRestProvider(settings, session).fetch_issue("VWO-48")
    assert len(session.calls) == 1


def test_rest_maps_404_to_not_found(settings):
    session = FakeSession(FakeResponse(404, {}, "missing"))
    with pytest.raises(JiraNotFoundError):
        JiraRestProvider(settings, session).fetch_issue("VWO-48")


def test_rest_retries_a_transient_500_then_succeeds(settings, rest_payload):
    session = FakeSession(FakeResponse(503, {}, "busy"), FakeResponse(200, rest_payload))
    issue = JiraRestProvider(settings, session).fetch_issue("VWO-48")
    assert issue.key == "VWO-48"
    assert len(session.calls) == 2


def test_rest_timeout_becomes_a_typed_error(settings):
    session = FakeSession(requests.Timeout(), requests.Timeout())
    with pytest.raises(JiraError):
        JiraRestProvider(settings, session).fetch_issue("VWO-48")


def test_rest_rejects_a_body_without_fields(settings):
    session = FakeSession(FakeResponse(200, {"key": "VWO-48"}))
    with pytest.raises(JiraMalformedResponseError):
        JiraRestProvider(settings, session).fetch_issue("VWO-48")


def test_rest_bearer_auth_sets_the_header(monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_AUTH_MODE", "bearer")
    monkeypatch.setenv("JIRA_BEARER_TOKEN", "bearer-token-value-123")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    settings = Settings.load(env_file=os.devnull)
    assert settings.jira_auth_mode is AuthMode.BEARER

    session = FakeSession(FakeResponse(200, {"key": "X-1", "fields": {"summary": "s"}}))
    JiraRestProvider(settings, session).fetch_issue("X-1")
    _, kwargs = session.calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer bearer-token-value-123"
    assert "auth" not in kwargs


def test_rest_includes_comments_only_when_enabled(settings, rest_payload, monkeypatch):
    import os

    session = FakeSession(FakeResponse(200, rest_payload))
    assert JiraRestProvider(settings, session).fetch_issue("VWO-48").comments == []

    monkeypatch.setenv("JIRA_INCLUDE_COMMENTS", "true")
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token-abcdef123456")
    with_comments = Settings.load(env_file=os.devnull)
    session = FakeSession(FakeResponse(200, rest_payload))
    issue = JiraRestProvider(with_comments, session).fetch_issue("VWO-48")
    assert issue.comments and "Priya" in issue.comments[0]


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------
def test_mcp_success_path_returns_an_issue(settings, rest_payload):
    tool = FakeTool("getJiraIssue", result=json.dumps(rest_payload))
    adapter = FakeAdapter([tool])
    provider = JiraMCPProvider(settings, adapter_factory_for(adapter))

    issue = provider.fetch_issue("VWO-48")
    assert issue.source is JiraSource.MCP
    assert issue.summary.startswith("Shopping cart total")
    assert tool.calls == [{"issueIdOrKey": "VWO-48"}]
    assert adapter.stopped, "the MCP client must always be shut down"


def test_mcp_tool_name_and_argument_are_configurable(settings, rest_payload, monkeypatch):
    import os

    monkeypatch.setenv("JIRA_MCP_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("JIRA_MCP_GET_ISSUE_TOOL", "atlassian_fetch_one")
    monkeypatch.setenv("JIRA_MCP_ISSUE_KEY_ARG", "issue_key")
    monkeypatch.setenv("JIRA_MCP_EXTRA_ARGS_JSON", '{"cloudId": "abc-123"}')
    configured = Settings.load(env_file=os.devnull)

    tool = FakeTool("atlassian_fetch_one", result=rest_payload)
    provider = JiraMCPProvider(configured, adapter_factory_for(FakeAdapter([tool])))
    provider.fetch_issue("VWO-48")
    assert tool.calls == [{"issue_key": "VWO-48", "cloudId": "abc-123"}]


def test_mcp_refuses_a_write_tool_even_when_it_is_pinned(settings, monkeypatch):
    """Configuration must not be able to hand an agent a mutating Jira tool."""
    import os

    monkeypatch.setenv("JIRA_MCP_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("JIRA_MCP_GET_ISSUE_TOOL", "updateJiraIssue")
    pinned = Settings.load(env_file=os.devnull)

    tool = FakeTool("updateJiraIssue", result="{}")
    provider = JiraMCPProvider(pinned, adapter_factory_for(FakeAdapter([tool])))
    with pytest.raises(JiraError, match="read-only"):
        provider.fetch_issue("VWO-48")
    assert tool.calls == [], "a write tool must never be invoked"


def test_mcp_autodetect_never_selects_a_write_tool(settings):
    tool = FakeTool("updateJiraIssue", result="{}")
    provider = JiraMCPProvider(settings, adapter_factory_for(FakeAdapter([tool])))
    with pytest.raises(JiraError, match="Could not identify an issue-fetch tool"):
        provider.fetch_issue("VWO-48")
    assert tool.calls == []


def test_mcp_allow_list_blocks_an_unlisted_tool(settings, monkeypatch):
    import os

    monkeypatch.setenv("JIRA_MCP_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("JIRA_MCP_ALLOWED_TOOLS_JSON", '["only_this_one"]')
    restricted = Settings.load(env_file=os.devnull)

    tool = FakeTool("getJiraIssue", result="{}")
    provider = JiraMCPProvider(restricted, adapter_factory_for(FakeAdapter([tool])))
    with pytest.raises(JiraError, match="ALLOWED_TOOLS"):
        provider.fetch_issue("VWO-48")


@pytest.mark.parametrize(
    ("name", "read_only"),
    [
        ("getJiraIssue", True),
        ("jira_get_issue", True),
        ("search", True),
        ("createJiraIssue", False),
        ("transitionJiraIssue", False),
        ("addCommentToJiraIssue", False),
        ("deleteIssue", False),
        ("editJiraIssue", False),
    ],
)
def test_read_only_tool_name_detection(name, read_only):
    assert is_read_only_tool_name(name) is read_only


def test_mcp_unavailable_when_the_server_will_not_start(settings):
    adapter = FakeAdapter([], start_error=RuntimeError("connection refused"))
    provider = JiraMCPProvider(settings, adapter_factory_for(adapter))
    with pytest.raises(JiraError):
        provider.fetch_issue("VWO-48")


def test_mcp_prose_response_is_malformed_not_silently_accepted(settings):
    tool = FakeTool("getJiraIssue", result="I could not find that ticket, sorry.")
    provider = JiraMCPProvider(settings, adapter_factory_for(FakeAdapter([tool])))
    with pytest.raises(JiraMalformedResponseError):
        provider.fetch_issue("VWO-48")


def test_mcp_envelope_shapes_are_unwrapped(settings, rest_payload):
    envelopes = [
        rest_payload,
        {"issue": rest_payload},
        {"result": {"data": rest_payload}},
        {"issues": {"nodes": [rest_payload]}},
        [rest_payload],
    ]
    for envelope in envelopes:
        issue = parse_mcp_issue_payload(envelope, "VWO-48", settings)
        assert issue.key == "VWO-48"
        assert issue.source is JiraSource.MCP


def test_mcp_flat_shape_is_supported(settings):
    flat = {"key": "VWO-49", "summary": "flat summary", "description": "flat description"}
    issue = parse_mcp_issue_payload(flat, "VWO-49", settings)
    assert issue.summary == "flat summary"


# --------------------------------------------------------------------------
# Gateway
# --------------------------------------------------------------------------
def test_auto_mode_prefers_mcp(settings):
    mcp = StubProvider("mcp", JiraSource.MCP, issue=make_issue())
    rest = StubProvider("rest", JiraSource.REST, issue=make_issue(source=JiraSource.REST))
    issue = JiraGateway(settings, mcp, rest).fetch_issue("VWO-48")
    assert issue.source is JiraSource.MCP
    assert rest.calls == 0


def test_auto_mode_falls_back_to_rest_when_mcp_fails(settings):
    mcp = StubProvider("mcp", JiraSource.MCP, error=JiraError("mcp down"))
    rest = StubProvider("rest", JiraSource.REST, issue=make_issue(source=JiraSource.REST))
    issue = JiraGateway(settings, mcp, rest).fetch_issue("VWO-48")
    assert issue.source is JiraSource.REST
    assert mcp.calls == 1 and rest.calls == 1


def test_mcp_only_mode_never_touches_rest(settings):
    mcp = StubProvider("mcp", JiraSource.MCP, error=JiraError("mcp down"))
    rest = StubProvider("rest", JiraSource.REST, issue=make_issue())
    with pytest.raises(AllProvidersFailedError):
        JiraGateway(settings, mcp, rest).fetch_issue("VWO-48", IntegrationMode.MCP)
    assert rest.calls == 0


def test_rest_only_mode_never_touches_mcp(settings):
    mcp = StubProvider("mcp", JiraSource.MCP, issue=make_issue())
    rest = StubProvider("rest", JiraSource.REST, issue=make_issue(source=JiraSource.REST))
    issue = JiraGateway(settings, mcp, rest).fetch_issue("VWO-48", IntegrationMode.REST)
    assert issue.source is JiraSource.REST
    assert mcp.calls == 0


def test_both_failed_reports_each_provider_error(settings):
    mcp = StubProvider("mcp", JiraSource.MCP, error=JiraError("mcp exploded"))
    rest = StubProvider("rest", JiraSource.REST, error=JiraAuthError("rest 401"))
    with pytest.raises(AllProvidersFailedError) as exc:
        JiraGateway(settings, mcp, rest).fetch_issue("VWO-48")
    assert set(exc.value.provider_errors) == {"mcp", "rest"}
    assert "mcp exploded" in exc.value.provider_errors["mcp"]


def test_an_empty_issue_counts_as_a_failure(settings):
    empty = JiraIssue(key="VWO-48", summary="", description="")
    mcp = StubProvider("mcp", JiraSource.MCP, issue=empty)
    rest = StubProvider("rest", JiraSource.REST, issue=make_issue(source=JiraSource.REST))
    issue = JiraGateway(settings, mcp, rest).fetch_issue("VWO-48")
    assert issue.source is JiraSource.REST


def test_live_failure_never_silently_falls_back_to_demo_fixtures(settings, fixtures_dir):
    """The critical anti-lying test: a failed live call must raise, not fake it."""
    assert settings.demo_mode is False
    mcp = StubProvider("mcp", JiraSource.MCP, error=JiraError("down"))
    rest = StubProvider("rest", JiraSource.REST, error=JiraError("down"))
    gateway = JiraGateway(settings, mcp, rest, fixtures_dir=fixtures_dir)

    with pytest.raises(AllProvidersFailedError):
        gateway.fetch_issue("VWO-48")  # a VWO-48 fixture exists and must NOT be used


def test_demo_mode_is_opt_in_and_labelled(monkeypatch, tmp_path, fixtures_dir):
    import os

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    demo_settings = Settings.load(env_file=os.devnull)

    gateway = JiraGateway(demo_settings, fixtures_dir=fixtures_dir)
    issue = gateway.fetch_issue("VWO-48")
    assert issue.source is JiraSource.DEMO_FIXTURE
    assert issue.summary.startswith("Shopping cart total")


def test_demo_mode_rejects_a_ticket_with_no_fixture(monkeypatch, tmp_path, fixtures_dir):
    import os

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    gateway = JiraGateway(Settings.load(env_file=os.devnull), fixtures_dir=fixtures_dir)
    with pytest.raises(AllProvidersFailedError):
        gateway.fetch_issue("NOPE-1")
