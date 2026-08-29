"""Atlassian Document Format (ADF) to plain text.

Jira Cloud REST v3 returns rich text as an ADF JSON tree, not a string. A
naive ``description["content"][0]["content"][0]["text"]`` drops most of the
ticket, so we walk the whole tree.

The converter is deliberately lossy but readable: it keeps paragraphs, lists,
headings, tables, code blocks and link targets, and ignores styling.
"""

from __future__ import annotations

from typing import Any

_BLOCK_TYPES = {
    "paragraph",
    "heading",
    "blockquote",
    "codeBlock",
    "panel",
    "rule",
    "mediaSingle",
    "mediaGroup",
}


def adf_to_text(node: Any, _depth: int = 0) -> str:
    """Convert an ADF node (or plain string) into readable text.

    Accepts ``None``, a ``str``, a ``list`` or a ``dict`` so it can be pointed
    at any Jira field without a type check at the call site.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(child, _depth) for child in node)
    if not isinstance(node, dict):
        return str(node)

    node_type = node.get("type", "")

    if node_type == "text":
        text = node.get("text", "")
        for mark in node.get("marks", []) or []:
            if mark.get("type") == "link":
                href = (mark.get("attrs") or {}).get("href", "")
                if href and href not in text:
                    text = f"{text} ({href})"
        return text

    if node_type == "hardBreak":
        return "\n"

    if node_type == "rule":
        return "\n---\n"

    if node_type == "mention":
        return f"@{(node.get('attrs') or {}).get('text', 'user').lstrip('@')}"

    if node_type == "emoji":
        attrs = node.get("attrs") or {}
        return attrs.get("text") or attrs.get("shortName") or ""

    if node_type == "inlineCard":
        return (node.get("attrs") or {}).get("url", "")

    if node_type == "date":
        return (node.get("attrs") or {}).get("timestamp", "")

    if node_type == "heading":
        level = int((node.get("attrs") or {}).get("level", 1))
        inner = adf_to_text(node.get("content"), _depth).strip()
        return f"\n{'#' * min(level, 6)} {inner}\n" if inner else ""

    if node_type == "codeBlock":
        language = (node.get("attrs") or {}).get("language", "")
        inner = adf_to_text(node.get("content"), _depth)
        return f"\n```{language}\n{inner.strip()}\n```\n"

    if node_type in {"bulletList", "orderedList"}:
        ordered = node_type == "orderedList"
        lines: list[str] = []
        for index, item in enumerate(node.get("content", []) or [], start=1):
            marker = f"{index}." if ordered else "-"
            inner = adf_to_text(item, _depth + 1).strip()
            if not inner:
                continue
            indent = "  " * _depth
            first, *rest = inner.splitlines()
            lines.append(f"{indent}{marker} {first}")
            lines.extend(f"{indent}  {line}" for line in rest)
        return "\n" + "\n".join(lines) + "\n" if lines else ""

    if node_type == "listItem":
        return adf_to_text(node.get("content"), _depth)

    if node_type in {"taskList", "decisionList"}:
        lines = []
        for item in node.get("content", []) or []:
            state = (item.get("attrs") or {}).get("state", "")
            box = "[x]" if str(state).upper() == "DONE" else "[ ]"
            inner = adf_to_text(item.get("content"), _depth).strip()
            if inner:
                lines.append(f"- {box} {inner}")
        return "\n" + "\n".join(lines) + "\n" if lines else ""

    if node_type in {"taskItem", "decisionItem"}:
        return adf_to_text(node.get("content"), _depth)

    if node_type == "table":
        rows: list[str] = []
        for row in node.get("content", []) or []:
            cells = [
                adf_to_text(cell.get("content"), _depth).strip().replace("\n", " ")
                for cell in row.get("content", []) or []
            ]
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n" + "\n".join(rows) + "\n" if rows else ""

    if node_type == "blockquote":
        inner = adf_to_text(node.get("content"), _depth).strip()
        quoted = "\n".join(f"> {line}" for line in inner.splitlines())
        return f"\n{quoted}\n" if inner else ""

    inner = adf_to_text(node.get("content"), _depth)
    if node_type in _BLOCK_TYPES or node_type == "doc":
        return inner + "\n"
    return inner


def normalize_text(raw: Any) -> str:
    """ADF (or string) to text with collapsed blank lines and trimmed edges."""
    text = adf_to_text(raw)
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if not line and cleaned and not cleaned[-1]:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()
