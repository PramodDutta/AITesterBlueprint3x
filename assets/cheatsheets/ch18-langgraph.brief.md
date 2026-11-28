Act as an expert educational infographic designer, technical instructor, and senior
software engineer with 15+ years of experience.

Convert the supplied technical topic and source code into a professional, handwritten
educational cheat sheet that looks like structured notes made on an iPad with an Apple
Pencil.

CANVAS      1920x1080, 16:9 landscape, clean white background, subtle paper texture.
            Consistent margins. No iPad, hands, desk or pencil in frame.

INK         Dark navy #102040 for headings and text.
            Sky blue #3399EE for borders, arrows, numbering, highlights.
            Pale blue #E5F3FF behind code blocks and heading highlights.

STYLE       Natural, normal-weight, highly readable handwriting. Slightly imperfect
            hand-drawn outlines, thin rounded rectangles, hand-drawn arrows, small
            numbered circles, minimal technical icons. Not bold, thick, childish or
            cursive. No gradients or drop shadows. Real teaching notes, not a slide.

LAYOUT      Header with large title, short subtitle, blue underline.
            Then 6-8 numbered panels over two rows, sized to their content:
              1 What is it          simple definition, 2-4 bullets
              2 Why do we need it   the problem it solves
              3 Core building blocks  components and how they relate
              4 How it works        hand-drawn architecture diagram or flowchart
              5 Code implementation the real snippet, pale blue background
              6 Step-by-step        the actual execution order of THIS code
              7 Examples and output realistic QA / SDET example
              8 Best practices      mistakes, limits, interview-worthy points
            Full-width "Key Takeaway" strip at the bottom.
            Bottom-right branding, small and subtle:
              The Testing Academy  /  https://thetestingacademy.com/

AUDIENCE    Manual testers, automation testers, QA engineers, SDETs and developers
            new to AI engineering. Beginner-friendly English, technically accurate.

CODE RULES  Preserve syntax, names, indentation, brackets and operators exactly.
            Invent no methods, libraries or APIs. Never mix Python and TypeScript
            syntax in one block. Label shortened code as an excerpt. Show no API keys
            or credentials. Claim no execution result that was not actually observed.

DIAGRAMS    For agent topics show only components that exist in the implementation:
            input, state, LLM, node, router, conditional edge, checkpointer, tools,
            output. Short readable labels on every arrow. Arrows point the right way.

CHECK       Spelling correct, no overlapping text, nothing cropped, readable at
            YouTube scale, no fabricated statistics or results.

Output the finished image, not a description.

================================================================================
INPUT
================================================================================

TOPIC
  Chapter 18 - LangGraph for QA: finding the flaky test
  Subtitle: "One test run is an observation. Two is a verdict."

WHAT TO TEACH
  A LangGraph agent reads two Playwright build reports, compares each test's PAIR
  of statuses, asks Groq why the flaky one flaked, then quarantines it either
  automatically or after pausing to ask a human.

CORE BUILDING BLOCKS (panel 3) - show these five, no others
  State        a TypedDict passed between nodes; a node returns ONLY the keys it
               changed and LangGraph merges them in
  Node         a plain Python function
  Edge         add_edge always runs; add_conditional_edges picks the next node
  Checkpointer InMemorySaver; required because interrupt() must save the pause
  interrupt()  freezes the graph and hands a question back to the caller

ARCHITECTURE (panel 4) - this is the real graph, do not add components
  START -> load_builds -> compare -> {conditional}
      conditional, no flaky test  -> report
      conditional, flaky found    -> triage  (Groq, structured output)
  triage -> {conditional}
      with --human  -> ask_human (interrupt, pauses) -> report
      auto          -> quarantine                    -> report
  report -> END
  Label the two dotted conditional edges. Mark the checkpointer on ask_human.

THE CLASSIFICATION RULE (panel 1 or 3, this is the core idea)
  ("passed", "passed") -> STABLE   trust it
  ("failed", "failed") -> BROKEN   the APP is wrong
  anything else        -> FLAKY    the TEST is wrong

CODE (panel 5) - Python, reproduce exactly, label as an excerpt
---
def compare(state: State) -> dict:
    """The whole rule: compare the PAIR, never a single status."""
    b1, b2 = state["runs"]
    passed, flaky, broken = [], [], []
    for test in b1:
        pair = (b1[test], b2[test])
        target = (passed if pair == ("passed", "passed")
                  else broken if pair == ("failed", "failed") else flaky)
        target.append(test)
    return {"passed": passed, "flaky": flaky, "broken": broken}

def route_after_compare(state: State) -> Literal["triage", "report"]:
    return "triage" if state["flaky"] else "report"
---

EXAMPLE OUTPUT (panel 7) - this is a REAL observed run, reproduce the numbers
---
TEST                    BUILD 1  BUILD 2  VERDICT
test_valid_login        passed   passed   PASSED
test_invalid_password   passed   passed   PASSED
test_empty_username     passed   passed   PASSED
test_locked_out_user    passed   passed   PASSED
test_products_load      passed   failed   FLAKY

4 passed, 1 flaky, 0 broken
cause: timing - the test checks the product grid before the async load completes
quarantined: test_products_load
---

BEST PRACTICES / MISTAKES (panel 8)
  - Two builds only SUSPECT flakiness. A test failing 1 run in 20 looks stable in
    both, and ("passed","failed") equals ("failed","passed").
  - Put the LLM behind the conditional edge: a clean build should cost zero tokens.
  - The LLM explains WHY; Python still decides WHAT HAPPENS. Never let the model
    choose whether to quarantine.
  - interrupt() needs a checkpointer and the SAME thread_id to resume.

KEY TAKEAWAY STRIP (full width, bottom)
  Compare the pair -> Groq explains why -> Python routes -> quarantine or ask a human

ADDITIONAL
  Use QA language throughout: builds, test runs, quarantine, flaky, triage.
  Panel 6 should walk the real execution order: load both JSON reports ->
  pair the statuses -> branch -> Groq triage -> branch on --human -> report.
