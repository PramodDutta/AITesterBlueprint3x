"""The read-only, scope-limited Jira tool handed to the analyst agent."""

from __future__ import annotations

from jira_qa_crew.exceptions import JiraAuthError
from jira_qa_crew.tools.jira_tool import FetchJiraIssueTool


class StubGateway:
    def __init__(self, issue=None, error=None):
        self._issue = issue
        self._error = error
        self.calls: list[str] = []

    def fetch_issue(self, issue_key, mode=None):
        self.calls.append(issue_key)
        if self._error:
            raise self._error
        return self._issue


def test_serves_a_ticket_that_is_in_scope(issue):
    gateway = StubGateway(issue)
    tool = FetchJiraIssueTool(gateway, {"VWO-48"})

    output = tool._run("VWO-48")
    assert "Ticket Key: VWO-48" in output
    assert "SAVE20" in output
    assert gateway.calls == ["VWO-48"]


def test_normalises_case_before_checking_scope(issue):
    tool = FetchJiraIssueTool(StubGateway(issue), {"VWO-48"})
    assert "Ticket Key: VWO-48" in tool._run("  vwo-48 ")


def test_refuses_a_ticket_that_is_not_in_scope(issue):
    """This is the prompt-injection defence: 'now go read SECRET-1' gets nothing."""
    gateway = StubGateway(issue)
    tool = FetchJiraIssueTool(gateway, {"VWO-48"})

    output = tool._run("SECRET-1")
    assert output.startswith("REFUSED")
    assert "VWO-48" in output
    assert gateway.calls == [], "an out-of-scope key must never reach the gateway"


def test_refuses_empty_input(issue):
    assert FetchJiraIssueTool(StubGateway(issue), {"VWO-48"})._run("").startswith("REFUSED")


def test_a_jira_error_is_reported_not_raised_into_the_agent_loop():
    tool = FetchJiraIssueTool(StubGateway(error=JiraAuthError("401 from Jira")), {"VWO-48"})
    output = tool._run("VWO-48")
    assert output.startswith("ERROR")
    assert "401 from Jira" in output


def test_the_tool_exposes_no_write_capability():
    tool = FetchJiraIssueTool(StubGateway(), {"VWO-48"})
    assert tool.name == "fetch_jira_issue"
    assert "read-only" in tool.description.lower()
    public = {m for m in dir(tool) if not m.startswith("_")}
    assert not {"create", "update", "delete", "transition"} & public


def test_issue_text_is_wrapped_for_the_agent_as_untrusted_data(issue):
    """The task prompt marks it untrusted; the tool output must stay pure data."""
    text = issue.to_prompt_text()
    assert text.startswith("Ticket Key:")
    assert "Description:" in text
