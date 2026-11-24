# Shared memory
# workflow

from typing import TypedDict
from langgraph.graph import END, START, StateGraph

class State(TypedDict):
    tester: str
    greeting: str


def greet(state: State) -> dict:
    return {"greeting": f"Hello {state['tester']}, your first graph ran."}

builder = StateGraph(State)
builder.add_node("greet", greet)

builder.add_edge(START, "greet")
builder.add_edge("greet", END)

app = builder.compile()

if __name__ == "__main__":
    result = app.invoke({"tester": "Pramod"})
    print(result["greeting"])
    print("\nFinal state:", result)
    print("\nThe graph as Mermaid (paste into mermaid.live):")
    print(app.get_graph().draw_mermaid())