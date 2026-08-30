"""Pipeline orchestration with the LLM mocked out.

The crew is never really executed here: ``_kickoff_single`` is replaced with a
stub that attaches a prepared Pydantic object to the task, which is exactly
what a successful CrewAI run does.
"""

from __future__ import annotations

from typing import Any

import pytest

from jira_qa_crew.exceptions import JiraError
from jira_qa_crew.models import (
    JiraSource,
    PlaywrightBundle,
    RequirementAnalysis,
    StageName,
    StageStatus,
    TestCaseSuite,
    TestPlan,
    TicketStatus,
)
from jira_qa_crew.services.pipeline import QAPipeline, new_run_id


class FakeTaskOutput:
    def __init__(self, obj):
        self.pydantic = obj
        self.json_dict = obj.model_dump(mode="json") if obj is not None else None
        self.raw = "stubbed"


class StubGateway:
    """Gateway double: serves prepared issues or raises prepared errors."""

    def __init__(self, issues: dict[str, Any], errors: dict[str, Exception] | None = None):
        self._issues = issues
        self._errors = errors or {}
        self.calls: list[str] = []

    def fetch_issue(self, issue_key, mode=None):
        self.calls.append(issue_key)
        if issue_key in self._errors:
            raise self._errors[issue_key]
        return self._issues[issue_key]


@pytest.fixture
def stub_outputs(analysis, test_plan, test_cases, playwright_bundle):
    return {
        RequirementAnalysis: analysis,
        TestPlan: test_plan,
        TestCaseSuite: test_cases,
        PlaywrightBundle: playwright_bundle,
    }


def install_stub_kickoff(monkeypatch, outputs, failures=None, call_log=None):
    """Replace real crew execution with a deterministic stub."""
    failures = failures or {}
    attempts: dict[Any, int] = {}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        model = task.output_pydantic
        attempts[model] = attempts.get(model, 0) + 1
        if call_log is not None:
            call_log.append((model.__name__, attempts[model]))
        planned = failures.get(model)
        if planned and attempts[model] <= planned.get("times", 0):
            if planned.get("raise"):
                raise planned["raise"]
            task.output = FakeTaskOutput(planned["object"])
            return
        task.output = FakeTaskOutput(outputs[model])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    return attempts


# --------------------------------------------------------------------------
def test_a_successful_ticket_produces_every_artifact(
    settings, issue, stub_outputs, monkeypatch, tmp_path
):
    install_stub_kickoff(monkeypatch, stub_outputs)
    pipeline = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue}))

    run = pipeline.run(["VWO-48"])

    assert run.successful
    result = run.results[0]
    assert result.status in (TicketStatus.COMPLETED, TicketStatus.COMPLETED_WITH_WARNINGS)
    assert result.analysis and result.test_plan and result.test_cases and result.playwright
    assert result.coverage is not None
    assert result.source is JiraSource.REST

    run_dir = tmp_path / "outputs" / run.run_id
    assert (run_dir / "run_summary.md").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "VWO-48" / "test_cases.csv").exists()
    assert (run_dir / "VWO-48" / "playwright" / "tests" / "vwo-48.spec.ts").exists()


def test_every_stage_is_reported(settings, issue, stub_outputs, monkeypatch):
    install_stub_kickoff(monkeypatch, stub_outputs)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    stages = {s.stage: s for s in run.results[0].stages}
    assert set(stages) == set(StageName)
    assert stages[StageName.FETCH].status is StageStatus.COMPLETED
    assert stages[StageName.ARTIFACTS].status is StageStatus.COMPLETED
    assert stages[StageName.FETCH].duration_seconds is not None


def test_progress_callback_receives_real_transitions(settings, issue, stub_outputs, monkeypatch):
    install_stub_kickoff(monkeypatch, stub_outputs)
    seen: list[tuple[str, str, str]] = []

    pipeline = QAPipeline(
        settings,
        gateway=StubGateway({"VWO-48": issue}),
        progress=lambda key, event: seen.append((key, event.stage.value, event.status.value)),
    )
    pipeline.run(["VWO-48"])

    assert seen, "the UI must receive genuine progress events"
    assert all(key == "VWO-48" for key, _, _ in seen)
    assert ("VWO-48", "Jira Analyst", "RUNNING") in seen
    assert any(status == "COMPLETED" for _, _, status in seen)


def test_a_broken_progress_sink_cannot_kill_a_run(settings, issue, stub_outputs, monkeypatch):
    install_stub_kickoff(monkeypatch, stub_outputs)

    def exploding(key, event):
        raise RuntimeError("the UI blew up")

    run = QAPipeline(
        settings, gateway=StubGateway({"VWO-48": issue}), progress=exploding
    ).run(["VWO-48"])
    assert run.successful


# --------------------------------------------------------------------------
def test_one_failed_ticket_does_not_stop_the_others(
    settings, issue, stub_outputs, monkeypatch
):
    install_stub_kickoff(monkeypatch, stub_outputs)
    gateway = StubGateway(
        {"VWO-48": issue}, errors={"VWO-49": JiraError("jira said no")}
    )

    run = QAPipeline(settings, gateway=gateway).run(["VWO-49", "VWO-48"])

    assert len(run.results) == 2
    failed, ok = run.results[0], run.results[1]
    assert failed.ticket_key == "VWO-49" and failed.status is TicketStatus.FAILED
    assert "jira said no" in failed.error
    assert ok.ticket_key == "VWO-48" and ok.status is not TicketStatus.FAILED
    assert run.successful, "a run with at least one completed ticket is a success"


def test_a_run_where_everything_fails_is_not_successful(settings, monkeypatch, stub_outputs):
    install_stub_kickoff(monkeypatch, stub_outputs)
    gateway = StubGateway({}, errors={"VWO-48": JiraError("down")})
    run = QAPipeline(settings, gateway=gateway).run(["VWO-48"])

    assert not run.successful
    assert run.results[0].status is TicketStatus.FAILED
    assert run.results[0].analysis is None


def test_a_ticket_is_never_marked_successful_without_its_output(
    settings, issue, stub_outputs, monkeypatch
):
    install_stub_kickoff(
        monkeypatch,
        stub_outputs,
        failures={PlaywrightBundle: {"times": 99, "object": None}},
    )
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    result = run.results[0]
    assert result.status is TicketStatus.FAILED
    assert result.playwright is None
    assert "Playwright" in result.error or "PlaywrightBundle" in result.error


def test_tickets_do_not_leak_into_each_other(settings, issue, stub_outputs, monkeypatch):
    """Each ticket gets its own crew, so VWO-49 must not inherit VWO-48's data."""
    other = issue.model_copy(update={"key": "VWO-49", "summary": "A different ticket"})
    install_stub_kickoff(monkeypatch, stub_outputs)

    gateway = StubGateway({"VWO-48": issue, "VWO-49": other})
    run = QAPipeline(settings, gateway=gateway).run(["VWO-48", "VWO-49"])

    assert gateway.calls == ["VWO-48", "VWO-49"]
    # The stub returns a VWO-48 analysis for both, and validation must catch it.
    second = run.results[1]
    assert second.status is TicketStatus.FAILED
    assert "VWO-48" in second.error and "VWO-49" in second.error


# --------------------------------------------------------------------------
def test_malformed_output_gets_exactly_one_repair_attempt(
    settings, issue, stub_outputs, monkeypatch
):
    log: list[tuple[str, int]] = []
    install_stub_kickoff(
        monkeypatch,
        stub_outputs,
        failures={RequirementAnalysis: {"times": 1, "object": None}},
        call_log=log,
    )
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    analysis_calls = [c for c in log if c[0] == "RequirementAnalysis"]
    assert len(analysis_calls) == 2, "one original attempt plus exactly one repair"
    assert run.results[0].status is not TicketStatus.FAILED


def test_repair_is_not_retried_forever(settings, issue, stub_outputs, monkeypatch):
    log: list[tuple[str, int]] = []
    install_stub_kickoff(
        monkeypatch,
        stub_outputs,
        failures={RequirementAnalysis: {"times": 99, "object": None}},
        call_log=log,
    )
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert len([c for c in log if c[0] == "RequirementAnalysis"]) == 2
    assert run.results[0].status is TicketStatus.FAILED


def test_an_llm_exception_is_retried_once_then_reported(
    settings, issue, stub_outputs, monkeypatch
):
    log: list[tuple[str, int]] = []
    install_stub_kickoff(
        monkeypatch,
        stub_outputs,
        failures={TestPlan: {"times": 99, "raise": RuntimeError("model unavailable")}},
        call_log=log,
    )
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert len([c for c in log if c[0] == "TestPlan"]) == 2
    assert run.results[0].status is TicketStatus.FAILED
    assert "model unavailable" in run.results[0].error


def test_the_repair_note_is_appended_once_not_stacked():
    from crewai import Task

    task = Task.model_construct(description="original body")
    QAPipeline._append_repair_instruction(task, ["problem one"])
    QAPipeline._append_repair_instruction(task, ["problem two"])

    assert task.description.count("CORRECTION REQUIRED") == 1
    assert "problem two" in task.description
    assert "problem one" not in task.description
    assert task.description.startswith("original body")


# --------------------------------------------------------------------------
def test_no_llm_configured_fails_the_ticket_without_pretending(
    settings, issue, monkeypatch, stub_outputs
):
    install_stub_kickoff(monkeypatch, stub_outputs)
    no_llm = settings.__class__(**{**settings.__dict__, "llm_api_key": ""})

    run = QAPipeline(no_llm, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    result = run.results[0]
    assert result.status is TicketStatus.FAILED
    assert "LLM is not configured" in result.error
    assert result.issue is not None, "the fetch stage still succeeded"
    assert result.analysis is None


def test_coverage_warnings_are_attached_to_the_result(
    settings, issue, stub_outputs, analysis, monkeypatch
):
    thin_suite = stub_outputs[TestCaseSuite].model_copy(
        update={"test_cases": [stub_outputs[TestCaseSuite].test_cases[0]]}
    )
    outputs = {**stub_outputs, TestCaseSuite: thin_suite}
    install_stub_kickoff(monkeypatch, outputs)

    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])
    result = run.results[0]

    assert result.status is TicketStatus.COMPLETED_WITH_WARNINGS
    assert any("REQ-002" in w for w in result.warnings)


def test_run_ids_are_sortable_and_prefixed():
    from datetime import datetime

    assert new_run_id(datetime(2026, 8, 29, 10, 30, 15)) == "RUN-20260829-103015"


def test_invalid_and_duplicate_input_is_carried_into_the_summary(
    settings, issue, stub_outputs, monkeypatch
):
    install_stub_kickoff(monkeypatch, stub_outputs)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(
        ["VWO-48"], invalid_inputs=["not-a-key"], duplicates=["VWO-48"]
    )
    assert run.invalid_inputs == ["not-a-key"]
    assert run.duplicates_removed == ["VWO-48"]


# --------------------------------------------------------------------------
# Provider without JSON-schema support
# --------------------------------------------------------------------------
def test_falls_back_to_prompted_json_when_the_provider_rejects_the_schema(
    settings, issue, stub_outputs, monkeypatch
):
    """DeepSeek rejects response_format=json_schema. The run must still finish."""
    calls: list[bool] = []
    rejection = RuntimeError(
        "Error code: 400 - {'error': {'message': 'This response_format type is "
        "unavailable now', 'type': 'invalid_request_error'}}"
    )

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        calls.append(enforce_schema)
        if enforce_schema:
            raise rejection
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    assert calls[0] is True, "the first attempt should try provider enforcement"
    assert calls[1] is False, "the second attempt should be prompted JSON"
    assert calls[2:] == [False] * len(calls[2:]), (
        "once rejected, later stages must go straight to prompted JSON"
    )


def test_json_object_is_preferred_over_plain_text_in_prompted_mode(
    settings, issue, stub_outputs, monkeypatch
):
    """response_format=json_object guarantees parseable JSON; prefer it."""
    from jira_qa_crew.config import StructuredOutputMode

    prompt_only = settings.__class__(
        **{**settings.__dict__, "llm_structured_output": StructuredOutputMode.PROMPT}
    )
    seen: list[tuple[bool, bool]] = []

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        seen.append((enforce_schema, json_object))
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(prompt_only, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    assert seen == [(False, True)] * len(seen)


def test_a_provider_that_also_rejects_json_object_falls_back_to_plain_text(
    settings, issue, stub_outputs, monkeypatch
):
    from jira_qa_crew.config import StructuredOutputMode

    prompt_only = settings.__class__(
        **{**settings.__dict__, "llm_structured_output": StructuredOutputMode.PROMPT}
    )
    seen: list[tuple[bool, bool]] = []

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        seen.append((enforce_schema, json_object))
        if json_object:
            raise RuntimeError(
                "Error code: 400 - unsupported_value: 'response_format' is not supported"
            )
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(prompt_only, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    assert seen[0] == (False, True)
    assert seen[1] == (False, False)
    assert (False, True) not in seen[2:], "the rejected rung must not be retried"


def test_a_rate_limit_is_not_treated_as_a_schema_problem(
    settings, issue, stub_outputs, monkeypatch
):
    calls: list[bool] = []

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        calls.append(enforce_schema)
        raise RuntimeError("Error code: 429 - rate limit exceeded")

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.results[0].status is TicketStatus.FAILED
    assert all(enforce is True for enforce in calls), (
        "a rate limit must never downgrade schema enforcement"
    )
    assert "429" in run.results[0].error


def test_raw_text_output_is_parsed_when_the_runtime_attaches_no_model(
    settings, issue, stub_outputs, monkeypatch
):
    """Prompted-JSON mode returns text; the pipeline must validate it itself."""

    class RawOnlyOutput:
        def __init__(self, obj):
            self.pydantic = None
            self.json_dict = None
            self.raw = "```json\n" + obj.model_dump_json() + "\n```"

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        task.output = RawOnlyOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    assert run.results[0].test_cases is not None


def test_an_empty_completion_is_retried_then_reported(
    settings, issue, stub_outputs, monkeypatch
):
    """DeepSeek returns empty content under load; that is transient, not fatal."""
    attempts = {"n": 0}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        if task.output_pydantic is RequirementAnalysis:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("Invalid response from LLM call - None or empty.")
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    monkeypatch.setattr("jira_qa_crew.services.pipeline.time.sleep", lambda _: None)

    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    assert attempts["n"] == 2, "one empty completion should be retried exactly once"


def test_empty_completions_do_not_retry_forever(settings, issue, stub_outputs, monkeypatch):
    attempts = {"n": 0}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        attempts["n"] += 1
        raise ValueError("Invalid response from LLM call - None or empty.")

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    monkeypatch.setattr("jira_qa_crew.services.pipeline.time.sleep", lambda _: None)

    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.results[0].status is TicketStatus.FAILED
    # Hard ceiling: MAX_CALLS_PER_ATTEMPT per execute, and at most two executes
    # (the original attempt plus the single repair).
    from jira_qa_crew.services.pipeline import MAX_CALLS_PER_ATTEMPT

    assert attempts["n"] <= MAX_CALLS_PER_ATTEMPT * 2, (
        f"retries are not bounded: {attempts['n']} calls"
    )


def test_downstream_stages_get_a_compact_handoff_not_the_raw_context(
    settings, issue, stub_outputs, monkeypatch
):
    """The prompt must not grow by the full JSON of every earlier stage."""
    seen: dict[str, tuple[str, object]] = {}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        # task.context is CrewAI's _NotSpecified sentinel until it is assigned.
        seen[task.output_pydantic.__name__] = (task.description, task.context)
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    plan_description, plan_context = seen["TestPlan"]
    assert "VALIDATED REQUIREMENT ANALYSIS" in plan_description
    assert "REQ-001" in plan_description
    assert plan_context == [], "raw context is replaced, not sent as well"

    pw_description, pw_context = seen["PlaywrightBundle"]
    assert "VALIDATED TEST CASES" in pw_description
    assert "VWO-48-TC-001" in pw_description
    assert "Do NOT automate" in pw_description
    assert pw_context == []


def test_the_test_case_stage_is_told_which_ids_exist(
    settings, issue, stub_outputs, monkeypatch
):
    descriptions: dict[str, str] = {}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        descriptions[task.output_pydantic.__name__] = task.description
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    cases = descriptions["TestCaseSuite"]
    assert "REQ-001, REQ-002" in cases
    assert "AC-001, AC-002" in cases
    assert "(none extracted)" not in cases


def test_prompt_mode_skips_the_schema_probe_entirely(
    settings, issue, stub_outputs, monkeypatch
):
    """On a provider known to lack schema support, don't waste a call finding out."""
    from jira_qa_crew.config import StructuredOutputMode

    prompt_only = settings.__class__(
        **{**settings.__dict__, "llm_structured_output": StructuredOutputMode.PROMPT}
    )
    calls: list[bool] = []

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        calls.append(enforce_schema)
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(prompt_only, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    assert calls == [False] * len(calls), "no attempt should ask for schema enforcement"


def test_schema_mode_never_downgrades(settings, issue, stub_outputs, monkeypatch):
    """If the operator insists on schema mode, a rejection is an error, not a fallback."""
    from jira_qa_crew.config import StructuredOutputMode

    strict = settings.__class__(
        **{**settings.__dict__, "llm_structured_output": StructuredOutputMode.SCHEMA}
    )
    calls: list[bool] = []

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        calls.append(enforce_schema)
        raise RuntimeError(
            "Error code: 400 - {'error': {'message': 'This response_format type is "
            "unavailable now', 'type': 'invalid_request_error'}}"
        )

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(strict, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.results[0].status is TicketStatus.FAILED
    assert all(enforce is True for enforce in calls)


def test_a_truncated_response_produces_an_actionable_retry_instruction(
    settings, issue, stub_outputs, monkeypatch
):
    """A cut-off response needs 'write less', not 'you made a mistake'."""
    descriptions: list[str] = []

    class TruncatedOutput:
        pydantic = None
        json_dict = None
        # long enough to count as "wrote too much"
        raw = '{"ticket_key": "VWO-48", "summary": "' + "x" * 4000 + '", "req": [{"id": "R'

    calls = {"n": 0}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        if task.output_pydantic is RequirementAnalysis:
            calls["n"] += 1
            descriptions.append(task.description)
            if calls["n"] == 1:
                task.output = TruncatedOutput()
                return
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    retry_prompt = descriptions[-1]
    assert "cut off before the JSON finished" in retry_prompt
    assert "MUST be under" in retry_prompt, "the retry needs a concrete size target"
    assert "roughly HALF the length" in retry_prompt
    assert "discarded" in retry_prompt


def test_repeated_empty_completions_step_down_the_ladder(
    settings, issue, stub_outputs, monkeypatch
):
    """If a constrained request keeps coming back empty, try a looser one."""
    from jira_qa_crew.config import StructuredOutputMode

    prompt_only = settings.__class__(
        **{**settings.__dict__, "llm_structured_output": StructuredOutputMode.PROMPT}
    )
    seen: list[tuple[bool, bool]] = []

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        seen.append((enforce_schema, json_object))
        if json_object:
            raise ValueError("Invalid response from LLM call - None or empty.")
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    monkeypatch.setattr("jira_qa_crew.services.pipeline.time.sleep", lambda _: None)

    run = QAPipeline(prompt_only, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful, "stepping down should rescue the stage"
    # json_object is tried, retried, then abandoned for the plain rung
    assert seen[0] == (False, True)
    assert (False, False) in seen, "the looser rung must be attempted"


def test_a_short_truncation_is_not_told_to_write_less(
    settings, issue, stub_outputs, monkeypatch
):
    """A 978-char cut is a dropped stream. Asking for 'half of that' is nonsense."""
    from jira_qa_crew.services.pipeline import LENGTHY_RESPONSE_CHARS

    descriptions: list[str] = []

    class ShortTruncation:
        pydantic = None
        json_dict = None
        raw = '{"ticket_key": "VWO-48", "files": [{"path": "tests/a.spec.ts", "content": "im'

    assert len(ShortTruncation.raw) < LENGTHY_RESPONSE_CHARS
    calls = {"n": 0}

    def fake_kickoff(self, task, enforce_schema=True, json_object=False):
        if task.output_pydantic is RequirementAnalysis:
            calls["n"] += 1
            descriptions.append(task.description)
            if calls["n"] == 1:
                task.output = ShortTruncation()
                return
        task.output = FakeTaskOutput(stub_outputs[task.output_pydantic])

    monkeypatch.setattr(QAPipeline, "_kickoff_single", fake_kickoff)
    run = QAPipeline(settings, gateway=StubGateway({"VWO-48": issue})).run(["VWO-48"])

    assert run.successful
    retry_prompt = descriptions[-1]
    assert "incomplete transmission" in retry_prompt
    assert "Return the SAME object again, complete" in retry_prompt
    assert "MUST be under" not in retry_prompt, (
        "a short truncation must not be given a smaller size target"
    )
