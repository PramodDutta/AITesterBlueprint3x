"""005 - Memory with a checkpointer.

Compile with a checkpointer and pass a thread_id. 
Each thread keeps its own state between invoke() calls, like separate test sessions. 
Swap InMemorySaver for a SQLite or Postgres saver and it survives restarts.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

class State(TypedDict):
    runs: Annotated[list[str], operator.add]


def record_run(state: State) -> dict:
    return {"runs": [f"run #{len(state.get('runs', [])) + 1}"]}

builder = StateGraph(State)
builder.add_node("record_run", record_run)
builder.add_edge(START, "record_run")
builder.add_edge("record_run", END)

app = builder.compile(checkpointer=InMemorySaver())

if __name__ == "__main__":
    nightly = {"configurable": {"thread_id": "nightly-regression"}}
    smoke = {"configurable": {"thread_id": "smoke"}}

    app.invoke({"runs": []}, nightly)
    app.invoke({"runs": []}, nightly)
    out = app.invoke({"runs": []}, nightly)
    print("nightly-regression remembers:", out["runs"])

    out = app.invoke({"runs": []}, smoke)
    print("smoke is separate:           ", out["runs"])

    snap = app.get_state(nightly)
    print("\nget_state(nightly).values:", snap.values)
    print("checkpoints saved for nightly:", len(list(app.get_state_history(nightly))))