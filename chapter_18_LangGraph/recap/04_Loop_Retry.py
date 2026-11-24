from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
MAX_ATTEMPTS = 3


class State(TypedDict):
    test_name: str
    scripted_outcomes: list[str]   # what each attempt will return (simulation)
    attempts: int
    history: list[str]
    verdict: str

def run_test(state: State) -> dict:
    n = state["attempts"]
    outcome = state["scripted_outcomes"][n]
    print(f"   attempt {n + 1}: {outcome}")
    return {"attempts": n + 1, "history": state["history"] + [outcome]}


def should_retry(state: State) -> Literal["run_test", "report"]:
    if state["history"][-1] == "passed":
        return "report"
    if state["attempts"] < MAX_ATTEMPTS:
        return "run_test"          # <- the loop
    return "report"

def report(state: State) -> dict:
    h = state["history"]
    if h[-1] == "passed" and "failed" in h:
        verdict = f"FLAKY: passed on attempt {len(h)} after {h.count('failed')} failure(s)"
    elif h[-1] == "passed":
        verdict = "STABLE PASS"
    else:
        verdict = f"REAL FAILURE: failed all {len(h)} attempts"
    return {"verdict": verdict}


builder = StateGraph(State)
builder.add_node("run_test", run_test)
builder.add_node("report", report)

builder.add_edge(START, "run_test")
builder.add_conditional_edges("run_test", should_retry, ["run_test", "report"])
builder.add_edge("report", END)

app = builder.compile()

if __name__ == "__main__":
    scenarios = {
        "login_redirect (flaky)": ["failed", "failed", "passed"],
        "checkout_pay (broken)": ["failed", "failed", "failed"],
        "cart_total (stable)": ["passed"],
    }
    for name, outcomes in scenarios.items():
        print(name)
        out = app.invoke({"test_name": name, "scripted_outcomes": outcomes,
                          "attempts": 0, "history": [], "verdict": ""})
        print("   =>", out["verdict"], "\n")