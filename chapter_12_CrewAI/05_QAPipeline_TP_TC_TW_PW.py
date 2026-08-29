"""
CrewAI + Jira MCP: Auto-Generate Test Plans, Test Cases & Playwright Scripts
─────────────────────────────────────────────────────────────────────────────
Input  : A Jira ticket ID (e.g., VWO-48)
Output : test_plan.md, test_cases.md, playwright_tests.md

Pipeline:
  1. Jira Analyst       → fetches ticket via MCP - fallback to API, extracts requirements
  2. Test Plan Writer   → writes complete test plan (12 sections)
  3. Test Case Writer   → writes detailed test cases table
  4. Playwright Coder   → generates automation scripts
"""

import os
import datetime
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import MCPServerAdapter
from dotenv import load_dotenv
import requests
from mcp import StdioServerParameters

load_dotenv()

groq_llm = LLM(
    model=f"openai/{os.getenv('GROQ_MODEL')}",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url=os.getenv("GROQ_BASE_URL"),
)

def get_mcp_server_params() -> StdioServerParameters:
    """
    Configure the mcp-atlassian server connection.

    This tells CrewAI to launch `uvx mcp-atlassian` as a subprocess
    and communicate with it over STDIO (stdin/stdout).

    The MCP server handles:
    - Jira REST API authentication
    - ADF (Atlassian Document Format) → text conversion
    - Pagination for large result sets
    - Error handling and retries
    """
    # Accept either JIRA_USERNAME or JIRA_EMAIL (Atlassian Cloud uses email
    # as the username). Default JIRA_URL to the known workspace if missing.
    jira_username = os.getenv("JIRA_USERNAME") or os.getenv("JIRA_EMAIL", "")
    jira_url = os.getenv("JIRA_URL", "https://bugzz.atlassian.net")
    return StdioServerParameters(
        command="uvx",
        args=["mcp-atlassian"],
        env={
            # Pass Jira credentials to the MCP server process
            "JIRA_URL": jira_url,
            "JIRA_USERNAME": jira_username,
            "JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN", ""),
            # Inherit PATH so `uvx` can find Python/Node
            "PATH": os.environ.get("PATH", ""),
            # Pin python for the uvx-spawned tool
            "UV_PYTHON": "3.12",
        },
    )


TEST_PLAN_TEMPLATE = """
Follow this EXACT structure for the test plan:

### 1. TEST PLAN OVERVIEW
- Test Plan ID: TP-<JIRA_ID>
- Project Name, Feature/Module, Prepared By, Date, Version

### 2. OBJECTIVE
What this test plan validates based on the Jira ticket.

### 3. SCOPE
- 3.1 In Scope: features to test
- 3.2 Out of Scope: features NOT covered

### 4. TEST STRATEGY
- Testing Types (Functional, Regression, Smoke, Integration)
- Testing Approach (Manual / Automated / Both)
- Automation Tool: Playwright with TypeScript

### 5. TEST ENVIRONMENT
- Browsers, OS, Devices, Test Data Requirements

### 6. ENTRY CRITERIA
Conditions before testing begins.

### 7. EXIT CRITERIA
Conditions for testing to be complete.

### 8. TEST SCENARIOS (High-Level)
Summary of key scenarios to be tested.

### 9. RISK ASSESSMENT
| Risk | Likelihood | Impact | Mitigation |

### 10. DEFECT MANAGEMENT
Tool, severity levels, bug lifecycle.

### 11. TEST SCHEDULE
| Phase | Start Date | End Date | Owner |

### 12. SIGN-OFF
QA Lead, Dev Lead, Product Owner.
"""

# ══════════════════════════════════════════════════════════════════
#  AGENTS
# ══════════════════════════════════════════════════════════════════

def create_agents(mcp_tools: list, ticket_id: str):
    """Create all four agents with MCP tools and return them."""

    # ── Agent 1: Jira Ticket Analyst ──────────────────────────────
    jira_analyst = Agent(
        role="Senior QA Analyst",
        goal=(
            f"Fetch Jira ticket {ticket_id} using the available Jira tools, "
            "then extract ALL testable requirements, acceptance criteria, "
            "edge cases, and risks."
        ),
        backstory=(
            "You are a senior QA analyst with 15+ years of experience. "
            "You have access to Jira through MCP tools. "
            "Your job is to fetch the ticket details and perform "
            "a thorough analysis of what needs to be tested. "
            "You identify functional requirements, acceptance criteria, "
            "edge cases, boundary conditions, and risks. "
            "IMPORTANT: Use the Jira tools to fetch the ticket first, "
            "then analyze what you receive."
        ),
        tools=mcp_tools,  # ← MCP tools injected here!
        llm=groq_llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )
    # ── Agent 2: Test Plan Writer ─────────────────────────────────
    test_plan_writer = Agent(
        role="Test Plan Documentation Specialist",
        goal=(
            "Create a comprehensive, professional test plan document "
            "following the standard 12-section template."
        ),
        backstory=(
            f"You are a certified ISTQB test planning expert. "
            f"You write detailed test plans that teams can immediately execute. "
            f"You MUST follow this template:\n{TEST_PLAN_TEMPLATE}\n"
            f"Today's date is {datetime.date.today().strftime('%B %d, %Y')}. "
            f"Use professional markdown formatting."
        ),
        llm=groq_llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )
    # ── Agent 3: Test Case Writer ─────────────────────────────────
    test_case_writer = Agent(
        role="Test Case Design Specialist",
        goal=(
            "Design detailed, executable test cases covering positive, "
            "negative, edge, and boundary scenarios."
        ),
        backstory=(
            "You are a QA engineer who specializes in test case design. "
            "You write test cases that are so clear and detailed that "
            "anyone — even a junior tester — can execute them without "
            "asking questions. Each test case includes: TC ID, Title, "
            "Preconditions, Step-by-step instructions, Expected Results, "
            "Test Data, and Priority. You always cover: "
            "happy path, negative scenarios, edge cases, boundary values, "
            "UI validations, and error handling."
        ),
        llm=groq_llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )

    # ── Agent 4: Playwright Script Generator ──────────────────────
    playwright_coder = Agent(
        role="Playwright Automation Engineer",
        goal=(
            "Generate production-ready Playwright test scripts in "
            "TypeScript that automate the key test cases."
        ),
        backstory=(
            "You are a senior SDET who writes clean, maintainable "
            "Playwright tests in TypeScript. Your scripts follow best "
            "practices:\n"
            "- Page Object Model (POM) structure\n"
            "- Proper locator strategies (data-testid > CSS > XPath)\n"
            "- Meaningful test descriptions using test.describe/test()\n"
            "- Proper assertions with expect()\n"
            "- Setup/teardown with beforeEach/afterEach\n"
            "- Error handling and retry logic where needed\n"
            "- Comments explaining the test logic\n"
            "You generate COMPLETE, RUNNABLE TypeScript files. "
        ),
        llm=groq_llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )

    return jira_analyst, test_plan_writer, test_case_writer, playwright_coder

# ══════════════════════════════════════════════════════════════════
#  TASKS
# ══════════════════════════════════════════════════════════════════

def create_tasks(agents: tuple, ticket_id: str):
    """Create all four tasks and wire them together."""

    jira_analyst, test_plan_writer, test_case_writer, playwright_coder = agents

    # ── Task 1: Fetch & Analyze Jira Ticket ───────────────────────
    analysis_task = Task(
        description=(
            f"Fetch Jira ticket **{ticket_id}** using the available Jira MCP tools.\n\n"
            "Look for a tool that can get issue details — it might be called "
            "something like 'jira_get_issue' or 'get_issue' or similar.\n\n"
            f"Pass the ticket ID '{ticket_id}' to fetch the full details.\n\n"
            "After fetching, provide a DETAILED analysis:\n"
            "1. Summary of the ticket (what the feature/bug is about)\n"
            "2. ALL testable requirements extracted from the ticket\n"
            "3. Acceptance criteria (explicit and implicit)\n"
            "4. Potential edge cases and boundary conditions\n"
            "5. Risks and dependencies\n"
            "6. Suggested testing types (functional, regression, performance, etc.)\n\n"
            "Be thorough — all other agents depend on your analysis."
        ),
        expected_output=(
            "A detailed analysis report containing: ticket summary, "
            "testable requirements list, acceptance criteria, edge cases, "
            "risks, and recommended testing types."
        ),
        agent=jira_analyst,
    )

    # ── Task 2: Write Test Plan ───────────────────────────────────
    test_plan_task = Task(
        description=(
            f"Based on the Jira ticket analysis, create a COMPLETE test plan "
            f"for {ticket_id}.\n\n"
            "Follow the standard 12-section template EXACTLY. Include:\n"
            "- All 12 sections from the template\n"
            "- High-level test scenarios (NOT detailed test cases)\n"
            "- Realistic risk assessment with 3-5 risks\n"
            "- Proper test schedule with phases\n"
            f"- Use today's date: {datetime.date.today().strftime('%B %d, %Y')}\n\n"
            "Format everything in clean, professional markdown."
        ),
        expected_output=(
            "A complete, professional test plan document in markdown format "
            "following all 12 sections of the template."
        ),
        agent=test_plan_writer,
        context=[analysis_task],
        output_file="output/test_plan.md",
    )
    # ── Task 3: Write Detailed Test Cases ─────────────────────────
    test_cases_task = Task(
        description=(
            f"Based on the ticket analysis and test plan, create DETAILED "
            f"test cases for {ticket_id}.\n\n"
            "Generate at least 12-15 test cases in a markdown table:\n\n"
            "| TC ID | Title | Preconditions | Steps | Expected Result | "
            "Test Data | Priority |\n\n"
            "Cover these categories:\n"
            "- Happy path / positive scenarios (3-4 cases)\n"
            "- Negative scenarios / invalid inputs (3-4 cases)\n"
            "- Edge cases / boundary values (2-3 cases)\n"
            "- UI/UX validations (2-3 cases)\n"
            "- API validations if applicable (1-2 cases)\n"
            "- Performance/load considerations (1 case)\n\n"
            "Each test case MUST have:\n"
            "- Clear, numbered step-by-step instructions\n"
            "- Specific test data (not generic)\n"
            "- Precise expected results\n"
            "- Priority: P0 (Blocker), P1 (Critical), P2 (Major), P3 (Minor)"
        ),
        expected_output=(
            "A markdown document with 12-15 detailed test cases in table "
            "format, covering positive, negative, edge, UI, and API scenarios."
        ),
        agent=test_case_writer,
        context=[analysis_task, test_plan_task],
        output_file="output/test_cases.md",
    )

    # ── Task 4: Generate Playwright Scripts ───────────────────────
    playwright_task = Task(
        description=(
            f"Based on the test cases, generate Playwright automation "
            f"scripts in TypeScript for {ticket_id}.\n\n"
            "Create COMPLETE, RUNNABLE Playwright test files that:\n\n"
            "1. Use TypeScript with proper imports:\n"
            "   ```\n"
            "   import { test, expect } from '@playwright/test';\n"
            "   ```\n\n"
            "2. Follow Page Object Model structure:\n"
            "   - Create a page object class for the feature being tested\n"
            "   - Use data-testid selectors where possible\n"
            "   - Encapsulate page interactions in methods\n\n"
            "3. Group tests logically with test.describe():\n"
            "   - Positive scenarios group\n"
            "   - Negative scenarios group\n"
            "   - Edge cases group\n\n"
            "4. Include proper assertions:\n"
            "   - expect(locator).toBeVisible()\n"
            "   - expect(locator).toHaveText()\n"
            "   - expect(page).toHaveURL()\n\n"
            "5. Add helpful comments explaining each test's purpose\n\n"
            "6. Include a test.beforeEach() for common setup\n\n"
            "Generate the COMPLETE code — no placeholders or TODOs."
        ),
        expected_output=(
            "Complete Playwright TypeScript test files with page objects, "
            "test suites covering positive/negative/edge cases, and proper "
            "assertions. The code should be copy-paste ready."
        ),
        agent=playwright_coder,
        context=[analysis_task, test_cases_task],
        output_file="output/playwright_tests.md",
    )

    return analysis_task, test_plan_task, test_cases_task, playwright_task


# ══════════════════════════════════════════════════════════════════
#  CREW ORCHESTRATION
# ══════════════════════════════════════════════════════════════════

def run_crew(ticket_id: str):
    """
    Main function: Connect to Jira MCP → Create Crew → Run Pipeline.

    The MCPServerAdapter handles:
    1. Launching `uvx mcp-atlassian` as a subprocess
    2. Discovering all available Jira tools via MCP protocol
    3. Converting MCP tools to CrewAI-compatible BaseTool instances
    4. Cleaning up the subprocess when done (context manager)
    """
    print(f"\n📡 Target Jira Ticket: {ticket_id}")
    print("=" * 60)

    # Create output directory
    os.makedirs("output", exist_ok=True)

    # ── Connect to Jira MCP Server ────────────────────────────────
    server_params = get_mcp_server_params()

    print("🔌 Connecting to Jira MCP server (mcp-atlassian)...")

    with MCPServerAdapter(server_params, connect_timeout=60) as mcp_tools:
        # Show discovered tools
        tool_names = [t.name for t in mcp_tools]
        print(f"✅ Connected! Discovered {len(mcp_tools)} Jira tools:")
        for name in tool_names:
            print(f"   • {name}")
        print()

        # Groq free tier caps `gpt-oss-120b` at 8000 TPM. mcp-atlassian
        # exposes ~49 tools — every tool schema is added to the system
        # prompt and easily blows the budget. Filter to just what Agent 1
        # actually needs: read a Jira issue.
        ALLOWED = {"jira_get_issue", "jira_search"}
        filtered_tools = [t for t in mcp_tools if t.name in ALLOWED]
        print(f"🔧 Using {len(filtered_tools)} tool(s) to stay under TPM limit: "
              f"{[t.name for t in filtered_tools]}\n")

        # ── Create Agents (inject MCP tools into Agent 1) ─────────
        agents = create_agents(filtered_tools, ticket_id)

        # ── Create Tasks (wired sequentially) ─────────────────────
        tasks = create_tasks(agents, ticket_id)

        # ── Assemble the Crew ─────────────────────────────────────
        crew = Crew(
            agents=list(agents),
            tasks=list(tasks),
            process=Process.sequential,
            verbose=True,
            max_rpm=4,  # Rate limit for Groq free tier
        )

        # ── Run! ──────────────────────────────────────────────────
        print(f"\n🚀 Starting QA Pipeline for {ticket_id}")
        print("=" * 60)

        result = crew.kickoff()

        print("\n" + "=" * 60)
        print("🎉 QA PIPELINE COMPLETE!")
        print("=" * 60)
        print(f"\n📁 Generated files in ./output/:")
        print(f"   📋 test_plan.md        — Complete test plan")
        print(f"   🧪 test_cases.md       — Detailed test cases")
        print(f"   🎭 playwright_tests.md — Automation scripts")
        print()

        return result


