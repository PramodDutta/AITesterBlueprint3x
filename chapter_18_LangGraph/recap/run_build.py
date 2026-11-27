"""Run the Playwright suite and save the result as builds/build_N.json.

    venv/bin/python run_build.py 1     # all 5 green
    venv/bin/python run_build.py 2     # FLAKY_BUILD=2 -> test_products_load fails

JUnit XML is pytest's built-in report, so there is no plugin to install and
xml.etree is stdlib. The JSON it writes is what the agent reads.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
BUILDS = HERE / "builds"
PYTHON = HERE / "venv" / "bin" / "python"


def main(build: str) -> None:
    BUILDS.mkdir(exist_ok=True)
    xml = HERE / f".build_{build}.xml"
    env = {**os.environ, "FLAKY_BUILD": build}
    subprocess.run([str(PYTHON), "-m", "pytest", "pw_tests", "-q", f"--junitxml={xml}"],
                   cwd=HERE, env=env, capture_output=True, text=True)

    results = [
        {"test": tc.get("name").split("[")[0],
         "status": "failed" if any(c.tag in ("failure", "error") for c in tc) else "passed"}
        for tc in ET.parse(xml).getroot().iter("testcase")
    ]
    out = BUILDS / f"build_{build}.json"
    out.write_text(json.dumps({"build": int(build), "results": results}, indent=2))
    xml.unlink()

    passed = sum(r["status"] == "passed" for r in results)
    print(f"build {build}: {passed}/{len(results)} passed -> {out.name}")
    for r in results:
        print(f"   {r['status']:<7} {r['test']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "1")
