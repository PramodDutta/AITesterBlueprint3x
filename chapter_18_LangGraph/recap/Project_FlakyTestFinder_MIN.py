"""Project (minimal) - find the flaky test by comparing two builds.

Everything from 01-04 in one small graph:
  01 state as a backpack, 02 a linear pipeline, 03 a conditional edge,
  04 the idea that a verdict needs more than one run.

Input : builds/build_1.json and builds/build_2.json (10 tests each)
Output: which test is FLAKY, which is BROKEN, which are STABLE

    venv/bin/python Project_FlakyTestFinder_MIN.py
"""
import json
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

BUILDS = Path(__file__).parent / "builds"


class State(TypedDict, total=False):
    runs: list[dict]        # [{test: status}, {test: status}]
    stable: list[str]
    flaky: list[str]
    broken: list[str]
    confirmed: str
    verdict: str


# ---------------------------------------------------------------- nodes
def load_builds(state: State) -> dict:
    """02 - step one of the pipeline: read both build reports."""
    runs = [{r["test"]: r["status"] for r in json.loads(p.read_text())["results"]}
            for p in (BUILDS / "build_1.json", BUILDS / "build_2.json")]
    print(f"loaded {len(runs)} builds, {len(runs[0])} tests each")
    return {"runs": runs}


def compare(state: State) -> dict:
    """02 - step two: one status per test is not a verdict. Two is."""
    b1, b2 = state["runs"]
    stable, flaky, broken = [], [], []
    for test in b1:
        pair = (b1[test], b2[test])
        if pair == ("passed", "passed"):
            stable.append(test)
        elif pair == ("failed", "failed"):
            broken.append(test)
        else:
            flaky.append(test)          # passed once, failed once
    return {"stable": stable, "flaky": flaky, "broken": broken}


def route(state: State) -> Literal["confirm_flaky", "report"]:
    """03 - the conditional edge: only rerun when there is something to rerun."""
    return "confirm_flaky" if state["flaky"] else "report"


def confirm_flaky(state: State) -> dict:
    """04 - a third run breaks the tie. Dummy Playwright, no network needed."""
    from playwright.sync_api import sync_playwright

    test = state["flaky"][0]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content("<h1 id='total'>Total: $17.27</h1>")   # stands in for the app
        passed = page.locator("#total").inner_text() == "Total: $17.27"
        browser.close()
    print(f"rerun of {test}: {'passed' if passed else 'failed'}")
    return {"confirmed": f"{test} passed on rerun 3 -> FLAKY, not broken"}


def report(state: State) -> dict:
    """Every test, both builds, and the label the comparison earned it."""
    b1, b2 = state["runs"]
    label = {t: "STABLE" for t in state["stable"]}
    label.update({t: "FLAKY" for t in state["flaky"]})
    label.update({t: "BROKEN" for t in state["broken"]})

    rows = [f"{'TEST':<32} {'BUILD 1':<8} {'BUILD 2':<8} VERDICT",
            "-" * 64]
    for test in b1:
        rows.append(f"{test:<32} {b1[test]:<8} {b2[test]:<8} {label[test]}")

    rows += ["", f"{len(state['stable'])} stable, "
                 f"{len(state['flaky'])} flaky, {len(state['broken'])} broken"]
    if state.get("confirmed"):
        rows.append(state["confirmed"])
    return {"verdict": "\n".join(rows)}


# ---------------------------------------------------------------- graph
builder = StateGraph(State)
builder.add_node("load_builds", load_builds)
builder.add_node("compare", compare)
builder.add_node("confirm_flaky", confirm_flaky)
builder.add_node("report", report)

builder.add_edge(START, "load_builds")
builder.add_edge("load_builds", "compare")
builder.add_conditional_edges("compare", route, ["confirm_flaky", "report"])
builder.add_edge("confirm_flaky", "report")
builder.add_edge("report", END)

app = builder.compile()

if __name__ == "__main__":
    out = app.invoke({})
    print(f"\n{out['verdict']}")
    print("\n--- the graph ---")
    print(app.get_graph().draw_mermaid())
