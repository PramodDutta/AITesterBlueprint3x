"""Deterministic traceability and coverage.

Coverage numbers are computed in Python from the validated objects. An agent
is never asked how well it covered the requirements, because an agent has an
obvious incentive to say "fully".
"""

from __future__ import annotations

from ..models import (
    AutomationCandidate,
    CoverageReport,
    CoverageStatus,
    PlaywrightBundle,
    RequirementAnalysis,
    TestCaseSuite,
    TraceabilityRow,
)


def build_coverage(
    analysis: RequirementAnalysis,
    suite: TestCaseSuite | None,
    bundle: PlaywrightBundle | None = None,
) -> CoverageReport:
    """Map requirements and acceptance criteria onto test cases and automation."""
    cases = list(suite.test_cases) if suite else []
    req_ids = {r.id for r in analysis.requirements}
    ac_ids = {a.id for a in analysis.acceptance_criteria}
    req_text = {r.id: r.text for r in analysis.requirements}
    ac_text = {a.id: a.text for a in analysis.acceptance_criteria}

    automated_case_ids = {t.test_case_id.strip().upper() for t in (bundle.traces if bundle else [])}
    intended_automation = {
        c.id
        for c in cases
        if c.automation_candidate in (AutomationCandidate.YES, AutomationCandidate.PARTIAL)
    }

    cases_by_req: dict[str, list[str]] = {r: [] for r in req_ids}
    cases_by_ac: dict[str, list[str]] = {a: [] for a in ac_ids}
    unknown_refs: set[str] = set()

    for case in cases:
        for rid in case.requirement_ids:
            key = rid.strip().upper()
            if key in cases_by_req:
                cases_by_req[key].append(case.id)
            else:
                unknown_refs.add(key)
        for aid in case.acceptance_criteria_ids:
            key = aid.strip().upper()
            if key in cases_by_ac:
                cases_by_ac[key].append(case.id)
            else:
                unknown_refs.add(key)

    # Acceptance criteria inherit onto the requirements they verify.
    ac_by_req: dict[str, list[str]] = {r: [] for r in req_ids}
    for criterion in analysis.acceptance_criteria:
        for rid in criterion.requirement_ids:
            key = rid.strip().upper()
            if key in ac_by_req:
                ac_by_req[key].append(criterion.id)
            else:
                unknown_refs.add(key)

    rows: list[TraceabilityRow] = []
    covered_reqs = partial_reqs = 0

    for requirement in analysis.requirements:
        linked_acs = ac_by_req.get(requirement.id, [])
        row_specs = (
            [(ac, ac_text.get(ac, "")) for ac in linked_acs] if linked_acs else [("", "")]
        )

        req_case_ids: set[str] = set(cases_by_req.get(requirement.id, []))
        for ac_id, _ in row_specs:
            if ac_id:
                req_case_ids.update(cases_by_ac.get(ac_id, []))

        for ac_id, ac_body in row_specs:
            row_cases = sorted(
                set(cases_by_req.get(requirement.id, []))
                | set(cases_by_ac.get(ac_id, []) if ac_id else [])
            )
            row_automated = sorted(c for c in row_cases if c in automated_case_ids)
            status, reason = _status_for(
                row_cases, row_automated, intended_automation, bundle
            )
            rows.append(
                TraceabilityRow(
                    requirement_id=requirement.id,
                    requirement_text=req_text.get(requirement.id, ""),
                    acceptance_criterion_id=ac_id,
                    acceptance_criterion_text=ac_body,
                    test_case_ids=row_cases,
                    automated_test_case_ids=row_automated,
                    coverage_status=status,
                    reason=reason,
                )
            )

        overall_cases = sorted(req_case_ids)
        overall_automated = sorted(c for c in overall_cases if c in automated_case_ids)
        overall_status, _ = _status_for(
            overall_cases, overall_automated, intended_automation, bundle
        )
        if overall_status is CoverageStatus.COVERED:
            covered_reqs += 1
        elif overall_status is CoverageStatus.PARTIAL:
            partial_reqs += 1

    # Acceptance criteria that are not attached to any requirement still need a row.
    orphan_acs = [
        a.id
        for a in analysis.acceptance_criteria
        if not any(r.strip().upper() in req_ids for r in a.requirement_ids)
    ]
    for ac_id in orphan_acs:
        row_cases = sorted(set(cases_by_ac.get(ac_id, [])))
        row_automated = sorted(c for c in row_cases if c in automated_case_ids)
        status, reason = _status_for(row_cases, row_automated, intended_automation, bundle)
        rows.append(
            TraceabilityRow(
                requirement_id="(unlinked)",
                requirement_text="",
                acceptance_criterion_id=ac_id,
                acceptance_criterion_text=ac_text.get(ac_id, ""),
                test_case_ids=row_cases,
                automated_test_case_ids=row_automated,
                coverage_status=status,
                reason=reason or "Acceptance criterion is not linked to any requirement",
            )
        )

    covered_acs = sum(1 for a in ac_ids if cases_by_ac.get(a))
    orphan_cases = [
        c.id
        for c in cases
        if not any(r.strip().upper() in req_ids for r in c.requirement_ids)
        and not any(a.strip().upper() in ac_ids for a in c.acceptance_criteria_ids)
    ]

    return CoverageReport(
        ticket_key=analysis.ticket_key,
        rows=rows,
        total_requirements=len(req_ids),
        covered_requirements=covered_reqs,
        partially_covered_requirements=partial_reqs,
        uncovered_requirements=len(req_ids) - covered_reqs - partial_reqs,
        total_acceptance_criteria=len(ac_ids),
        covered_acceptance_criteria=covered_acs,
        total_test_cases=len(cases),
        automated_test_cases=len([c for c in cases if c.id in automated_case_ids]),
        orphan_requirement_ids=sorted(r for r in req_ids if not cases_by_req.get(r)),
        orphan_acceptance_criteria_ids=sorted(a for a in ac_ids if not cases_by_ac.get(a)),
        orphan_test_case_ids=sorted(orphan_cases),
        unknown_reference_ids=sorted(unknown_refs),
    )


def _status_for(
    case_ids: list[str],
    automated_ids: list[str],
    intended_automation: set[str],
    bundle: PlaywrightBundle | None,
) -> tuple[CoverageStatus, str]:
    """Coverage verdict for one row, with the reason spelled out."""
    if not case_ids:
        return CoverageStatus.UNCOVERED, "No test case references this item"

    wanted = [c for c in case_ids if c in intended_automation]
    if not wanted:
        return CoverageStatus.COVERED, "Covered by manual test cases"

    missing = [c for c in wanted if c not in automated_ids]
    if missing:
        return (
            CoverageStatus.PARTIAL,
            "Test cases exist but automation is missing for: " + ", ".join(missing),
        )
    if bundle and bundle.missing_information:
        return (
            CoverageStatus.PARTIAL,
            "Automated, but the script is not execution-ready: "
            + "; ".join(bundle.missing_information[:2]),
        )
    return CoverageStatus.COVERED, "Covered by automated and manual test cases"
