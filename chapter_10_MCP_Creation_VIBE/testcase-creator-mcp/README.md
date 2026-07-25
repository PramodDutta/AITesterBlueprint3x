# VWO Test Cases MCP Server

One FastMCP server over a 5,000-row VWO manual QA test-case export. It exists to make the
**tools vs resources vs prompts** distinction concrete in a single file.

| Primitive | Who triggers it | What it is here |
|---|---|---|
| **Tools** | The model decides to call them | `search_test_cases`, `get_test_case`, `test_case_stats` |
| **Resources** | The client app fetches them by URI | `testcases://schema`, `testcases://all`, `testcases://modules`, `testcases://module/{name}` |
| **Prompts** | The user picks them from a menu | `review_test_case`, `generate_regression_suite` |

The CSV is read **once** at startup and cached in memory. Transport is stdio.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js (only for the MCP Inspector)

## Install

```bash
cd chapter_10_MCP_Creation_VIBE/testcase-creator-mcp
uv sync
```

This creates `.venv/` and installs the pinned `fastmcp==3.4.4`.

## Run

```bash
uv run python server.py
```

The process waits on stdin for JSON-RPC and appears to hang. That is correct: a stdio MCP
server is driven by a client, not by a terminal. Startup logs go to **stderr**:

```
INFO [vwo-testcases] loaded 5000 test cases from .../resource/vwo_5000_test_cases.csv
INFO [vwo-testcases] startup: 5000 test cases cached
```

Press `Ctrl+C` to stop. To drive it interactively, use the Inspector below.

## Inspect

```bash
npx -y @modelcontextprotocol/inspector \
  uv run --directory "$(pwd)" python server.py
```

Open the printed URL. It already carries the session token:

```
http://localhost:6274/?MCP_PROXY_PORT=6277&MCP_PROXY_AUTH_TOKEN=<token>
```

**If you see `Proxy Server PORT IS IN USE at port 6277`**, another Inspector is already
running. Do not kill it if it belongs to a different server. Use alternate ports instead:

```bash
CLIENT_PORT=6284 SERVER_PORT=6287 npx -y @modelcontextprotocol/inspector \
  uv run --directory "$(pwd)" python server.py
```

### Verification checklist

Click **Connect** first, then walk the three tabs. Each row is a distinct MCP primitive.

**Tools tab** — model-invoked actions

1. `get_test_case` with `test_id` = `VWO-1001`. Expect one case with `Steps` returned as a
   4-element array, not one pipe-delimited string. Bare `1001` and lowercase `vwo-1001` also work.
2. `search_test_cases` with `query` = `invite user`, `module` = `user management`, `limit` = `3`.
   Expect 3 results, all with `Component: "User Management"`. Note the module matched despite
   the lowercase input.
3. `test_case_stats` with `group_by` = `status`. Expect
   `{"Ready": 2234, "Automated": 1594, "Draft": 757, "Deprecated": 415}` totalling 5000.
4. Error path: `get_test_case` with `test_id` = `VWO-9999`. Expect a readable message naming a
   valid example key, not a stack trace.
5. Error path: `test_case_stats` with `group_by` = `colour`. The error lists the six valid values.

**Resources tab** — application-controlled context

6. `testcases://schema` — 14 columns with distinct counts and enum values. This is the
   ground truth for what the other primitives accept.
7. `testcases://modules` — the 17 valid module names with counts. Read this before step 9.
8. `testcases://all` — all 5000 rows, roughly 5.5 MB. Slow to render, which is exactly why
   bulk data belongs in a resource rather than a tool response.
9. `testcases://module/{name}` — the **templated** resource. Enter `Reports` for 333 cases.
   Lowercase `reports` works too. An unknown name returns a readable error pointing at step 7.

**Prompts tab** — user-invoked templates

10. `review_test_case` with `test_id` = `VWO-1001`. Expect a rendered message with the full
    case embedded as JSON plus a four-axis review rubric. Nothing is sent to a model here;
    the Inspector shows you the assembled text.
11. `generate_regression_suite` with `module` = `Reports`. The second line reads
    `Showing 40 of 333 available cases.` The cap is stated in the prompt rather than applied
    silently, so the model knows it is working from a sample.

## Register with Claude Desktop

Config file on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "vwo-testcases": {
      "command": "/Users/promode/.local/bin/uv",
      "args": [
        "run",
        "--directory",
        "/Users/promode/Documents/AITesterBlueprint3x/chapter_10_MCP_Creation_VIBE/testcase-creator-mcp",
        "python",
        "server.py"
      ]
    }
  }
}
```

Use the **absolute path** to `uv`. Claude Desktop does not inherit your shell `PATH`, so a bare
`"command": "uv"` fails with `spawn uv ENOENT`. Find yours with `which uv`. Restart Claude
Desktop fully (quit, do not just close the window) after editing.

For Claude Code, one command does the same thing:

```bash
claude mcp add vwo-testcases -- \
  uv run --directory "$(pwd)" python server.py
```

## Dataset location

Resolved in this order, so nothing is hardcoded to an absolute path:

1. `$VWO_TESTCASES_CSV`, if set
2. `./resource/vwo_5000_test_cases.csv` next to `server.py`
3. `./vwo_5000_test_cases.csv` next to `server.py`
4. `../resource/vwo_5000_test_cases.csv` — **the repo layout, used by default**

Point it elsewhere without editing code:

```bash
VWO_TESTCASES_CSV=/path/to/other.csv uv run python server.py
```

A missing or empty CSV does not crash the server. It logs the failure to stderr at startup
and returns a readable error on the first tool call, listing every path it searched.

## Schema

14 string columns, 5000 rows, no empty cells. Three names differ from the obvious guess:
the primary key is **`Issue Key`** (not `ID`), the title is **`Summary`** (not `Title`), and
the module is **`Component`** (not `Module`).

| Column | Distinct | Values |
|---|---|---|
| `Issue Type` | 1 | `Test` |
| `Issue Key` | 5000 | `VWO-1001` … `VWO-6000` (primary key) |
| `Summary` | free | shaped `[Component] TestType: title` |
| `Description` | free | |
| `Priority` | 4 | Highest, High, Medium, Low |
| `Component` | 17 | Reports, Personalization, Feature Rollout, Surveys, … |
| `Labels` | free | space-separated, split into a list on output |
| `Test Type` | 9 | Functional, Negative, UI/UX, API, Boundary, Regression, Security, Accessibility, Performance |
| `Preconditions` | free | |
| `Steps` | free | ` \| `-delimited, split into a list on output |
| `Expected Result` | free | |
| `Browser` | 4 | Chrome 148, Firefox 141, Safari 19, Edge 148 |
| `Device` | 4 | desktop, tablet, mobile (Android), mobile (iOS) |
| `Status` | 4 | Ready, Automated, Draft, Deprecated |

`search_test_cases` matches against Summary, Description, Steps, Expected Result, Labels,
and Preconditions.

## Two things worth knowing

**Resources return `list[ResourceContent]`, not `list[dict]`.** FastMCP 3.x reads a returned
list as a list of *content blocks*. Returning `list[dict]` from a resource, which is valid in
FastMCP 2.x, raises on 3.x:

```
TypeError: contents[0] must be ResourceContent, got dict.
```

Returning a bare `str` works but silently forces `mimeType: text/plain`, overriding the
`mime_type` declared on the decorator. Wrapping in `ResourceContent(..., mime_type=...)` is
what actually delivers `application/json` for both plain and templated resources.

**Nothing is written to stdout.** stdout carries the JSON-RPC stream, so a single stray
`print()` corrupts the session. All logging goes to stderr, and `mcp.run(show_banner=False)`
suppresses the FastMCP startup banner. When an expected error fires, such as an unknown
module, FastMCP renders a traceback to **stderr** while the client receives only the clean
message. That stderr noise is intentional and left in place: muting it would also hide real bugs.
