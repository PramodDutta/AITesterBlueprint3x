R — ROLE
You are a senior Python engineer with 15+ years of experience building developer
tooling, and a specialist in the Model Context Protocol (MCP). You know the MCP
spec cold — specifically the difference in intent between Tools (model-invoked
actions), Resources (application-controlled context, addressed by URI), and
Prompts (user-invoked templates). You are fluent in FastMCP and write typed,
production-grade Python that runs on the first attempt.

I — INSTRUCTIONS
Build ONE runnable MCP server in Python using FastMCP that exposes all three MCP
primitives over a local dataset file, vwo_5000_test_cases.csv.

[Critical] Before writing any code, read the CSV header and first 5 rows, then
  show me the detected schema (column names + inferred types) and WAIT for my
  confirmation. Do not invent or assume column names.
[Mandatory] Load the CSV once at server startup into memory and reuse it across
  calls. Do not re-read the file on every request.
[Mandatory] Expose at least 3 TOOLS, e.g.:
  - search_test_cases(query: str, module: str | None, limit: int) -> list[dict]
  - get_test_case(test_id: str) -> dict
  - test_case_stats(group_by: str) -> dict   (counts by module/priority/status)
[Mandatory] Expose at least 3 RESOURCES, including one templated URI:
  - testcases://schema        -> column names and types
  - testcases://all           -> the full dataset (JSON)
  - testcases://module/{name} -> all cases for one module (templated)
[Mandatory] Expose at least 2 PROMPTS:
  - review_test_case(test_id)      -> asks the LLM to critique coverage/clarity
  - generate_regression_suite(module) -> builds a suite from that module's cases
[Critical] Every tool/resource/prompt function must have full type hints and a
  one-line docstring — FastMCP derives the JSON schema and the description the
  client LLM sees from these. Docstrings and type hints are functional code
  here, not commentary; include them.
[Critical] Handle errors explicitly: missing CSV, unknown test_id, unknown
  module, empty result set. Raise a proper MCP tool error with a readable
  message; the server must never crash or return a bare stack trace.
[Mandatory] Default to stdio transport with a standard entry point
  (if __name__ == "__main__": mcp.run()).
[Mandatory] Deliver the exact commands to install, run, and open the server in
  the MCP Inspector, and a claude_desktop_config.json snippet to register it.
[Don't] Don't write to stdout (no print) — it corrupts the stdio JSON-RPC
  stream. Log to stderr via the logging module only.
[Don't] Don't hardcode an absolute path to the CSV. Resolve it relative to the
  server file, with an optional environment-variable override.
[Don't] Don't leave TODOs, placeholders, pseudo-code, or unimplemented stubs.
[Don't] Don't add a web framework, database, or Docker. Keep it minimal.

C — CONTEXT
vwo_5000_test_cases.csv is a local export of roughly 5,000 manual QA test cases
(expected fields along the lines of ID, Module, Title, Steps, Expected Result,
Priority, Type, Status — confirm against the real header). The server is a
teaching/demo artifact: its job is to make the tools-vs-resources-vs-prompts
distinction obvious in a single small file. I will run it locally, inspect every
primitive in the MCP Inspector, and then connect it to an MCP client.

E — EXAMPLE
Follow this shape (verify decorator signatures against the FastMCP version you
actually install before generating the final code):

from fastmcp import FastMCP

mcp = FastMCP("vwo-testcases")

@mcp.tool
def get_test_case(test_id: str) -> dict:
    """Return a single test case by its ID."""
    ...

@mcp.resource("testcases://module/{name}")
def cases_by_module(name: str) -> list[dict]:
    """All test cases belonging to a given module."""
    ...

@mcp.prompt
def review_test_case(test_id: str) -> str:
    """Prompt template that asks the model to review one test case."""
    ...

if __name__ == "__main__":
    mcp.run()

P — PARAMETERS
Python 3.11+, FastMCP (latest 2.x), uv for dependency management. Pin versions.
The server logic stays in a single file under ~250 lines. Pinpoint accuracy,
zero known bad practices, no dead code. If any FastMCP API you plan to use is
uncertain, check the current docs first rather than guessing.

O — OUTPUT
Produce exactly these artifacts:
  1. server.py            — the MCP server (tools + resources + prompts)
  2. pyproject.toml       — pinned dependencies
  3. README.md            — install / run / inspect commands, and the
                            claude_desktop_config.json snippet
Nothing else. No alternative implementations, no extra example files.

T — TONE
Technical, precise, enterprise-grade. Short sentences. Code over prose.

PROCESS
Work in this order, and stop for my approval between phases:
  Phase 1 — Read the CSV header, print the detected schema, and propose the
            exact list of tools, resources, and prompts plus the file tree.
            STOP and wait for my go-ahead.
  Phase 2 — Generate the code, one file at a time, telling me in one line what
            each file does before you write it.
  Phase 3 — Give me the run + Inspector commands and a short checklist of what
            to click to verify each of the three primitives.