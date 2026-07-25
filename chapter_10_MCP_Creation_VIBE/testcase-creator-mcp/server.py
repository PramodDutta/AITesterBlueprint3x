"""MCP server exposing the VWO manual test-case corpus as tools, resources, and prompts."""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Final

from fastmcp import FastMCP
from fastmcp.exceptions import PromptError, ResourceError, ToolError
from fastmcp.resources import ResourceContent

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log: Final = logging.getLogger("vwo-testcases")

CSV_ENV_VAR: Final = "VWO_TESTCASES_CSV"
CSV_FILENAME: Final = "vwo_5000_test_cases.csv"
_HERE: Final = Path(__file__).resolve().parent
_CANDIDATES: Final = (
    _HERE / "resource" / CSV_FILENAME,
    _HERE / CSV_FILENAME,
    _HERE.parent / "resource" / CSV_FILENAME,
)

COL_ID: Final = "Issue Key"
COL_MODULE: Final = "Component"
GROUPABLE: Final[dict[str, str]] = {
    "module": COL_MODULE,
    "priority": "Priority",
    "status": "Status",
    "test_type": "Test Type",
    "browser": "Browser",
    "device": "Device",
}
SEARCH_FIELDS: Final = ("Summary", "Description", "Steps", "Expected Result", "Labels", "Preconditions")
ENUM_COLUMNS: Final = ("Issue Type", "Priority", COL_MODULE, "Test Type", "Browser", "Device", "Status")
MAX_LIMIT: Final = 200
SUITE_SAMPLE: Final = 40

_CASES: list[dict[str, str]] = []
_BY_ID: dict[str, dict[str, str]] = {}


def _resolve_csv_path() -> Path:
    """Locate the dataset via the env override, then paths relative to this file."""
    override = os.environ.get(CSV_ENV_VAR)
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"{CSV_ENV_VAR}={override!r} is not a readable file")
        return path
    for candidate in _CANDIDATES:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(c) for c in _CANDIDATES)
    raise FileNotFoundError(f"{CSV_FILENAME} not found (looked in: {searched}); set {CSV_ENV_VAR} to override")


def _cases() -> list[dict[str, str]]:
    """Return the dataset, reading and caching the CSV on first use."""
    global _CASES, _BY_ID
    if _CASES:
        return _CASES
    try:
        path = _resolve_csv_path()
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
        if not rows:
            raise ValueError(f"{path} contains a header but no data rows")
        if COL_ID not in rows[0]:
            raise ValueError(f"{path} has no {COL_ID!r} column; found {list(rows[0])}")
    except (OSError, ValueError, csv.Error) as exc:
        raise ToolError(f"test-case dataset unavailable: {exc}") from exc
    _CASES = rows
    _BY_ID = {row[COL_ID].upper(): row for row in rows}
    log.info("loaded %d test cases from %s", len(rows), path)
    return _CASES


def _expand(row: dict[str, str]) -> dict[str, Any]:
    """Return a copy of a row with Steps and Labels split into lists."""
    expanded: dict[str, Any] = dict(row)
    expanded["Steps"] = [step.strip() for step in row["Steps"].split("|") if step.strip()]
    expanded["Labels"] = row["Labels"].split()
    return expanded


def _values(column: str) -> list[str]:
    """Return the sorted distinct values held in one column."""
    return sorted({row[column] for row in _cases()})


def _match_enum(column: str, value: str) -> str:
    """Resolve a user-supplied value to its canonical casing, or raise ToolError."""
    for known in _values(column):
        if known.casefold() == value.strip().casefold():
            return known
    raise ToolError(f"unknown {column} {value!r}; valid values: {', '.join(_values(column))}")


def _lookup(test_id: str) -> dict[str, str] | None:
    """Resolve an issue key, or a bare number such as 1001, to its row."""
    key = test_id.strip().upper()
    if key.isdigit():
        key = f"VWO-{key}"
    _cases()
    return _BY_ID.get(key)


def _module_rows(module: str) -> list[dict[str, str]]:
    """Return every row for a module, matched case-insensitively; empty when unknown."""
    wanted = module.strip().casefold()
    return [row for row in _cases() if row[COL_MODULE].casefold() == wanted]


def _as_json(payload: Any) -> str:
    """Serialise a payload to indented JSON text."""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _json_resource(payload: Any) -> list[ResourceContent]:
    """Wrap a payload as JSON resource content, forcing the application/json mime type."""
    return [ResourceContent(_as_json(payload), mime_type="application/json")]


mcp: Final = FastMCP(
    "vwo-testcases",
    instructions=(
        "Read-only access to a 5000-row VWO manual QA test-case export. "
        "Use tools to search, fetch, and aggregate; read resources for schema and bulk context."
    ),
)


@mcp.tool
def search_test_cases(
    query: str,
    module: str | None = None,
    test_type: str | None = None,
    priority: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search test cases by free text, optionally filtered by module, test type, and priority."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ToolError(f"limit must be between 1 and {MAX_LIMIT}, got {limit}")
    needle = query.strip().casefold()
    if not needle:
        raise ToolError("query must not be empty; pass a keyword such as 'invite user' or 'keyboard'")
    filters = {
        COL_MODULE: _match_enum(COL_MODULE, module) if module else None,
        "Test Type": _match_enum("Test Type", test_type) if test_type else None,
        "Priority": _match_enum("Priority", priority) if priority else None,
    }
    hits = [
        row
        for row in _cases()
        if all(row[col] == want for col, want in filters.items() if want)
        and any(needle in row[field].casefold() for field in SEARCH_FIELDS)
    ]
    if not hits:
        applied = ", ".join(f"{col}={want!r}" for col, want in filters.items() if want) or "no filters"
        raise ToolError(f"no test cases match query {query!r} ({applied}); try a broader keyword")
    log.info("search %r matched %d cases, returning %d", query, len(hits), min(len(hits), limit))
    return [_expand(row) for row in hits[:limit]]


@mcp.tool
def get_test_case(test_id: str) -> dict[str, Any]:
    """Return one test case by its issue key, for example VWO-1001."""
    row = _lookup(test_id)
    if row is None:
        raise ToolError(
            f"unknown test_id {test_id!r}; expected an issue key such as "
            f"{next(iter(_BY_ID))} (dataset holds {len(_BY_ID)} cases)"
        )
    return _expand(row)


@mcp.tool
def test_case_stats(group_by: str) -> dict[str, Any]:
    """Count test cases grouped by module, priority, status, test_type, browser, or device."""
    key = group_by.strip().casefold()
    column = GROUPABLE.get(key)
    if column is None:
        raise ToolError(f"unknown group_by {group_by!r}; valid values: {', '.join(GROUPABLE)}")
    counts = Counter(row[column] for row in _cases())
    return {
        "group_by": key,
        "column": column,
        "total": sum(counts.values()),
        "distinct": len(counts),
        "counts": dict(counts.most_common()),
    }


@mcp.resource("testcases://schema", mime_type="application/json")
def schema_resource() -> list[ResourceContent]:
    """Column names, inferred types, enum values, and row count for the dataset."""
    rows = _cases()
    return _json_resource(
        {
            "row_count": len(rows),
            "primary_key": COL_ID,
            "groupable_fields": GROUPABLE,
            "columns": [
                {
                    "name": name,
                    "type": "string",
                    "distinct": len({row[name] for row in rows}),
                    "values": _values(name) if name in ENUM_COLUMNS else None,
                }
                for name in rows[0]
            ],
        }
    )


@mcp.resource("testcases://all", mime_type="application/json")
def all_resource() -> list[ResourceContent]:
    """The complete test-case dataset as a JSON array."""
    return _json_resource([_expand(row) for row in _cases()])


@mcp.resource("testcases://modules", mime_type="application/json")
def modules_resource() -> list[ResourceContent]:
    """The valid module names accepted by testcases://module/{name}, with case counts."""
    counts = Counter(row[COL_MODULE] for row in _cases())
    return _json_resource([{"module": name, "count": n} for name, n in counts.most_common()])


@mcp.resource("testcases://module/{name}", mime_type="application/json")
def module_resource(name: str) -> list[ResourceContent]:
    """All test cases belonging to one module, matched case-insensitively."""
    hits = _module_rows(name)
    if not hits:
        raise ResourceError(f"unknown module {name!r}; read testcases://modules for the valid list")
    return _json_resource([_expand(row) for row in hits])


@mcp.prompt
def review_test_case(test_id: str) -> str:
    """Ask the model to critique one test case for coverage, clarity, and missing edge cases."""
    row = _lookup(test_id)
    if row is None:
        raise PromptError(f"unknown test_id {test_id!r}; expected an issue key such as {next(iter(_BY_ID))}")
    return (
        "You are a senior QA lead reviewing a single manual test case.\n\n"
        f"{_as_json(_expand(row))}\n\n"
        "Review it on four axes and be specific, citing the field you are criticising:\n"
        "1. Coverage: what scenario does this miss? Name concrete untested paths.\n"
        "2. Clarity: are the steps unambiguous and independently executable?\n"
        "3. Assertability: is the expected result objectively verifiable, or subjective?\n"
        "4. Automation readiness: what blocks this from becoming an automated check?\n\n"
        "Finish with a rewritten version of the weakest field."
    )


@mcp.prompt
def generate_regression_suite(module: str) -> str:
    """Ask the model to build an ordered regression suite from one module's test cases."""
    hits = _module_rows(module)
    if not hits:
        raise PromptError(f"unknown module {module!r}; valid modules: {', '.join(_values(COL_MODULE))}")
    sample = hits[:SUITE_SAMPLE]
    return (
        f"You are building a regression suite for the {hits[0][COL_MODULE]} module.\n"
        f"Showing {len(sample)} of {len(hits)} available cases.\n\n"
        f"{_as_json([_expand(row) for row in sample])}\n\n"
        "Produce a prioritised suite:\n"
        "1. Select the smallest set of cases that covers the module's critical paths.\n"
        "2. Order them so setup-heavy cases run first and dependent cases follow.\n"
        "3. For each, state the case key, why it is in the suite, and its runtime risk.\n"
        "4. List coverage gaps this module's existing cases do not address.\n\n"
        "Output a markdown table followed by the gap list."
    )


if __name__ == "__main__":
    try:
        log.info("startup: %d test cases cached", len(_cases()))
    except ToolError as exc:
        log.error("startup: %s", exc)
    mcp.run(show_banner=False)
