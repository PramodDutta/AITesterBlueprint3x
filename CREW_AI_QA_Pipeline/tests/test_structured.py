"""Structured output on providers that cannot enforce a JSON schema."""

from __future__ import annotations

import json

import pytest

from jira_qa_crew.models import RequirementAnalysis, TestPlan
from jira_qa_crew.services.structured import (
    compact_schema,
    extract_json,
    is_empty_response,
    json_mode_instruction,
    parse_model,
    schema_rejected,
)


# --------------------------------------------------------------------------
# Detecting a provider that cannot enforce a schema
# --------------------------------------------------------------------------
def test_recognises_the_deepseek_rejection():
    """The exact error this project hit against DeepSeek on 2026-08-29."""
    exc = Exception(
        "Error code: 400 - {'error': {'message': 'This response_format type is "
        "unavailable now', 'type': 'invalid_request_error'}}"
    )
    assert schema_rejected(exc)


def test_recognises_an_openai_style_schema_rejection():
    exc = Exception(
        "Error code: 400 - unsupported_value: 'response_format.json_schema' is not supported"
    )
    assert schema_rejected(exc)


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 429 - rate limit exceeded",
        "Error code: 401 - invalid api key",
        "Connection timed out",
        "Error code: 400 - {'message': 'context length exceeded'}",
    ],
)
def test_other_failures_are_not_mistaken_for_a_schema_problem(message):
    """A rate limit must never silently downgrade schema enforcement."""
    assert not schema_rejected(Exception(message))


# --------------------------------------------------------------------------
# Extracting JSON from a model response
# --------------------------------------------------------------------------
def test_extracts_a_bare_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extracts_from_a_fenced_block():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json("```\n{\"a\": 2}\n```") == {"a": 2}


def test_extracts_an_object_wrapped_in_prose():
    text = 'Sure, here is the result:\n{"a": 1, "b": [2, 3]}\nLet me know if you need more.'
    assert extract_json(text) == {"a": 1, "b": [2, 3]}


def test_takes_the_first_object_of_a_json_array():
    assert extract_json('[{"a": 1}, {"a": 2}]') == {"a": 1}


@pytest.mark.parametrize("text", ["", "   ", "no json at all", "{not: valid}", None])
def test_returns_none_when_there_is_nothing_parseable(text):
    assert extract_json(text) is None


def test_nested_braces_survive_extraction():
    payload = {"outer": {"inner": {"deep": [1, 2, {"x": "}"}]}}}
    assert extract_json(f"prefix {json.dumps(payload)} suffix") == payload


# --------------------------------------------------------------------------
# Parsing into a model
# --------------------------------------------------------------------------
def test_parses_a_valid_payload_into_the_model(analysis):
    text = "```json\n" + analysis.model_dump_json() + "\n```"
    parsed = parse_model(text, RequirementAnalysis)
    assert parsed is not None
    assert parsed.ticket_key == "VWO-48"
    assert [r.id for r in parsed.requirements] == ["REQ-001", "REQ-002"]


def test_a_payload_that_breaks_the_schema_is_rejected_not_coerced():
    text = json.dumps({"ticket_key": "VWO-48", "summary": "s",
                       "requirements": [{"id": "NOT-AN-ID", "text": "x"}]})
    assert parse_model(text, RequirementAnalysis) is None


def test_the_twelve_section_rule_still_applies_in_prompted_mode():
    text = json.dumps({"ticket_key": "V-1", "title": "t", "sections": []})
    assert parse_model(text, TestPlan) is None


def test_prose_only_output_is_rejected():
    assert parse_model("I was unable to produce that object.", RequirementAnalysis) is None


# --------------------------------------------------------------------------
# The prompt suffix
# --------------------------------------------------------------------------
def test_the_instruction_carries_the_real_schema():
    instruction = json_mode_instruction(TestPlan)
    assert "OUTPUT FORMAT" in instruction
    assert "single JSON object" in instruction
    # The embedded schema must itself be valid JSON and describe the model.
    start = instruction.index("{")
    end = instruction.rindex("}")
    schema = json.loads(instruction[start : end + 1])
    assert "sections" in schema["properties"]
    assert "ticket_key" in schema["properties"]


# --------------------------------------------------------------------------
# Compaction and transient failures
# --------------------------------------------------------------------------
def test_compaction_removes_prompt_noise_but_keeps_structure():
    raw = TestPlan.model_json_schema()
    small = compact_schema(raw)

    assert "properties" in small
    assert "sections" in small["properties"]
    assert "$defs" in small
    # metadata is gone from the schema bodies
    assert "description" not in small
    assert "description" not in small["$defs"]["TestPlanSection"]

    # and the prompt actually shrinks: compact separators vs an indented dump
    prompt_size = len(json.dumps(small, separators=(",", ":")))
    assert prompt_size < len(json.dumps(raw, indent=2)) // 2


def test_compaction_never_deletes_a_field_actually_called_title():
    """Regression: `title` is both a schema keyword and a real field name here."""
    small = compact_schema(TestPlan.model_json_schema())

    assert "title" in small["properties"], "TestPlan.title must survive compaction"
    section = small["$defs"]["TestPlanSection"]["properties"]
    assert set(section) == {"number", "title", "content"}
    scenario = small["$defs"]["TestScenario"]["properties"]
    assert "title" in scenario and "description" in scenario

    # every required field must still have a definition
    for name in small["required"]:
        assert name in small["properties"], name


def test_compaction_output_still_round_trips_a_real_object(test_plan):
    """A compacted schema must still describe objects the model accepts."""
    small = compact_schema(TestPlan.model_json_schema())
    payload = json.loads(test_plan.model_dump_json())
    for field in small["required"]:
        assert field in payload
    assert TestPlan.model_validate(payload).ticket_key == "VWO-48"


def test_compaction_is_recursive_and_handles_lists():
    nested = {"title": "x", "anyOf": [{"title": "y", "type": "string"}, {"type": "null"}]}
    assert compact_schema(nested) == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_recognises_an_empty_completion():
    """DeepSeek's characteristic failure: a successful call with no content."""
    assert is_empty_response(ValueError("Invalid response from LLM call - None or empty."))
    assert is_empty_response(Exception("empty response from provider"))


@pytest.mark.parametrize(
    "message",
    ["Error code: 429 - rate limit", "Error code: 401 - bad key", "context length exceeded"],
)
def test_real_errors_are_not_treated_as_empty_completions(message):
    assert not is_empty_response(Exception(message))


# --------------------------------------------------------------------------
# Truncation
# --------------------------------------------------------------------------
def test_detects_a_response_cut_off_mid_object():
    from jira_qa_crew.services.structured import looks_truncated

    assert looks_truncated('{"ticket_key": "VWO-48", "test_cases": [{"id": "VWO-48-TC-0')
    assert looks_truncated('{"a": [1, 2, 3]')
    assert looks_truncated('[{"a": 1}, {"b":')


def test_complete_or_non_json_responses_are_not_called_truncated():
    from jira_qa_crew.services.structured import looks_truncated

    assert not looks_truncated('{"a": 1}')
    assert not looks_truncated('[{"a": 1}]')
    assert not looks_truncated("I could not produce that object.")
    assert not looks_truncated("")


def test_brackets_inside_strings_do_not_confuse_truncation_detection():
    from jira_qa_crew.services.structured import looks_truncated

    assert not looks_truncated('{"selector": "div[data-id=\'{x}\']"}')
    assert not looks_truncated('{"note": "he said \\"} {\\" loudly"}')
    assert looks_truncated('{"selector": "div[data-id=\'{x}\']"')
