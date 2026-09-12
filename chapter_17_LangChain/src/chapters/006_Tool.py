import ast
import operator

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool          # create custom tools

load_dotenv()

# eval() on text a model produced is arbitrary code execution. This walks the
# parsed expression instead, so only arithmetic can ever run.
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("only arithmetic is allowed")


@tool
def qa_metric_calculator(expression: str) -> str:
    """Calculate a QA metric from an arithmetic expression.

    Use this for pass rate, defect density, automation coverage, defect leakage
    or execution time. Input must be plain arithmetic with no words, for example
    '(438/500)*100' for a pass rate or '18/12' for defects per KLOC.
    """
    try:
        result = _safe_eval(ast.parse(expression, mode="eval").body)
        return f"{round(result, 2)}"
    except Exception:
        return "Error: give me a plain arithmetic expression, e.g. '(438/500)*100'"


agent = create_agent(
    model="google_genai:gemini-flash-lite-latest",
    tools=[qa_metric_calculator],          # list of available tools
    system_prompt=(
        "You are a QA metrics assistant for a test automation team. "
        "Use the qa_metric_calculator tool whenever a number must be computed. "
        "State the formula you used, then the result with its unit."
    ),
)

queries = [
    # maths -> the agent must call the tool
    "We ran 500 regression tests and 438 passed. What is the pass rate?",
    "A module of 12 KLOC has 18 defects. What is the defect density per KLOC?",
    # no maths -> the agent answers directly, no tool call
    "What is the difference between smoke testing and sanity testing?",
]

for q in queries:
    print(f"\nQuestion: {q}")
    result = agent.invoke({"messages": [{"role": "user", "content": q}]})
    print("Agent:", result["messages"][-1].text)
