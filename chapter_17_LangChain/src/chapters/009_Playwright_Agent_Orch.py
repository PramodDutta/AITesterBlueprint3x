import asyncio
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_groq import ChatGroq
from playwright_tools import PLAYWRIGHT_TOOLS
import os

load_dotenv()

llm = ChatGroq(model=os.getenv("LLM_MODEL"), temperature=1)

SYSTEM_PROMPT="""
You are an automation testing agent that controls a real browser
using Playwright.

Rules:
1. Always start by launching the browser before performing any action.
2. Perform the actions in the order they are requested.
3. Use clear CSS selectors to interact with elements on the page.
4. Take a screenshot before closing the browser to capture the final state.
5. At the end, report every step you took and whether the test PASSED or FAILED."""

TASK = """ Test the login functionality on https://app.thetestingacademy.com/playwright/ttacart/
1. Launch the browser
2. Navigate to the login page
3. Enter the username "standard_user"
4. Enter the password "tta_secret"
5. Click the login button
6. Close the browser
"""

async def main():
   
    agent = create_agent(
        model=llm,
        tools=PLAYWRIGHT_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )

    # Playwright's async API needs ainvoke: every tool call runs on the same event loop
    result = await agent.ainvoke({"messages": [{"role": "user", "content": TASK}]})

    # Show each tool call and what the browser answered
    print("\n===== Steps taken =====")
    for msg in result["messages"]:
        if msg.type == "ai" and msg.tool_calls:
            for call in msg.tool_calls:
                print(f"-> {call['name']}({call['args']})")
        elif msg.type == "tool":
            print(f"   {msg.content}")

    print("\n===== Final Result =====")
    print(result["messages"][-1].text)   # .text joins the reply's text blocks


asyncio.run(main())