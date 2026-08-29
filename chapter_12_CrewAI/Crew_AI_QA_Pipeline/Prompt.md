"""
CrewAI + Jira MCP: Auto-Generate Test Plans, Test Cases & Playwright Scripts
─────────────────────────────────────────────────────────────────────────────
Input  : A Jira ticket ID (e.g., VWO-48)
Output : test_plan.md, test_cases.md, playwright_tests.md

Pipeline:
  1. Jira Analyst       → fetches ticket via MCP, extracts requirements
  2. Test Plan Writer   → writes complete test plan (12 sections)
  3. Test Case Writer   → writes detailed test cases table
  4. Playwright Coder   → generates automation scripts
"""