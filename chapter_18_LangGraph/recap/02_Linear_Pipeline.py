from typing import TypedDict
from langgraph.graph import END, START, StateGraph

class State(TypedDict, total=False):
    test_name: str
    browser: str
    status: str
    cleaned_up: bool



def setup(state: State) -> dict:
    # 
    return {"browser": "chromium"}

def execute(state: State) -> dict:
    return {"status": "passed"}

def teardown(state: State) -> dict:
    return {"cleaned_up": True}

builder = StateGraph(State)
builder.add_node("setup", setup)
builder.add_node("execute", execute)
builder.add_node("teardown", teardown)


builder.add_edge(START, "setup")
builder.add_edge("setup", "execute")
builder.add_edge("execute", "teardown")
builder.add_edge("teardown", END)


app = builder.compile()

if __name__ == "__main__":
    for step in app.stream({"test_name": "login_works"}, stream_mode="updates"):
        for node, update in step.items():
            print(f"{node:<9} changed -> {update}")

    print("\nFinal state:", app.invoke({"test_name": "login_works"}))