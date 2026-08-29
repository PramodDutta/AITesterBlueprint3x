"""Pydantic models: the contract between every pipeline stage.

These are the internal source of truth. Renderers in
:mod:`jira_qa_crew.services.artifacts` turn validated objects into Markdown,
CSV, JSON and TypeScript. Raw LLM Markdown is never used as the source of
truth for anything.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Provenance(StrEnum):
    """Where a piece of information came from.

    The anti-hallucination rules hang off this: anything not EXPLICIT must be
    visibly labelled in the artifacts.
    """

    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"
    MISSING = "MISSING"
    ASSUMPTION_REQUIRING_CONFIRMATION = "ASSUMPTION_REQUIRING_CONFIRMATION"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TestType(StrEnum):
    HAPPY_PATH = "happy_path"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    VALIDATION = "validation"
    ERROR_HANDLING = "error_handling"
    STATE_TRANSITION = "state_transition"
    PERMISSIONS = "permissions"
    DATA_INTEGRITY = "data_integrity"
    API_CONTRACT = "api_contract"
    ACCESSIBILITY = "accessibility"
    CROSS_BROWSER = "cross_browser"
    REGRESSION = "regression"
    RECOVERY = "recovery"


class AutomationCandidate(StrEnum):
    YES = "Yes"
    NO = "No"
    PARTIAL = "Partial"


class AutomationReadiness(StrEnum):
    READY = "READY"
    NEEDS_CONFIGURATION = "NEEDS_CONFIGURATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class JiraSource(StrEnum):
    MCP = "MCP"
    REST = "REST"
    DEMO_FIXTURE = "DEMO_FIXTURE"


class TicketStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class StageName(StrEnum):
    FETCH = "Jira Fetch"
    ANALYSIS = "Jira Analyst"
    TEST_PLAN = "Test Plan Writer"
    TEST_CASES = "Test Case Writer"
    PLAYWRIGHT = "Playwright Coder"
    ARTIFACTS = "Artifacts"


class StageStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WARNING = "WARNING"
    FAILED = "FAILED"


class CoverageStatus(StrEnum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    UNCOVERED = "UNCOVERED"


REQ_ID_RE = re.compile(r"^REQ-\d{3,}$")
AC_ID_RE = re.compile(r"^AC-\d{3,}$")
TC_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+-TC-\d{3,}$")


# --------------------------------------------------------------------------
# Raw Jira issue (produced by the gateway, not by an LLM)
# --------------------------------------------------------------------------


class JiraIssue(BaseModel):
    """A Jira issue normalized to plain text.

    Built deterministically in Python from MCP or REST. The LLM never
    populates this model, so nothing here can be hallucinated.
    """

    key: str
    summary: str = ""
    description: str = ""
    issue_type: str = ""
    status: str = ""
    priority: str = ""
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    parent: str | None = None
    subtasks: list[str] = Field(default_factory=list)
    linked_issues: list[str] = Field(default_factory=list)
    acceptance_criteria_raw: str = ""
    comments: list[str] = Field(default_factory=list)
    url: str = ""
    source: JiraSource = JiraSource.REST
    fetched_at: datetime = Field(default_factory=datetime.now)
    raw_fields: dict[str, Any] = Field(default_factory=dict)

    def to_prompt_text(self) -> str:
        """Flatten to the text handed to the Jira Analyst agent.

        Wrapped in an explicit untrusted-data marker: Jira content is business
        data, never instructions.
        """
        lines = [
            f"Ticket Key: {self.key}",
            f"Summary: {self.summary}",
            f"Issue Type: {self.issue_type or 'not set'}",
            f"Status: {self.status or 'not set'}",
            f"Priority: {self.priority or 'not set'}",
            f"Labels: {', '.join(self.labels) or 'none'}",
            f"Components: {', '.join(self.components) or 'none'}",
            f"Parent: {self.parent or 'none'}",
            f"Subtasks: {', '.join(self.subtasks) or 'none'}",
            f"Linked Issues: {', '.join(self.linked_issues) or 'none'}",
            f"URL: {self.url or 'not available'}",
            "",
            "Description:",
            self.description or "(empty)",
        ]
        if self.acceptance_criteria_raw:
            lines += ["", "Acceptance Criteria field:", self.acceptance_criteria_raw]
        if self.comments:
            lines += ["", "Comments:"]
            lines += [f"- {c}" for c in self.comments]
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Stage 1 - Requirement analysis
# --------------------------------------------------------------------------


class Requirement(BaseModel):
    id: str = Field(description="Stable identifier, e.g. REQ-001")
    text: str
    provenance: Provenance = Provenance.EXPLICIT
    source_quote: str = Field(
        default="", description="Verbatim Jira text supporting this requirement"
    )
    category: str = Field(default="functional")

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        value = value.strip().upper()
        if not REQ_ID_RE.match(value):
            raise ValueError(f"Requirement id must look like REQ-001, got {value!r}")
        return value


class AcceptanceCriterion(BaseModel):
    id: str = Field(description="Stable identifier, e.g. AC-001")
    text: str
    provenance: Provenance = Provenance.EXPLICIT
    source_quote: str = ""
    requirement_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        value = value.strip().upper()
        if not AC_ID_RE.match(value):
            raise ValueError(f"Acceptance criterion id must look like AC-001, got {value!r}")
        return value


class RequirementAnalysis(BaseModel):
    """Validated output of Agent 1."""

    ticket_key: str
    summary: str
    issue_type: str = ""
    status: str = ""
    priority: str = ""
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    parent: str | None = None
    subtasks: list[str] = Field(default_factory=list)
    linked_issues: list[str] = Field(default_factory=list)

    description_summary: str = ""
    requirements: list[Requirement] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    source: JiraSource = JiraSource.REST

    @property
    def requirement_ids(self) -> list[str]:
        return [r.id for r in self.requirements]

    @property
    def acceptance_criteria_ids(self) -> list[str]:
        return [a.id for a in self.acceptance_criteria]


# --------------------------------------------------------------------------
# Stage 2 - Test plan
# --------------------------------------------------------------------------

TEST_PLAN_SECTIONS: tuple[str, ...] = (
    "Executive Summary",
    "Test Objectives",
    "In Scope",
    "Out of Scope",
    "Requirements and Acceptance-Criteria Coverage",
    "Test Strategy, Levels, and Test Types",
    "Test Environment, Tools, and Browser Coverage",
    "Test Data Requirements",
    "High-Level Test Scenarios",
    "Entry and Exit Criteria",
    "Risks, Dependencies, Assumptions, and Mitigations",
    "Execution, Defect Management, Reporting, and Deliverables",
)


class TestPlanSection(BaseModel):
    number: int = Field(ge=1, le=12)
    title: str
    content: str


class TestScenario(BaseModel):
    id: str
    title: str
    description: str = ""
    requirement_ids: list[str] = Field(default_factory=list)
    acceptance_criteria_ids: list[str] = Field(default_factory=list)
    priority: Priority = Priority.P2

    @model_validator(mode="after")
    def _needs_a_trace(self) -> TestScenario:
        if not self.requirement_ids and not self.acceptance_criteria_ids:
            raise ValueError(
                f"Scenario {self.id} must reference at least one REQ-* or AC-* id"
            )
        return self


class TestPlan(BaseModel):
    """Validated output of Agent 2."""

    ticket_key: str
    title: str
    sections: list[TestPlanSection]
    scenarios: list[TestScenario] = Field(default_factory=list)

    @field_validator("sections")
    @classmethod
    def _twelve_sections(cls, sections: list[TestPlanSection]) -> list[TestPlanSection]:
        if len(sections) != 12:
            raise ValueError(
                f"A test plan must have exactly 12 sections, got {len(sections)}"
            )
        numbers = sorted(s.number for s in sections)
        if numbers != list(range(1, 13)):
            raise ValueError(f"Section numbers must be 1..12 exactly once, got {numbers}")
        return sorted(sections, key=lambda s: s.number)


# --------------------------------------------------------------------------
# Stage 3 - Test cases
# --------------------------------------------------------------------------


class TestStep(BaseModel):
    number: int = Field(ge=1)
    action: str
    expected: str = ""


class TestCase(BaseModel):
    id: str = Field(description="e.g. VWO-48-TC-001")
    ticket_key: str
    title: str
    objective: str = ""
    priority: Priority = Priority.P2
    test_type: TestType = TestType.HAPPY_PATH
    requirement_ids: list[str] = Field(default_factory=list)
    acceptance_criteria_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    test_data: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(default_factory=list)
    expected_result: str = ""
    automation_candidate: AutomationCandidate = AutomationCandidate.NO
    automation_rationale: str = ""
    tags: list[str] = Field(default_factory=list)
    assumptions_or_blockers: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        value = value.strip().upper()
        if not TC_ID_RE.match(value):
            raise ValueError(
                f"Test case id must look like VWO-48-TC-001, got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _needs_steps_and_trace(self) -> TestCase:
        if not self.steps:
            raise ValueError(f"Test case {self.id} has no steps")
        if not self.requirement_ids and not self.acceptance_criteria_ids:
            raise ValueError(
                f"Test case {self.id} must trace to at least one REQ-* or AC-* id"
            )
        return self


class TestCaseSuite(BaseModel):
    """Validated output of Agent 3."""

    ticket_key: str
    test_cases: list[TestCase]
    coverage_notes: str = ""

    @model_validator(mode="after")
    def _unique_ids(self) -> TestCaseSuite:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for case in self.test_cases:
            if case.id in seen:
                duplicates.add(case.id)
            seen.add(case.id)
        if duplicates:
            raise ValueError(f"Duplicate test case ids: {sorted(duplicates)}")
        if not self.test_cases:
            raise ValueError("A test case suite must contain at least one test case")
        return self


# --------------------------------------------------------------------------
# Stage 4 - Playwright bundle
# --------------------------------------------------------------------------


class PlaywrightFile(BaseModel):
    path: str = Field(description="Relative path, e.g. tests/vwo-48.spec.ts")
    content: str
    kind: str = Field(default="spec", description="spec | page | fixture")

    @field_validator("path")
    @classmethod
    def _safe_relative_path(cls, value: str) -> str:
        value = value.strip().replace("\\", "/").lstrip("/")
        if not value:
            raise ValueError("Playwright file path must not be empty")
        if ".." in value.split("/"):
            raise ValueError(f"Playwright file path must not traverse upwards: {value!r}")
        if not value.endswith((".ts", ".js")):
            raise ValueError(f"Playwright file must be .ts or .js, got {value!r}")
        return value


class AutomatedTestTrace(BaseModel):
    test_name: str
    test_case_id: str
    ticket_key: str
    requirement_ids: list[str] = Field(default_factory=list)
    acceptance_criteria_ids: list[str] = Field(default_factory=list)
    spec_path: str = ""


class PlaywrightBundle(BaseModel):
    """Validated output of Agent 4."""

    ticket_key: str
    files: list[PlaywrightFile] = Field(default_factory=list)
    traces: list[AutomatedTestTrace] = Field(default_factory=list)
    readiness: AutomationReadiness = AutomationReadiness.NEEDS_CONFIGURATION
    setup_notes: str = ""
    missing_information: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ready_needs_evidence(self) -> PlaywrightBundle:
        if self.readiness is AutomationReadiness.READY and self.missing_information:
            raise ValueError(
                "readiness=READY is not allowed while missing_information is non-empty"
            )
        if self.readiness is not AutomationReadiness.NOT_APPLICABLE and not self.files:
            raise ValueError("A Playwright bundle must contain at least one file")
        if self.readiness is AutomationReadiness.NOT_APPLICABLE and self.traces:
            raise ValueError(
                "readiness=NOT_APPLICABLE means nothing was automated, so there "
                "can be no traces"
            )
        return self


# --------------------------------------------------------------------------
# Traceability and run bookkeeping (computed in Python, never by the LLM)
# --------------------------------------------------------------------------


class TraceabilityRow(BaseModel):
    requirement_id: str
    requirement_text: str = ""
    acceptance_criterion_id: str = ""
    acceptance_criterion_text: str = ""
    test_case_ids: list[str] = Field(default_factory=list)
    automated_test_case_ids: list[str] = Field(default_factory=list)
    coverage_status: CoverageStatus = CoverageStatus.UNCOVERED
    reason: str = ""


class CoverageReport(BaseModel):
    ticket_key: str
    rows: list[TraceabilityRow] = Field(default_factory=list)
    total_requirements: int = 0
    covered_requirements: int = 0
    partially_covered_requirements: int = 0
    uncovered_requirements: int = 0
    total_acceptance_criteria: int = 0
    covered_acceptance_criteria: int = 0
    total_test_cases: int = 0
    automated_test_cases: int = 0
    orphan_requirement_ids: list[str] = Field(default_factory=list)
    orphan_acceptance_criteria_ids: list[str] = Field(default_factory=list)
    orphan_test_case_ids: list[str] = Field(default_factory=list)
    unknown_reference_ids: list[str] = Field(default_factory=list)

    @property
    def requirement_coverage_pct(self) -> float:
        if not self.total_requirements:
            return 0.0
        return round(100.0 * self.covered_requirements / self.total_requirements, 1)

    @property
    def automation_pct(self) -> float:
        if not self.total_test_cases:
            return 0.0
        return round(100.0 * self.automated_test_cases / self.total_test_cases, 1)


class StageEvent(BaseModel):
    stage: StageName
    status: StageStatus = StageStatus.PENDING
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds(), 2)
        return None


class TicketResult(BaseModel):
    """Everything produced for one ticket, successful or not."""

    ticket_key: str
    status: TicketStatus = TicketStatus.PENDING
    source: JiraSource | None = None
    issue: JiraIssue | None = None
    analysis: RequirementAnalysis | None = None
    test_plan: TestPlan | None = None
    test_cases: TestCaseSuite | None = None
    playwright: PlaywrightBundle | None = None
    coverage: CoverageReport | None = None
    stages: list[StageEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str = ""
    artifact_dir: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds(), 2)
        return None

    def stage(self, name: StageName) -> StageEvent:
        for event in self.stages:
            if event.stage is name:
                return event
        event = StageEvent(stage=name)
        self.stages.append(event)
        return event


class RunSummary(BaseModel):
    run_id: str
    requested_keys: list[str] = Field(default_factory=list)
    invalid_inputs: list[str] = Field(default_factory=list)
    duplicates_removed: list[str] = Field(default_factory=list)
    results: list[TicketResult] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_dir: str = ""

    @property
    def completed(self) -> list[TicketResult]:
        return [r for r in self.results if r.status is TicketStatus.COMPLETED]

    @property
    def completed_with_warnings(self) -> list[TicketResult]:
        return [r for r in self.results if r.status is TicketStatus.COMPLETED_WITH_WARNINGS]

    @property
    def failed(self) -> list[TicketResult]:
        return [r for r in self.results if r.status is TicketStatus.FAILED]

    @property
    def successful(self) -> bool:
        """A run succeeds when at least one ticket produced a full artifact set."""
        return bool(self.completed or self.completed_with_warnings)
