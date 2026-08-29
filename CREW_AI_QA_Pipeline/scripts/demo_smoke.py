"""End-to-end smoke test over the local fixtures.

Runs the real four-agent pipeline against ./fixtures with DEMO_MODE forced on,
so it exercises the LLM and every renderer without touching Jira.

    python scripts/demo_smoke.py [TICKET ...]
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jira_qa_crew.config import Settings  # noqa: E402
from jira_qa_crew.models import StageEvent  # noqa: E402
from jira_qa_crew.services.pipeline import QAPipeline  # noqa: E402


def main(tickets: list[str]) -> int:
    # Progress must appear as it happens, including when stdout is redirected
    # to a file, otherwise a long run looks hung.
    sys.stdout.reconfigure(line_buffering=True)
    os.environ["DEMO_MODE"] = "true"
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s - %(message)s")

    settings = Settings.load(ROOT / ".env")
    print(f"model={settings.llm_model} demo={settings.demo_mode} output={settings.output_dir}")
    if not settings.llm_ready():
        print("LLM_API_KEY is not set; cannot run the smoke test.")
        return 2

    def on_progress(key: str, event: StageEvent) -> None:
        print(f"  [{key}] {event.stage.value}: {event.status.value} {event.message[:80]}")

    run = QAPipeline(settings, progress=on_progress).run(tickets)

    print("\n=== RESULT ===")
    print(f"run_id={run.run_id} successful={run.successful}")
    for result in run.results:
        source = result.source.value if result.source else "-"
        print(f"\n{result.ticket_key}: {result.status.value} source={source}")
        if result.error:
            print(f"  error: {result.error}")
        if result.analysis:
            print(
                f"  requirements={len(result.analysis.requirements)} "
                f"acceptance_criteria={len(result.analysis.acceptance_criteria)}"
            )
        if result.test_plan:
            print(
                f"  plan_sections={len(result.test_plan.sections)} "
                f"scenarios={len(result.test_plan.scenarios)}"
            )
        if result.test_cases:
            print(f"  test_cases={len(result.test_cases.test_cases)}")
        if result.playwright:
            print(
                f"  playwright_files={len(result.playwright.files)} "
                f"readiness={result.playwright.readiness.value}"
            )
        if result.coverage:
            print(
                f"  requirement_coverage={result.coverage.requirement_coverage_pct}% "
                f"automation={result.coverage.automation_pct}%"
            )
        for warning in result.warnings[:6]:
            print(f"  warn: {warning}")

    print(f"\nartifacts: {run.output_dir}")
    return 0 if run.successful else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["VWO-48", "VWO-49"]))
