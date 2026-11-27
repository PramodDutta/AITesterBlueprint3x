"""Project (final) - two Playwright builds in, a triaged verdict out.

Everything from 01-07 in one graph:
  01 state     a TypedDict backpack, nodes return only what they changed
  02 pipeline  load -> compare -> ...
  03 branch    skip the LLM entirely when nothing is flaky
  04 loop idea one status is an observation, a pair is a verdict
  05 memory    a checkpointer, which interrupt() requires
  06 human     interrupt() pauses before quarantining
  07 LLM node  Groq classifies WHY it flaked; Python still routes

    venv/bin/python run_build.py 1 && venv/bin/python run_build.py 2
    venv/bin/python Project_FlakyTestFinderFinal.py              # auto-quarantine
    venv/bin/python Project_FlakyTestFinderFinal.py --human      # ask me first
"""
import json
import sys
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from llm import get_llm

BUILDS = Path(__file__).parent / "builds"


class Triage(BaseModel):
    """07 - structured output, so the answer is an enum and not prose."""
    cause: Literal["timing", "test_bug", "product_bug", "environment"]
    reason: str = Field(description="one sentence")


class State(TypedDict, total=False):
    runs: list[dict]
    passed: list[str]
    flaky: list[str]
    broken: list[str]
    triage: Triage
    quarantined: str
    verdict: str


# ---------------------------------------------------------------- nodes
def load_builds(state: State) -> dict:
    runs = [{r["test"]: r["status"] for r in json.loads(p.read_text())["results"]}
            for p in (BUILDS / "build_1.json", BUILDS / "build_2.json")]
    print(f"loaded 2 builds, {len(runs[0])} tests each")
    return {"runs": runs}


def compare(state: State) -> dict:
    """The whole rule: compare the PAIR, never a single status."""
    b1, b2 = state["runs"]
    passed, flaky, broken = [], [], []
    for test in b1:
        pair = (b1[test], b2[test])
        target = (passed if pair == ("passed", "passed")
                  else broken if pair == ("failed", "failed") else flaky)
        target.append(test)
    return {"passed": passed, "flaky": flaky, "broken": broken}


def route_after_compare(state: State) -> Literal["triage", "report"]:
    """03 - no flaky test means no LLM call, and no spend."""
    return "triage" if state["flaky"] else "report"


def triage(state: State) -> dict:
    """07 - Groq says WHY. Python still decides what happens next."""
    b1, b2 = state["runs"]
    test = state["flaky"][0]
    t = get_llm().with_structured_output(Triage).invoke(
        "You triage flaky UI tests. One sentence.\n"
        f"Test: {test}\nBuild 1: {b1[test]}   Build 2: {b2[test]}\n"
        "It asserts the product grid has 6 items after login."
    )
    print(f"groq: {t.cause} - {t.reason}")
    return {"triage": t}


def route_quarantine(state: State) -> Literal["ask_human", "quarantine"]:
    """03 again - the --human flag picks the lane."""
    return "ask_human" if "--human" in sys.argv else "quarantine"


def ask_human(state: State) -> dict:
    """06 - interrupt() freezes the graph until someone answers."""
    answer = interrupt({"question": f"Quarantine {state['flaky'][0]}?",
                        "cause": state["triage"].cause})
    return {"quarantined": state["flaky"][0] if str(answer).lower().startswith("y")
            else ""}


def quarantine(state: State) -> dict:
    return {"quarantined": state["flaky"][0]}


def report(state: State) -> dict:
    b1, b2 = state["runs"]
    rows = [f"{'TEST':<24}{'BUILD 1':<9}{'BUILD 2':<9}VERDICT", "-" * 56]
    label = {t: "PASSED" for t in state["passed"]}
    label.update({t: "FLAKY" for t in state["flaky"]})
    label.update({t: "BROKEN" for t in state["broken"]})
    rows += [f"{t:<24}{b1[t]:<9}{b2[t]:<9}{label[t]}" for t in b1]
    rows += ["", f"{len(state['passed'])} passed, {len(state['flaky'])} flaky, "
                 f"{len(state['broken'])} broken"]
    if state.get("triage"):
        rows.append(f"cause: {state['triage'].cause} - {state['triage'].reason}")
    q = state.get("quarantined")
    rows.append(f"quarantined: {q}" if q else "quarantined: nothing")
    return {"verdict": "\n".join(rows)}


# ---------------------------------------------------------------- graph
builder = StateGraph(State)
for name, fn in [("load_builds", load_builds), ("compare", compare), ("triage", triage),
                 ("ask_human", ask_human), ("quarantine", quarantine), ("report", report)]:
    builder.add_node(name, fn)

builder.add_edge(START, "load_builds")
builder.add_edge("load_builds", "compare")
builder.add_conditional_edges("compare", route_after_compare, ["triage", "report"])
builder.add_conditional_edges("triage", route_quarantine, ["ask_human", "quarantine"])
builder.add_edge("ask_human", "report")
builder.add_edge("quarantine", "report")
builder.add_edge("report", END)

app = builder.compile(checkpointer=InMemorySaver())      # 05 - interrupt needs it

if __name__ == "__main__":
    cfg = {"configurable": {"thread_id": "flaky-final"}}
    out = app.invoke({}, cfg)

    if "__interrupt__" in out:                            # 06 - paused, ask and resume
        q = out["__interrupt__"][0].value
        answer = input(f"\n{q['question']} (cause: {q['cause']}) [y/N]: ")
        out = app.invoke(Command(resume=answer), cfg)

    print(f"\n{out['verdict']}")
