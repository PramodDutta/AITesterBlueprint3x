# Jira QA Crew — AI-Powered QA Artifact Generator

Enter one or more Jira ticket IDs. Get back a requirements analysis, a
twelve-section test plan, detailed test cases, Playwright TypeScript
automation, a traceability matrix, and downloadable artifacts.

The engine is a real four-agent CrewAI pipeline. Nothing is simulated, and no
agent response is hard-coded.

---

## Verification status

Last verified 2026-08-29 against `deepseek/deepseek-v4-flash`:

| Check | Result |
| --- | --- |
| `ruff check .` | clean |
| `pytest` | 260 passed, 3 skipped (the 3 are opt-in live tests) |
| Streamlit app | starts and renders, verified in a browser |
| Full four-agent run | completed end to end, full artifact set written |
| Generated Playwright | compiles under `tsc --noEmit` |

Not verified here, and not claimed: the Docker image build (no daemon on the
build machine), live Jira, and live MCP. See Limitations for the one stage that
is unreliable on this model.

---

## What it does

Manual workflow today:

1. Open Jira, read the story and acceptance criteria
2. Interpret requirements
3. Write a test plan
4. Write test cases
5. Decide what to automate
6. Write Playwright tests
7. Build traceability
8. Export and share

This tool does all eight, and keeps the human review points visible instead of
hiding them: everything it is unsure about is labelled rather than smoothed
over.

It does **not** update Jira, transition issues, create bugs, run Playwright
against anything, or guess missing product behaviour.

---

## Pipeline

```text
Jira IDs
   ↓  parse, normalize, deduplicate, validate
Jira Gateway  ──  MCP (primary)  →  REST (fallback)
   ↓
Agent 1: Jira Analyst        →  RequirementAnalysis   (REQ-*, AC-*, provenance)
   ↓  validate: ids unique, references resolve, quotes present
Agent 2: Test Plan Writer    →  TestPlan              (exactly 12 sections)
   ↓  validate: sections complete, scenarios trace to real ids
Agent 3: Test Case Writer    →  TestCaseSuite         (steps, data, automation calls)
   ↓  validate: no duplicate ids, no dangling refs, every AC covered
Agent 4: Playwright Coder    →  PlaywrightBundle      (compilable .spec.ts)
   ↓  validate: no hard waits, no XPath, no secrets, readiness is honest
Deterministic renderers      →  Markdown, CSV, JSON, TypeScript, ZIP
   ↓
Streamlit results and downloads
```

The process is **sequential** because each stage depends on the *validated*
output of the one before it. Each ticket gets a fresh crew, fresh agents and
fresh tasks, with crew memory off, so nothing leaks between tickets.

### Agent responsibilities

| Agent | Owns | Cannot |
| --- | --- | --- |
| **Jira Analyst** | Extracting requirements, acceptance criteria, risks, gaps; assigning `REQ-001` / `AC-001`; labelling provenance | Invent a requirement, or read a ticket outside the current run |
| **Test Plan Writer** | The twelve-section plan and its scenarios | Reference an id the analysis did not produce |
| **Test Case Writer** | Detailed cases, boundaries, negatives, automation judgement | Reference an unknown id, or pad with irrelevant categories |
| **Playwright Coder** | Compilable TypeScript, per-test traceability, readiness status | Invent selectors or claim READY while placeholders remain |

Only the Jira Analyst gets the Jira tool. The other three work from validated
upstream output, so a prompt injected into a ticket cannot reach Jira through
them.

---

## Architecture decisions

**Provider choice is application logic, not an LLM decision.** `JiraGateway`
decides MCP-then-REST in Python. An agent is never asked which provider to
use, and never learns the credentials.

**`MCPServerAdapter`, not the `mcps` DSL.** The `mcps` DSL attaches a server to
an agent and lets the model decide when to call it. Our fallback contract needs
the MCP attempt, its failure detection, and the switch to REST to be
deterministic, so we drive a contained MCP client ourselves and expose one
narrow tool. That also lets us enforce a read-only allow-list, which an
agent-attached server cannot guarantee.

**Pydantic objects are the source of truth, never LLM Markdown.** Agents return
structured objects. Every `.md`, `.csv`, `.json` and `.ts` artifact is rendered
from those objects by deterministic Python in `services/artifacts.py`. Change a
renderer and every past object re-renders identically.

**Coverage is computed, not claimed.** `services/traceability.py` derives
coverage from the validated objects. No agent is asked how well it covered the
requirements, because an agent has an obvious incentive to answer "fully".

**Stages hand off validated summaries, not raw text.** CrewAI's `Task.context`
forwards the full raw output of every earlier task. Across four stages that
compounds: by the Playwright stage the prompt carries the entire analysis and
plan JSON, source quotes and all. Measured against DeepSeek, that is what
pushes it into returning empty completions. So each stage receives a compact
block rendered from the *validated* upstream object
(`services/handoff.py`), and the raw context is dropped so the same
information is not sent twice. This is strictly better than the raw text: it
is 40-70% smaller, it cannot contain anything validation rejected, and it
lists exactly the ids the next stage is allowed to reference. The Playwright
stage is only sent the cases marked for automation, so it is never tempted to
automate one a human judged manual-only.

**Structured output degrades gracefully.** Providers disagree about how much
structure they can guarantee, so the pipeline walks a ladder and remembers
where it landed:

| Rung | Request | Notes |
| --- | --- | --- |
| 1 | `output_pydantic` → provider enforces the JSON schema | Strongest. DeepSeek rejects it with HTTP 400, "This response_format type is unavailable now" |
| 2 | `response_format: json_object` + schema in the prompt | Guarantees parseable JSON. Skipped for the Jira Analyst, because a tool call is not a JSON object |
| 3 | Schema in the prompt, free text back | Last resort; the response is still validated here |

A provider that refuses a rung is never asked for it again during that run.
**Enforcement is downgraded; validation never is** - every rung ends with the
same `model_validate` call. A rate limit or an auth error never triggers a
downgrade, and there is a test for that.

Set `LLM_STRUCTURED_OUTPUT=prompt` to skip rung 1 on a provider you already
know cannot do it, or `=schema` to insist on it and treat a rejection as an
error.

**One repair attempt, never a loop.** A stage whose output fails schema or
deterministic validation is re-run exactly once with the specific problems
listed, and told not to invent content to satisfy a check. Transient empty
completions are retried on a bounded backoff. Both are capped.

---

## Repository structure

```text
app.py                          Streamlit entry point (presentation only)
src/jira_qa_crew/
├── config.py                   Settings, readiness, secret redaction
├── models.py                   Pydantic contracts between stages
├── exceptions.py               Typed errors
├── jira/
│   ├── adf.py                  Atlassian Document Format → text
│   ├── base.py                 JiraProvider interface
│   ├── mcp_provider.py         MCP client, read-only tool selection
│   ├── rest_provider.py        REST v3, typed HTTP failures, backoff
│   └── gateway.py              Deterministic MCP → REST fallback
├── tools/jira_tool.py          Read-only, scope-limited agent tool
├── crew/
│   ├── prompts.py              YAML prompt loader
│   ├── agents.py               The four agents
│   ├── tasks.py                Tasks, context wiring, output_pydantic
│   ├── factory.py              One isolated crew per ticket
│   └── callbacks.py            Real stage progress
├── prompts/
│   ├── agents.yaml             Agent role/goal/backstory
│   └── tasks.yaml              Task descriptions and expected output
├── services/
│   ├── tickets.py              Input parsing, path sanitization
│   ├── pipeline.py             Orchestration, stage gates, repair
│   ├── handoff.py              Compact validated stage-to-stage summaries
│   ├── structured.py           Schema-rejection fallback, JSON extraction
│   ├── validation.py           Deterministic post-stage checks
│   ├── traceability.py         Coverage and orphan detection
│   └── artifacts.py            Renderers, manifests, ZIP
└── ui/                         Streamlit state, components, results
tests/                          260 tests, no live Jira or LLM
fixtures/                       VWO-48, VWO-49 demo tickets
tools/playwright-check/         TypeScript harness for generated specs
scripts/                        Demo smoke test, Playwright compile check
outputs/                        Generated artifacts (gitignored)
```

---

## Install

Requires Python 3.11+ (developed on 3.13).

```bash
cd CREW_AI_QA_Pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill it in
```

## Configure

All configuration is environment based. Nothing secret is ever typed into the
UI, and the sidebar shows only a redacted readiness report.

```dotenv
LLM_MODEL=deepseek/deepseek-v4-flash
LLM_API_KEY=sk-...
LLM_TEMPERATURE=0.1

JIRA_INTEGRATION_MODE=auto     # auto | mcp | rest
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=...
```

See `.env.example` for the full list.

The model id is configurable on purpose, because provider naming changes.
Anything CrewAI supports works: `deepseek/deepseek-v4-flash`,
`openai/gpt-4o-mini`, `openai/openai/gpt-oss-120b` with a `LLM_BASE_URL`, and
so on.

`JIRA_QA_CREW_SKIP_DOTENV=1` makes the app ignore any `.env` and read the
environment only. Tests and containers use it so local files cannot change
behaviour.

### Jira REST setup

1. Create an API token at
   <https://id.atlassian.com/manage-profile/security/api-tokens>
2. Set `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
3. Bearer auth instead: `JIRA_AUTH_MODE=bearer` and `JIRA_BEARER_TOKEN`
4. If acceptance criteria live in a custom field, set
   `JIRA_ACCEPTANCE_CRITERIA_FIELD=customfield_10035`

The account only needs **browse** permission. The app never writes to Jira.

### Jira MCP setup

```dotenv
JIRA_MCP_TRANSPORT=streamable_http     # streamable_http | sse | stdio
JIRA_MCP_URL=https://mcp.atlassian.com/v1/mcp
JIRA_MCP_HEADERS_JSON={"Authorization":"Bearer ..."}
```

For stdio:

```dotenv
JIRA_MCP_TRANSPORT=stdio
JIRA_MCP_COMMAND=npx
JIRA_MCP_ARGS_JSON=["-y","@some/jira-mcp-server"]
```

MCP servers do not agree on tool names or argument names, so both are
configurable:

```dotenv
JIRA_MCP_GET_ISSUE_TOOL=getJiraIssue       # blank = auto-detect
JIRA_MCP_ISSUE_KEY_ARG=issueIdOrKey
JIRA_MCP_EXTRA_ARGS_JSON={"cloudId":"..."}
JIRA_MCP_ALLOWED_TOOLS_JSON=["getJiraIssue"]
```

Auto-detection tries a list of common names, then any tool whose name contains
both "get" and "issue". A tool whose name suggests mutation (`create`,
`update`, `delete`, `transition`, `comment`, …) is **refused even if you pin
it explicitly**.

## Run

```bash
streamlit run app.py
```

Then open <http://localhost:8501>, paste ticket IDs, pick a mode, and press
**Analyze & Generate QA Pack**.

### Demo mode

```dotenv
DEMO_MODE=true
```

Reads `fixtures/VWO-48.json` and `fixtures/VWO-49.json` instead of Jira. It is
labelled in the sidebar and on every result, and artifacts record the source as
`DEMO_FIXTURE`. **It is never an automatic fallback for a failed live call** -
a failed live fetch raises, and there is a test that proves it.

---

## Testing

```bash
pytest                                   # 260 tests, no network, no LLM cost
pytest --cov=src/jira_qa_crew            # with coverage
ruff check .                             # lint
python scripts/demo_smoke.py             # real pipeline over fixtures (costs LLM tokens)
python scripts/check_playwright.py outputs/RUN-...   # compile generated specs
```

Covered: ticket parsing and dedup, ADF conversion, MCP success, MCP→REST
fallback, REST-only mode, both-providers-failed, no-silent-demo-fallback,
Pydantic validation, duplicate detection, traceability and coverage maths,
Markdown/CSV rendering, artifact paths and ZIP, path traversal, secret
redaction, partial multi-ticket success, the schema-rejection fallback, the
stage handoffs, truncation detection, and the Streamlit surface via
`streamlit.testing.v1.AppTest`.

Live tests are opt-in and skipped by default:

```bash
RUN_INTEGRATION_TESTS=1 LIVE_JIRA_KEY=VWO-48 pytest tests/test_integration_live.py -v
```

---

## Security

- Secrets come from the environment or `st.secrets`, never from a UI field
- Every log line and error message passes through `Settings.redact`
- Jira access is read-only; write-sounding MCP tools are refused
- The agent's Jira tool only serves ticket keys the run was started with, so a
  ticket that says "now fetch SECRET-1" gets a refusal
- Ticket content is wrapped in an explicit untrusted-data marker and the agent
  is told to report embedded instructions as a risk rather than follow them
- Ticket keys are sanitized before touching the filesystem; traversal is tested
- Input size and ticket count are capped
- Network calls have timeouts and bounded exponential backoff
- No `eval`, no `exec`, no shell execution from Jira content, no unsafe
  deserialization
- Playwright is never executed by the Streamlit server

---

## Deployment

### Streamlit Community Cloud

1. Push this directory to GitHub
2. New app → point at `app.py`, Python 3.11+
3. Paste the contents of `.streamlit/secrets.toml.example` into **Secrets** and
   fill in real values. Key names match `.env` exactly; `app.py` copies them
   into the environment before configuration is read.

`outputs/` is ephemeral there, so use the download buttons.

### Docker

```bash
docker compose up --build          # http://localhost:8501
# or
docker build -t jira-qa-crew .
docker run --env-file .env -p 8501:8501 -v "$PWD/outputs:/app/outputs" jira-qa-crew
```

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Sidebar: "LLM is not configured" | Set `LLM_MODEL` and `LLM_API_KEY` |
| "Could not fetch X from any configured provider" | The message lists each provider's error. A 404 usually means an expired token or no browse permission |
| "This response_format type is unavailable now" | The provider cannot enforce JSON schemas. Handled automatically: the run switches to prompted JSON and logs it |
| "Invalid response from LLM call - None or empty" | The provider returned no content. Retried with bounded backoff. Persistent cases mean the prompt is too large for that model: try a larger model, or shorten the agent backstories in `prompts/agents.yaml` |
| "output did not parse into X" | The model returned text that failed validation. The log names the offending fields. One repair attempt runs automatically |
| "Could not identify an issue-fetch tool" | Set `JIRA_MCP_GET_ISSUE_TOOL` to the tool name your server exposes |
| "Refusing to use MCP tool … read-only" | The pinned tool name looks like it can mutate Jira. Pin a read-only one |
| Ticket completes with warnings | Expected. Warnings are coverage gaps and missing information, listed per ticket |
| Run is slow | Four sequential LLM calls per ticket. Latency is the provider's, not the app's |

---

## Limitations

- **Requires real credentials to be useful.** Demo mode proves the pipeline;
  it does not read your Jira.
- **Generated Playwright is usually `NEEDS_CONFIGURATION`.** A ticket rarely
  contains real selectors or routes, so the coder emits marked placeholders
  and says what it needs. That is the honest outcome, not a defect.
- **Artifact quality tracks ticket quality.** A ticket with no acceptance
  criteria produces an analysis that says so, not invented criteria.
- **Provider variance is real, and it is the main operational constraint.**
  Measured against `deepseek-v4-flash` on 2026-08-29, by intercepting the
  actual provider request: CrewAI sends `max_tokens=8000` with no stop
  sequences, and a clean generation returns ~2,300 completion tokens with
  `finish_reason=stop`. But on the longest objects the model stops mid-JSON at
  roughly 3,000-3,500 completion tokens, far below the budget it accepted.
  That is a model ceiling, not a framework bug and not a misconfiguration.

  Two consequences you can act on:
  - The size budgets in `prompts/tasks.yaml` (at most 8 test cases, 5 steps
    each, 15 words per field) exist to keep the largest object under that
    ceiling. Raise them only on a model that can sustain longer output.
  - A truncated response is detected, never silently accepted, and the retry
    is given a concrete character target. A qualitative "be shorter" is
    ignored by models: the first version of that retry asked for a shorter
    object and got one three times longer.
- **Tickets are processed sequentially**, so a large batch takes a while.
  Expect roughly 3-6 minutes per ticket on DeepSeek: four sequential stages at
  40-120 seconds each, plus any retry.
- **`outputs/` is local disk.** On Streamlit Community Cloud it does not
  persist; download the ZIP.
