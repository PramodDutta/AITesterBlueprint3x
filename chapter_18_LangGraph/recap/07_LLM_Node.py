"""008 - An LLM inside a node, and its answer driving the fork.

The LLM classifies a failure log into a fixed category (structured output, so
it's a real enum, not prose). 

A normal Python router then reads that category
and picks the next node. The model decides, the graph stays in control.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from llm import get_llm

class Triage(BaseModel):
    category: Literal["product_bug", "test_bug", "environment", "flaky"]
    reason: str = Field(description="one sentence")

class State(TypedDict, total=False):
    test_name: str
    log: str
    triage: Triage
    action: str

classifier = get_llm().with_structured_output(Triage)

def classify(state: State) -> dict:
    t = classifier.invoke(
        "You triage failed UI tests. Classify this failure.\n"
        f"Test: {state['test_name']}\nLog:\n{state['log']}"
    )
    return {"triage": t}

def route(state: State) -> str:
    return state["triage"].category

ACTIONS = {
    "product_bug": "file a Jira bug for the dev team",
    "test_bug": "fix the test code (locator / assertion)",
    "environment": "ping DevOps, rerun when the env is healthy",
    "flaky": "quarantine and rerun nightly",
}

def make_action(category):
    return lambda state: {"action": ACTIONS[category]}

builder = StateGraph(State)
builder.add_node("classify", classify)


for cat in ACTIONS:
    builder.add_node(cat, make_action(cat))
    builder.add_edge(cat, END)
builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", route, list(ACTIONS))
app = builder.compile()

FAILURES = [
    ("checkout_pay",
     "AssertionError: expected order total '$120.00' but got '$0.00'. API /cart returned 200 with total=0."),
    ("login_button",
     "TimeoutError: locator('#login-btn') not found. Page has button[data-test=login] instead."),
    ("search_results",
     "net::ERR_CONNECTION_REFUSED at https://staging.example.com - staging DB container restarting."),
]

if __name__ == "__main__":
    for name, log in FAILURES:
        out = app.invoke({"test_name": name, "log": log})
        t = out["triage"]
        print(f"{name:<15} -> {t.category:<12} | {out['action']}")
        print(f"{'':<15}    why: {t.reason}")