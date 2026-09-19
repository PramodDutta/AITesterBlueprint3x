import asyncio
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_deepseek import ChatDeepSeek
from playwright_tools import PLAYWRIGHT_TOOLS
import os

load_dotenv()

# The .env calls the key DEEPSEEK_API, but the SDK looks for DEEPSEEK_API_KEY,
# so it has to be passed in explicitly.
llm = ChatDeepSeek(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
    api_key=os.environ["DEEPSEEK_API"],
    temperature=0,
)

SYSTEM_PROMPT="""
You are an end-to-end automation testing agent that controls a real browser
using Playwright.

Rules:
1. Always call launch_browser FIRST, before any other action.
2. Call snapshot_page whenever you land on a new page. It returns every role and
   name on that page, so you never have to guess a selector.
3. Prefer click_by_role and type_by_label over raw CSS. This app also exposes
   stable [data-test="..."] attributes if you need a CSS selector.
4. Verify as you go with assert_visible and assert_text_contains. Do not assume
   a step worked because the previous tool call returned no error.
5. Never invent a value you were not given, and never report a price you did not
   actually read off the page.
6. Before closing, call get_console_errors and take_screenshot.
7. Report every step, every assertion with its PASS/FAIL, and one final verdict:
   TEST PASSED or TEST FAILED."""

TASK = """Run the full end-to-end purchase flow on TTACart and verify the order completes.

Site:     https://app.thetestingacademy.com/playwright/ttacart/
Username: standard_user
Password: tta_secret

Steps:
 1. Launch the browser and navigate to the site.
 2. Log in with the credentials above.
 3. VERIFY you land on the products page (URL ends in /inventory, heading "Products").
 4. Add the FIRST product to the cart. It is "Test.allTheThings() T-Shirt (Red)" at $15.99.
    Record its price, you will need it in step 8.
 5. VERIFY the cart badge in the header now shows 1.
 6. Open the shopping cart and VERIFY the T-shirt is listed with quantity 1.
 7. Click "Checkout", then fill in the customer details:
    First Name "Pramod", Last Name "Dutta", Zip/Postal Code "560001", and click "Continue".
 8. You are now on "Checkout: Overview". Read the price block and VERIFY the maths:
    Item total ($15.99) + Tax ($1.28) must equal the Total ($17.27).
    Use the qa arithmetic in your head, and report all three numbers you actually read.
 9. Click "Finish" to place the order.
10. VERIFY the confirmation page: URL ends in /checkout-complete and the page shows
    the heading "Thank you for your order!".
11. Check the console for JavaScript errors, take a screenshot named "order_complete.png",
    then close the browser.

Report a PASS or FAIL for every VERIFY step above, then the final verdict.
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