from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain.agents import create_agent

load_dotenv()

# 1) Define the response schema with Pydantic
class TestCase(BaseModel):
    title: str
    description: str
    steps: list[str]
    expected_result: str
    priority: Literal["High", "Medium", "Low"]
    tags: list[str]

class TestCaseList(BaseModel):
    # Tip: always wrap arrays inside an object (better compatibility, especially with Anthropic)
    test_cases: list[TestCase]

# 2) Create the agent with response_format
agent = create_agent(
    model="google_genai:gemini-flash-lite-latest",
    # model="anthropic:claude-haiku-4-5",     # optional
    system_prompt=(
        "You are a senior automation testing engineer. Always return test cases "
        "in the exact structured JSON format requested. Be detailed and professional."
    ),
    response_format=TestCaseList,             # enforce the schema on the final output
)

# 3) Provide a user story and invoke the agent
user_story = ("As a logged-in user, I want to add items to my shopping cart "
              "so that I can purchase them later.")

result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": f"Generate 2 detailed test cases for this user story: {user_story}",
    }]
})

# 4) Work with the structured result: no manual parsing
print("=== Structured Output ===")
test_cases = result["structured_response"].test_cases
for tc in test_cases:
    print(tc.model_dump_json(indent=2))

print(f"\nSuccessfully generated {len(test_cases)} test cases!")