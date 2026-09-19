"""The full QA pipeline: Jira -> RAG -> plan -> cases -> browser -> Slack.

    python 013_FULL_E2E_Fetch_JIRA_Local_RAG_QA_Orch.py VWO-49

Six stages, three of them agents, with a human gate before anything touches a
real browser:

    1. FETCH    the Jira ticket (REST v3, offline fixture fallback)
    2. RETRIEVE the most similar existing test cases from a local RAG   <- gate
    3. PLAN     a test plan grounded in BOTH the ticket and the RAG hits (Groq)
    4. EXECUTE  the automatable cases in Chromium (DeepSeek)            <- gate
    5. REPORT   a reporter agent posts the verdict over a DUMMY Slack MCP

Two models on purpose: Groq writes the plan, DeepSeek drives the browser,
because DeepSeek is markedly better at long multi-step tool discipline (see
chapter 09 vs 10). Both are cheap.

    --yes       skip both gates (CI)
    --dry-run   stop after stage 3, no browser
    --no-rag    skip retrieval, to see what grounding is actually worth
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_deepseek import ChatDeepSeek
from langchain_groq import ChatGroq

from playwright_tools import PLAYWRIGHT_TOOLS
from slack_tools import SLACK_TOOLS, _DummySlackMCP, sent_messages
from tta_rag import TestCaseRAG, format_for_prompt

# 012 already solved Jira fetching; reuse it rather than copy it.
sys.path.insert(0, str(Path(__file__).parent))
_jira = __import__("012_Fetch_JIRA_QA_Orch")
fetch_jira_issue = _jira.fetch_jira_issue

load_dotenv()

TARGET_URL = os.getenv("TARGET_APP_URL", "https://app.thetestingacademy.com/playwright/ttacart/")
TARGET_USER = os.getenv("TARGET_APP_USER", "standard_user")
TARGET_PASS = os.getenv("TARGET_APP_PASS", "tta_secret")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#qa-automation")

# Planner: Groq. Executor + reporter: DeepSeek.
planner_llm = ChatGroq(model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"), temperature=0)
browser_llm = ChatDeepSeek(model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
                           api_key=os.environ["DEEPSEEK_API"], temperature=0)


# ------------------------------------------------------------------ schema
class TestCase(BaseModel):
    id: str = Field(description="e.g. TC-01")
    title: str
    priority: Literal["P0", "P1", "P2"]
    steps: list[str] = Field(description="Concrete UI steps against the target app")
    expected_result: str
    automatable: bool = Field(description="False if the target app lacks this UI")
    reason_if_not: str = ""
    rag_relation: Literal["duplicate", "extends", "new"] = Field(
        description="duplicate = an existing case already covers this exactly; "
                    "extends = it builds on one; new = nothing similar exists")
    related_existing_ids: list[str] = Field(
        default_factory=list, description="Ids from the retrieved library, e.g. TTA-002")


class TestPlan(BaseModel):
    ticket_key: str
    scope: str
    risks: list[str]
    coverage_gap: str = Field(description="What the ticket needs that the existing library misses")
    test_cases: list[TestCase]


PLANNER_PROMPT = f"""You are a senior QA engineer writing a test plan from a Jira ticket.

You are given the ticket AND the most similar test cases already in the team's
library. Use the library: do not re-write a case that already exists.

The cases will be executed by a browser agent against THIS app, which may be a
different product from the one the ticket describes:

    Target app: {TARGET_URL}
    Login:      {TARGET_USER} / {TARGET_PASS}

Rules:
1. Write 5-8 test cases covering the ticket's acceptance criteria.
2. For each case set rag_relation and related_existing_ids against the retrieved
   library. If an existing case already covers it exactly, mark it "duplicate"
   and still list it, so the reviewer can see the overlap rather than guess.
3. Set automatable=true ONLY when every step can be performed on the target app.
   If the ticket describes UI the target app does not have, set automatable=false
   and explain in reason_if_not. Never invent UI or credentials.
4. coverage_gap must name what the existing library does not yet cover.
5. Steps must be concrete and clickable."""

EXECUTOR_PROMPT = """You are an end-to-end automation testing agent driving a real
browser with Playwright.

Rules:
1. Call launch_browser FIRST.
2. Call snapshot_page on every new page instead of guessing selectors.
3. Prefer click_by_role and type_by_label over raw CSS.
4. Verify with assert_visible / assert_text_contains. Never assume a step worked.
5. If an element genuinely does not exist, report the case FAILED with what you
   saw. Do not pretend it passed and do not substitute a different element.
6. Before closing, call get_console_errors and take_screenshot.
7. Report each test case id with PASS or FAIL, then a final summary line."""

REPORTER_PROMPT = f"""You are a QA reporting agent. You are given the results of an
automated run and you post one summary to Slack.

Rules:
1. Post exactly one message, to {SLACK_CHANNEL}, using slack_post_message.
2. Slack mrkdwn only: *bold*, `code`, > quote. No markdown tables, they do not render.
3. Lead with the verdict and the Jira key. Then counts. Then any FAILED case with
   one line on why. Then the coverage gap. Keep it under 25 lines.
4. Report only what the results say. Never invent a number or a passing case."""


def confirm(question: str, auto_yes: bool) -> bool:
    if auto_yes:
        print(f"{question} [auto-yes]")
        return True
    return input(f"{question} [y/N]: ").strip().lower() in ("y", "yes")


def banner(n: int, title: str) -> None:
    print(f"\n{'='*72}\nSTAGE {n}  {title}\n{'='*72}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket", nargs="?")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-rag", action="store_true")
    ap.add_argument("-k", type=int, default=5, help="how many cases to retrieve")
    args = ap.parse_args()

    key = args.ticket or input("Jira ticket key (e.g. VWO-49): ").strip().upper()
    if not key:
        sys.exit("No ticket key given.")

    # ---- 1. Jira --------------------------------------------------------
    banner(1, f"Fetch {key} from Jira")
    issue = fetch_jira_issue(key)
    print(f"Source  : {issue['source']}")
    print(f"Key     : {issue['key']} ({issue['issuetype']}, {issue['priority']}, {issue['status']})")
    print(f"Summary : {issue['summary']}")
    desc = issue["description"]
    print(f"\n{desc[:700]}{' ...[truncated]' if len(desc) > 700 else ''}")

    # ---- 2. RAG ---------------------------------------------------------
    rag_block = "RAG retrieval was skipped for this run."
    if not args.no_rag:
        banner(2, "Retrieve similar existing test cases (local RAG)")
        rag = TestCaseRAG()
        query = f"{issue['summary']}. {desc[:600]}"
        hits = rag.search(query, k=args.k)
        print(f"corpus  : {len(rag.cases)} cases | backend: {rag.backend}\n")
        for score, c in hits:
            print(f"  {score:.3f}  {c['id']}  [{c['type']:7}] {c['title']}")
            print(f"           last run: {c['last_result']}, {c['status']}, tags: {', '.join(c['tags'][:5])}")
        rag_block = format_for_prompt(hits)

    if not confirm(f"\nWrite a test plan for {key} grounded in these results?", args.yes):
        sys.exit("Stopped before planning.")

    # ---- 3. Plan --------------------------------------------------------
    banner(3, "Write the test plan (Groq + RAG context)")
    planner = create_agent(model=planner_llm, system_prompt=PLANNER_PROMPT,
                           response_format=TestPlan)
    planned = await planner.ainvoke({"messages": [{"role": "user", "content":
        f"TICKET {issue['key']} ({issue['issuetype']}, priority {issue['priority']})\n"
        f"Summary: {issue['summary']}\n\nDescription:\n{desc}\n\n"
        f"--- EXISTING TEST CASES RETRIEVED FROM THE TEAM LIBRARY ---\n{rag_block}"}]})
    plan: TestPlan = planned["structured_response"]

    print(f"\nScope: {plan.scope}")
    print(f"\nCoverage gap: {plan.coverage_gap}\n")
    for r in plan.risks:
        print(f"  risk: {r}")
    runnable = [tc for tc in plan.test_cases if tc.automatable]
    print(f"\n{len(plan.test_cases)} case(s): {len(runnable)} automatable\n")
    for tc in plan.test_cases:
        rel = f"{tc.rag_relation}"
        if tc.related_existing_ids:
            rel += f" of {', '.join(tc.related_existing_ids)}"
        print(f"[{'RUN ' if tc.automatable else 'SKIP'}] {tc.id} ({tc.priority}) {tc.title}")
        print(f"         vs library: {rel}")
        if not tc.automatable:
            print(f"         not automatable: {tc.reason_if_not}")

    dupes = [tc for tc in plan.test_cases if tc.rag_relation == "duplicate"]
    if dupes:
        print(f"\n{len(dupes)} case(s) already covered by the library: "
              f"{', '.join(tc.id + ' -> ' + ','.join(tc.related_existing_ids) for tc in dupes)}")

    Path(f"test_plan_{key}.json").write_text(plan.model_dump_json(indent=2))
    print(f"\nPlan written to test_plan_{key}.json")

    if args.dry_run:
        print("--dry-run: stopping before the browser.")
        return
    if not runnable:
        print("Nothing automatable against the target app. Stopping.")
        return
    if not confirm(f"\nRun {len(runnable)} case(s) against {TARGET_URL} in a REAL browser?", args.yes):
        sys.exit("Stopped before execution.")

    # ---- 4. Execute -----------------------------------------------------
    banner(4, "Execute in Chromium (DeepSeek)")
    cases = "\n\n".join(
        f"{tc.id} ({tc.priority}) {tc.title}\n"
        + "\n".join(f"  {i}. {s}" for i, s in enumerate(tc.steps, 1))
        + f"\n  EXPECTED: {tc.expected_result}"
        for tc in runnable)
    executor = create_agent(model=browser_llm, tools=PLAYWRIGHT_TOOLS,
                            system_prompt=EXECUTOR_PROMPT)
    run = await executor.ainvoke({"messages": [{"role": "user", "content":
        f"Execute these test cases from {key} against {TARGET_URL}\n"
        f"Login: {TARGET_USER} / {TARGET_PASS}\n\n{cases}\n\n"
        f"Report PASS or FAIL for each id, then a final summary."}]})
    report = run["messages"][-1].text
    print(f"\n{'-'*72}\n{report}\n{'-'*72}")

    # ---- 5. Slack (dummy MCP) ------------------------------------------
    banner(5, "Report to Slack (DUMMY MCP - nothing is sent)")
    print(_DummySlackMCP.connect())
    reporter = create_agent(model=browser_llm, tools=SLACK_TOOLS,
                            system_prompt=REPORTER_PROMPT)
    await reporter.ainvoke({"messages": [{"role": "user", "content":
        f"Jira ticket: {key} - {issue['summary']}\n"
        f"Target app: {TARGET_URL}\n"
        f"Coverage gap identified while planning: {plan.coverage_gap}\n\n"
        f"--- RUN RESULTS ---\n{report}"}]})

    posted = sent_messages()
    print(f"\n{len(posted)} Slack call(s) simulated, 0 actually sent.")


if __name__ == "__main__":
    asyncio.run(main())
