"""Compile-check the Playwright specs a run generated.

Copies the generated TypeScript into tools/playwright-check, then runs the
TypeScript compiler and Playwright's collector. Neither opens a browser or
contacts a server, so this is safe to run anywhere.

    python scripts/check_playwright.py outputs/RUN-20260829-103015

Exits non-zero if anything fails to compile or collect. If Node.js is missing
it says so and exits 0, because an absent toolchain is not a code defect.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools" / "playwright-check"


def _node_available() -> bool:
    return shutil.which("npx") is not None and shutil.which("node") is not None


def _collect_specs(run_dir: Path) -> list[Path]:
    return sorted(run_dir.rglob("playwright/**/*.ts"))


def _run(command: list[str]) -> tuple[int, str]:
    process = subprocess.run(  # noqa: S603 - fixed command, no shell, no user input
        command, cwd=HARNESS, capture_output=True, text=True, timeout=300, check=False
    )
    return process.returncode, (process.stdout + process.stderr).strip()


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python scripts/check_playwright.py <run-directory>")
        return 2

    run_dir = Path(argv[0])
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    if not run_dir.exists():
        print(f"run directory not found: {run_dir}")
        return 2

    specs = _collect_specs(run_dir)
    if not specs:
        # A run where nothing was automatable legitimately produces no code.
        # That is not a compilation failure.
        print(f"no generated TypeScript under {run_dir}: nothing to compile")
        return 0
    print(f"found {len(specs)} generated file(s)")

    if not _node_available():
        print("Node.js/npx is not installed, so the generated TypeScript could not be")
        print("compiled or collected. Reporting this honestly rather than claiming it passed.")
        return 0

    for sub in ("tests", "pages", "fixtures"):
        target = HARNESS / sub
        target.mkdir(parents=True, exist_ok=True)
        for stale in target.glob("*.ts"):
            stale.unlink()

    for spec in specs:
        # playwright/<kind>/<name>.ts -> <kind>/<name>.ts
        parts = spec.parts
        kind = parts[parts.index("playwright") + 1] if "playwright" in parts else "tests"
        if kind not in {"tests", "pages", "fixtures"}:
            kind = "tests"
        destination = HARNESS / kind / spec.name
        destination.write_text(spec.read_text())
        print(f"  staged {kind}/{spec.name}")

    if not (HARNESS / "node_modules").exists():
        print("installing the harness dependencies (first run only)...")
        code, output = _run(["npm", "install", "--silent"])
        if code != 0:
            print(f"npm install failed:\n{output}")
            return 1

    failures = 0
    for label, command in (
        ("tsc --noEmit", ["npx", "tsc", "--noEmit"]),
        ("playwright test --list", ["npx", "playwright", "test", "--list"]),
    ):
        code, output = _run(command)
        status = "PASS" if code == 0 else "FAIL"
        print(f"\n[{status}] {label}")
        if output:
            print(output[:4000])
        failures += code != 0

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
