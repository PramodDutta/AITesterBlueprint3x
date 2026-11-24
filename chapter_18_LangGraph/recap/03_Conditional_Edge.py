from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

class State(TypedDict, total=False):
    test_name: str
    status: str          # passed | failed | flaky
    action: str

def read_result(state: State) -> dict:
    return {}            # in real life: parse a Playwright report here


def route_by_status(state: State) -> Literal["log_pass", "file_bug", "quarantine"]:
    return {"passed": "log_pass", "failed": "file_bug"}.get(state["status"], "quarantine")


def log_pass(state: State) -> dict:
    return {"action": "logged as green"}


def file_bug(state: State) -> dict:
    return {"action": f"Jira bug filed for {state['test_name']}"}


def quarantine(state: State) -> dict:
    return {"action": f"{state['test_name']} moved to quarantine, rerun nightly"}



builder = StateGraph(State)
builder.add_node("read_result", read_result)
builder.add_node("log_pass", log_pass)
builder.add_node("file_bug", file_bug)
builder.add_node("quarantine", quarantine)

builder.add_edge(START, "read_result")
builder.add_conditional_edges("read_result", route_by_status,
                              ["log_pass", "file_bug", "quarantine"])


for leaf in ("log_pass", "file_bug", "quarantine"):
    builder.add_edge(leaf, END)

app = builder.compile()

if __name__ == "__main__":
    for name, status in [("cart_total", "passed"),
                         ("checkout_pay", "failed"),
                         ("login_redirect", "flaky")]:
        out = app.invoke({"test_name": name, "status": status})
        print(f"{name:<15} {status:<7} -> {out['action']}")

    # print("\n" + app.get_graph().draw_mermaid())