"""ADF to text conversion."""

from __future__ import annotations

from jira_qa_crew.jira.adf import adf_to_text, normalize_text


def _doc(*content):
    return {"type": "doc", "version": 1, "content": list(content)}


def test_plain_string_passes_through():
    assert adf_to_text("already text") == "already text"


def test_none_and_empty_are_safe():
    assert adf_to_text(None) == ""
    assert normalize_text(None) == ""


def test_walks_the_whole_tree_not_just_the_first_node():
    doc = _doc(
        {"type": "paragraph", "content": [{"type": "text", "text": "first"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "second"}]},
    )
    text = normalize_text(doc)
    assert "first" in text
    assert "second" in text


def test_headings_lists_and_code_blocks():
    doc = _doc(
        {"type": "heading", "attrs": {"level": 2},
         "content": [{"type": "text", "text": "Acceptance Criteria"}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "criterion one"}]}]},
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "criterion two"}]}]},
        ]},
        {"type": "codeBlock", "attrs": {"language": "ts"},
         "content": [{"type": "text", "text": "const x = 1;"}]},
    )
    text = normalize_text(doc)
    assert "## Acceptance Criteria" in text
    assert "- criterion one" in text
    assert "- criterion two" in text
    assert "```ts" in text and "const x = 1;" in text


def test_ordered_lists_are_numbered():
    doc = _doc({"type": "orderedList", "content": [
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "step one"}]}]},
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "step two"}]}]},
    ]})
    text = normalize_text(doc)
    assert "1. step one" in text
    assert "2. step two" in text


def test_links_keep_their_target():
    doc = _doc({"type": "paragraph", "content": [
        {"type": "text", "text": "spec",
         "marks": [{"type": "link", "attrs": {"href": "https://example.com/spec"}}]}]})
    assert "https://example.com/spec" in normalize_text(doc)


def test_tables_become_pipe_rows():
    doc = _doc({"type": "table", "content": [
        {"type": "tableRow", "content": [
            {"type": "tableCell", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Field"}]}]},
            {"type": "tableCell", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Value"}]}]},
        ]}]})
    assert "Field | Value" in normalize_text(doc)


def test_task_lists_show_state():
    doc = _doc({"type": "taskList", "content": [
        {"type": "taskItem", "attrs": {"state": "DONE"},
         "content": [{"type": "text", "text": "done item"}]},
        {"type": "taskItem", "attrs": {"state": "TODO"},
         "content": [{"type": "text", "text": "open item"}]},
    ]})
    text = normalize_text(doc)
    assert "- [x] done item" in text
    assert "- [ ] open item" in text


def test_blank_lines_are_collapsed():
    doc = _doc(
        {"type": "paragraph", "content": [{"type": "text", "text": "a"}]},
        {"type": "paragraph", "content": []},
        {"type": "paragraph", "content": []},
        {"type": "paragraph", "content": [{"type": "text", "text": "b"}]},
    )
    assert "\n\n\n" not in normalize_text(doc)
