"""A DUMMY Slack MCP connection.

Nothing here talks to Slack. It mimics the shape of a real MCP client so the
reporter agent is written exactly as it would be against a live server, then
prints the payload instead of sending it. When you wire up the real thing, the
agent code does not change: only _DummySlackMCP.call_tool is replaced by a
genuine MCP session.

Run this file directly to see the simulated handshake.
"""

import json
import os
from datetime import datetime, timezone

from langchain.tools import tool

SLACK_MCP_URL = os.getenv("SLACK_MCP_URL", "stdio://npx -y @modelcontextprotocol/server-slack")
DEFAULT_CHANNEL = os.getenv("SLACK_CHANNEL", "#qa-automation")

_SENT: list[dict] = []          # everything the agent "posted", for assertions


class _DummySlackMCP:
    """Stands in for an MCP client session. Same method names, no network."""

    connected = False

    @classmethod
    def connect(cls) -> str:
        cls.connected = True
        return (f"[DUMMY MCP] connected to {SLACK_MCP_URL}\n"
                f"[DUMMY MCP] server advertises: "
                f"{', '.join(t['name'] for t in cls.list_tools())}\n"
                f"[DUMMY MCP] NOTE: no credentials configured, nothing will actually be sent.")

    @staticmethod
    def list_tools() -> list[dict]:
        return [
            {"name": "slack_post_message", "description": "Post a message to a channel"},
            {"name": "slack_upload_file", "description": "Upload a file to a channel"},
            {"name": "slack_list_channels", "description": "List channels the bot can post to"},
        ]

    @classmethod
    def call_tool(cls, name: str, arguments: dict) -> dict:
        """The seam. Swap this body for a real MCP call and everything else holds."""
        if not cls.connected:
            cls.connect()
        ts = f"{datetime.now(timezone.utc).timestamp():.6f}"
        print(f"\n{'-'*66}\n[DUMMY SLACK MCP] call_tool({name})\n{'-'*66}")
        print(json.dumps(arguments, indent=2)[:2000])
        print(f"{'-'*66}\n[DUMMY SLACK MCP] not sent - dummy connection\n")
        record = {"tool": name, "arguments": arguments, "ts": ts}
        _SENT.append(record)
        return {"ok": True, "ts": ts, "simulated": True,
                "permalink": f"https://example.slack.com/archives/C0DUMMY/p{ts.replace('.', '')}"}


@tool
def slack_list_channels() -> str:
    """List the Slack channels the bot may post QA reports to."""
    _DummySlackMCP.connect()
    return "Channels: #qa-automation (default), #releases, #build-failures"


@tool
def slack_post_message(channel: str, text: str) -> str:
    """Post a QA run report to a Slack channel.

    Use Slack mrkdwn: *bold*, `code`, and > for quotes. Keep it under 30 lines,
    lead with the verdict, and always name the Jira ticket.
    """
    res = _DummySlackMCP.call_tool("slack_post_message", {"channel": channel, "text": text})
    return f"Posted to {channel} (simulated, ts={res['ts']}). Permalink: {res['permalink']}"


@tool
def slack_upload_file(channel: str, file_path: str, title: str = "") -> str:
    """Attach an artifact such as a screenshot or the test plan JSON to a channel."""
    exists = os.path.exists(file_path)
    res = _DummySlackMCP.call_tool("slack_upload_file",
                                   {"channel": channel, "file_path": file_path,
                                    "title": title, "file_exists_locally": exists})
    if not exists:
        return f"Refused: {file_path} does not exist on disk, nothing uploaded."
    return f"Uploaded {os.path.basename(file_path)} to {channel} (simulated, ts={res['ts']})."


SLACK_TOOLS = [slack_list_channels, slack_post_message, slack_upload_file]


def sent_messages() -> list[dict]:
    return list(_SENT)


if __name__ == "__main__":
    print(_DummySlackMCP.connect())
    print(slack_post_message.invoke({"channel": "#qa-automation",
                                     "text": "*VWO-49* smoke run: 4/4 PASS"}))
