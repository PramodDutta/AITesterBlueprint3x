"""Jira ticket -> test plan -> test cases -> a real browser run.

    python 012_Fetch_JIRA_QA_Orch.py VWO-49

Three stages with a human gate between each, because stage 3 drives a real
browser against a real site and that is not something to start by accident:

    1. FETCH    the ticket from Jira (REST v3)          -> you confirm
    2. PLAN     a test plan + test cases (typed output) -> you confirm
    3. EXECUTE  the automatable cases in Chromium       -> report

Pass --yes to skip both gates (CI). Pass --dry-run to stop after stage 2.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_deepseek import ChatDeepSeek

from playwright_tools import PLAYWRIGHT_TOOLS

load_dotenv()

# Jira credentials live in chapter 13's .env; fall back to this chapter's own.
for candidate in (Path(__file__).parents[3] / "chapter_13_CREW_AI_QA_Pipeline/.env",):
    if candidate.exists():
        load_dotenv(candidate, override=False)

# The .env calls the key DEEPSEEK_API, but the SDK looks for DEEPSEEK_API_KEY,
# so it has to be passed in explicitly. deepseek-flash is pinned on purpose:
# "deepseek-chat" is an alias and deepseek-v4-pro costs 4x more.
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")

# Stage 3 (tool calling) is happy with the default thinking mode.
llm = ChatDeepSeek(model=MODEL, api_key=os.environ["DEEPSEEK_API"], temperature=0)

# Stage 2 is NOT. response_format pins tool_choice to one function, and
# deepseek-flash rejects that while thinking is on:
#     400 "Thinking mode does not support this tool_choice"
# extra_body reaches the raw request body; model_kwargs does not.
planner_llm = ChatDeepSeek(
    model=MODEL,
    api_key=os.environ["DEEPSEEK_API"],
    temperature=0,
    extra_body={"thinking": {"type": "disabled"}},
)

# The app the generated cases actually run against.
TARGET_URL = os.getenv("TARGET_APP_URL", "https://app.thetestingacademy.com/playwright/ttacart/")
TARGET_USER = os.getenv("TARGET_APP_USER", "standard_user")
TARGET_PASS = os.getenv("TARGET_APP_PASS", "tta_secret")


# ---------------------------------------------------------------- stage 1
def _adf_to_text(node) -> str:
    """Jira v3 returns descriptions as ADF (nested JSON), not text."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    inner = _adf_to_text(node.get("content", []))
    return inner + "\n" if node.get("type") in ("paragraph", "heading", "listItem") else inner


def fetch_jira_issue(key: str) -> dict:
    """Fetch one issue over REST v3. Returns a dict with a 'source' field."""
    url = (os.getenv("JIRA_URL") or "").rstrip("/")
    email, token = os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN")
    if not (url and email and token):
        return _fixture(key, "no JIRA_URL / JIRA_EMAIL / JIRA_API_TOKEN found")

    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"{url}/rest/api/3/issue/{key}?fields=summary,description,status,issuetype,priority",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            f = json.load(resp)["fields"]
        return {
            "key": key,
            "summary": f.get("summary", ""),
            "description": _adf_to_text(f.get("description")).strip(),
            "status": (f.get("status") or {}).get("name", "?"),
            "issuetype": (f.get("issuetype") or {}).get("name", "?"),
            "priority": (f.get("priority") or {}).get("name", "?"),
            "source": f"Jira REST ({url})",
        }
    except urllib.error.HTTPError as exc:
        # 401 = bad/expired token. 404 on a real issue also means "not permitted".
        return _fixture(key, f"Jira returned HTTP {exc.code}. The API token is most "
                             f"likely expired - regenerate it at "
                             f"id.atlassian.com/manage-profile/security/api-tokens")
    except Exception as exc:
        return _fixture(key, f"{type(exc).__name__}: {exc}")


def _fixture(key: str, why: str) -> dict:
    """Offline fallback so a class demo still works with no live Jira."""
    path = Path(__file__).parent / "fixtures" / f"{key}.json"
    if not path.exists():
        print(f"\n[FATAL] Could not reach Jira ({why}) and no fixture at {path}")
        sys.exit(1)
    data = json.loads(path.read_text())
    data["source"] = f"OFFLINE FIXTURE ({path.name}) - live fetch failed: {why}"
    return data


# ---------------------------------------------------------------- stage 2
class TestCase(BaseModel):
    id: str = Field(description="e.g. TC-01")
    title: str
    priority: Literal["P0", "P1", "P2"]
    steps: list[str] = Field(description="Concrete UI steps against the target app")
    expected_result: str
    automatable: bool = Field(
        description="False when the ticket describes something absent from the target app")
    reason_if_not: str = Field(default="", description="Why it cannot be automated here")


class TestPlan(BaseModel):
    ticket_key: str
    scope: str = Field(description="2-3 sentences: what is tested and what is not")
    risks: list[str]
    test_cases: list[TestCase]


PLANNER_PROMPT = f"""You are a senior QA engineer writing a test plan from a Jira ticket.

The test cases will be executed by a browser agent against THIS app, which may be
a different product from the one the ticket describes:

    Target app: {TARGET_URL}
    Login:      {TARGET_USER} / {TARGET_PASS}

Rules:
1. Write 5-8 test cases covering the ticket's acceptance criteria.
2. Set automatable=true ONLY when every step can be performed on the target app
   above. If the ticket describes a feature the target app does not have (for
   example SSO or passkey buttons that are not on this login page), set
   automatable=false and say so in reason_if_not. Do NOT invent UI.
3. Steps must be concrete and clickable: name the field, button or text to check.
4. Never invent credentials beyond the ones given."""


# ---------------------------------------------------------------- stage 3
EXECUTOR_PROMPT = """You are an end-to-end automation testing agent driving a real
browser with Playwright.

Rules:
1. Call launch_browser FIRST.
2. Call snapshot_page on every new page instead of guessing selectors.
3. Prefer click_by_role and type_by_label over raw CSS.
4. Verify with assert_visible / assert_text_contains. Never assume a step worked.
5. If a case's element genuinely does not exist, report it FAILED with what you
   saw. Do not pretend it passed and do not substitute a different element.
6. Before closing, call get_console_errors and take_screenshot.
7. Report each test case id with PASS or FAIL, then a final summary line."""


def confirm(question: str, auto_yes: bool) -> bool:
    if auto_yes:
        print(f"{question} [auto-yes]")
        return True
    return input(f"{question} [y/N]: ").strip().lower() in ("y", "yes")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket", nargs="?", help="Jira key, e.g. VWO-49")
    ap.add_argument("--yes", action="store_true", help="skip confirmations")
    ap.add_argument("--dry-run", action="store_true", help="plan only, no browser")
    args = ap.parse_args()

    key = args.ticket or input("Jira ticket key (e.g. VWO-49): ").strip().upper()
    if not key:
        sys.exit("No ticket key given.")

    # ---- stage 1: fetch -------------------------------------------------
    print(f"\n{'='*70}\nSTAGE 1  Fetching {key}\n{'='*70}")
    issue = fetch_jira_issue(key)
    print(f"Source   : {issue['source']}")
    print(f"Key      : {issue['key']}  ({issue['issuetype']}, {issue['priority']}, {issue['status']})")
    print(f"Summary  : {issue['summary']}")
    desc = issue["description"]
    print(f"\n{desc[:1200]}{' ...[truncated]' if len(desc) > 1200 else ''}")

    if not confirm(f"\nGenerate a test plan from {key}?", args.yes):
        sys.exit("Stopped before planning.")

    # ---- stage 2: plan --------------------------------------------------
    print(f"\n{'='*70}\nSTAGE 2  Writing the test plan\n{'='*70}")
    planner = create_agent(model=planner_llm, system_prompt=PLANNER_PROMPT,
                           response_format=TestPlan)
    planned = await planner.ainvoke({"messages": [{"role": "user", "content":
        f"Ticket {issue['key']} ({issue['issuetype']}, priority {issue['priority']})\n"
        f"Summary: {issue['summary']}\n\nDescription:\n{desc}"}]})
    plan: TestPlan = planned["structured_response"]

    print(f"\nScope: {plan.scope}\n")
    for r in plan.risks:
        print(f"  risk: {r}")
    runnable = [tc for tc in plan.test_cases if tc.automatable]
    skipped = [tc for tc in plan.test_cases if not tc.automatable]
    print(f"\n{len(plan.test_cases)} case(s): {len(runnable)} automatable, {len(skipped)} not\n")
    for tc in plan.test_cases:
        mark = "RUN " if tc.automatable else "SKIP"
        print(f"[{mark}] {tc.id} ({tc.priority}) {tc.title}")
        for s in tc.steps:
            print(f"         - {s}")
        print(f"         expected: {tc.expected_result}")
        if not tc.automatable:
            print(f"         not automatable: {tc.reason_if_not}")

    out = Path(f"test_plan_{key}.json")
    out.write_text(plan.model_dump_json(indent=2))
    print(f"\nPlan written to {out}")

    if args.dry_run:
        print("--dry-run: stopping before the browser.")
        return
    if not runnable:
        print("Nothing automatable against the target app. Stopping.")
        return
    if not confirm(f"\nRun {len(runnable)} case(s) against {TARGET_URL} in a REAL browser?", args.yes):
        sys.exit("Stopped before execution.")

    # ---- stage 3: execute ----------------------------------------------
    print(f"\n{'='*70}\nSTAGE 3  Executing in Chromium\n{'='*70}")
    cases = "\n\n".join(
        f"{tc.id} ({tc.priority}) {tc.title}\n"
        + "\n".join(f"  {i}. {s}" for i, s in enumerate(tc.steps, 1))
        + f"\n  EXPECTED: {tc.expected_result}"
        for tc in runnable)
    task = (f"Execute these test cases from {key} against {TARGET_URL}\n"
            f"Login: {TARGET_USER} / {TARGET_PASS}\n\n{cases}\n\n"
            f"Report PASS or FAIL for each id, then a final summary.")

    executor = create_agent(model=llm, tools=PLAYWRIGHT_TOOLS, system_prompt=EXECUTOR_PROMPT)
    result = await executor.ainvoke({"messages": [{"role": "user", "content": task}]})

    print("\n----- steps taken -----")
    for msg in result["messages"]:
        if msg.type == "ai" and msg.tool_calls:
            for call in msg.tool_calls:
                print(f"-> {call['name']}({call['args']})")

    print(f"\n{'='*70}\nRESULT\n{'='*70}")
    print(result["messages"][-1].text)


if __name__ == "__main__":
    asyncio.run(main())
