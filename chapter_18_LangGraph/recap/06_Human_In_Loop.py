"""007 - Human in the loop: pause the graph and ask before doing something risky.

interrupt(payload) freezes the graph and hands `payload` to the caller.
You resume it later with Command(resume=answer) on the SAME thread_id.
A checkpointer is required: the pause has to be saved somewhere.

    python 007_Human_In_The_Loop.py        # asks you
    python 007_Human_In_The_Loop.py yes    # answers for you (CI / demos)
"""
import sys
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict, total=False):
    flaky_tests: list[str]
    approved: bool
    outcome: str

def detect(state: State) -> dict:
    return {"flaky_tests": ["login_redirect", "search_autocomplete"]}

def ask_approval(state: State) -> dict:
    answer = interrupt({
        "question": "Quarantine these tests? (yes/no)",
        "tests": state["flaky_tests"],
    })
    return {"approved": str(answer).strip().lower() in ("y", "yes")}

def route(state: State) -> Literal["quarantine", "skip"]:
    return "quarantine" if state["approved"] else "skip"


def quarantine(state: State) -> dict:
    return {"outcome": f"quarantined {len(state['flaky_tests'])} tests"}


def skip(state: State) -> dict:
    return {"outcome": "left as is, nothing changed"}


builder = StateGraph(State)
builder.add_node("detect", detect)
builder.add_node("ask_approval", ask_approval)
builder.add_node("quarantine", quarantine)
builder.add_node("skip", skip)


builder.add_edge(START, "detect")
builder.add_edge("detect", "ask_approval")
builder.add_conditional_edges("ask_approval", route, ["quarantine", "skip"])
builder.add_edge("quarantine", END)
builder.add_edge("skip", END)

app = builder.compile(checkpointer=InMemorySaver())

if __name__ == "__main__":
    cfg = {"configurable": {"thread_id": "flaky-review-1"}}

    first = app.invoke({}, cfg)
    pause = first["__interrupt__"][0].value
    print("Graph paused. It is asking:")
    print(" ", pause["question"])
    for t in pause["tests"]:
        print("   -", t)
    print("Paused before node:", app.get_state(cfg).next)

    answer = sys.argv[1] if len(sys.argv) > 1 else input("\nYour answer: ")
    final = app.invoke(Command(resume=answer), cfg)
    print("\nResumed with", repr(answer), "->", final["outcome"])