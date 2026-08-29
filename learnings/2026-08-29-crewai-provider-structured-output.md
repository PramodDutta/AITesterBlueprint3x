# Making a CrewAI pipeline survive a provider that can't enforce JSON schemas

**Date:** 2026-08-29
**Where:** `CREW_AI_QA_Pipeline/` (Jira QA Crew, four-agent Streamlit app)

## The problem, in one line

A four-stage CrewAI pipeline using `output_pydantic` worked on stage 1 and died
on stage 2 against DeepSeek, first with HTTP 400, then with empty completions.

## The approach

1. **Read the actual API error instead of guessing.** The 400 said *"This
   response_format type is unavailable now"*. A direct probe of every model on
   the key settled it: DeepSeek accepts `response_format: json_object` and
   rejects `json_schema` outright. Not a schema-complexity problem, not a
   prompt problem: an unsupported feature.

2. **Explain the stage-1 anomaly before building on it.** Stage 1 passed while
   stage 2 failed. The difference was that the analyst agent has a tool, and
   CrewAI does not send `response_format` when tools are present. Without that
   explanation the fix would have been aimed at the wrong stage.

3. **Build a degradation ladder, not a flag.** Three rungs: provider-enforced
   schema → `json_object` + schema in the prompt → free text + schema in the
   prompt. A rung that gets rejected is never requested again in that run.
   The crucial invariant: *enforcement* degrades, **validation never does** —
   every rung ends at the same `model_validate`.

4. **Then the empty completions.** A direct call with the same task succeeded
   6/6 in ~20s, but the same stage through CrewAI returned empty. The
   difference was prompt size: CrewAI's `Task.context` forwards the **full raw
   text** of every upstream task, so by stage 3 the prompt carried the entire
   analysis and plan JSON, source quotes and all.

5. **Replace raw context with a compact handoff rendered from the validated
   object.** 40-70% smaller, cannot contain anything validation rejected, and
   it lists exactly the ids the next stage may reference. The Playwright stage
   is sent only the cases marked for automation.

## The judgment calls

- **Did NOT treat every 400 as a schema problem.** `schema_rejected()` requires
  both an error-shape marker and a schema-specific marker, so a 429 or a 401
  can never silently downgrade enforcement. There is a test for exactly that.

- **Did NOT force `json_object` on the tool-using agent.** A tool call is not a
  JSON object; forcing the format would break the agent loop. The rung is
  skipped when the agent has tools.

- **Did NOT keep both `context` and the handoff.** Sending the same information
  twice is worse than either alone. The pipeline sets `task.context = []` when
  it injects a handoff, and the code says why.

- **Did NOT switch models to make the failure go away.** `deepseek-v4-pro` was
  no more reliable than `flash` on the probe (3/3 each), which proved the
  problem was ours, not the model tier.

- **Believed the failing test over my own code.** A test asserting `"title"` was
  gone from a compacted schema failed, and it was right: my compaction was
  deleting real fields *named* `title`, because inside `properties` the dict
  keys are field names, not schema keywords.

## The reusable rules

> When a provider rejects a request, probe the feature directly before changing
> your code. "Which of these four calls does this API accept?" is a two-minute
> experiment that replaces an hour of guessing.

> Degrade enforcement, never validation. A fallback path that also relaxes the
> checks is not a fallback, it is a silent quality drop.

> In a multi-stage agent pipeline, never forward raw upstream text. Hand the
> next stage a compact summary rendered from the validated object: it is
> smaller, and it cannot carry anything the schema already rejected.
