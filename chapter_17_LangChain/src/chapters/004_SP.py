from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv()

agent = create_agent(
    model="google_genai:gemini-flash-lite-latest",
    system_prompt=(
        "You are a helpful AI assistant specialized in automation testing "
        "and software development. Be clear, concise, and always think step by step."
    ),
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Who are you?"}]
})

print("Agent Response:")
print(result["messages"][-1].content)