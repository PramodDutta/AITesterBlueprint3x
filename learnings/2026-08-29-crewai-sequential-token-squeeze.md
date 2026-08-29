# CrewAI sequential crews: the token squeeze that truncates your last agent

**Date:** 2026-08-29
**Where:** `chapter_12_CrewAI/04_Build_QABugTriageCrew_Prod.py`

## The problem, in one line

A 3-agent sequential CrewAI crew on a Groq free-tier key kept returning reports
that stopped mid-sentence, and the later the agent, the worse the truncation.

## The approach

1. **Read the error, not the symptom.** Raising `max_tokens=8000` turned the
   silent truncation into a loud `413`: *"Limit 8000, Requested 10421"*. That
   error is the whole diagnosis: the free-tier cap is on **prompt + max_tokens
   together, per request**, not on output alone.

2. **Realize the prompt GROWS at every stage.** In a sequential crew, task 2
   receives task 1's output as `context`, and task 3 receives both. So the
   agent with the most to write has the least room to write it. Rough shape:

   ```
   agent 1 prompt ~2.3k  ->  5.7k spare for output
   agent 2 prompt ~3.0k  ->  5.0k spare
   agent 3 prompt ~4.8k  ->  3.2k spare   <- the one that got cut
   ```

3. **Check whether the ceiling is escapable before engineering around it.**
   Queried every model on the key via `/models` plus a 1-token probe reading
   the `x-ratelimit-limit-tokens` header. All five: 8000. Not escapable by
   switching models, so it had to be budgeted.

4. **Budget per agent, not globally.** `LLM` is shared by default, so one
   `max_tokens` fits nobody. Built a `make_llm(...)` factory and gave each
   agent its own instance with its own budget, ordered by how big its prompt
   will be.

5. **Also cap the upstream agents' verbosity.** A wordy agent 1 steals room
   from agent 3. Added HARD LIMIT word counts to each `expected_output`, with
   the reason stated in the prompt ("every word you spend costs them room"),
   plus "a complete short report beats a truncated long one."

6. **Add a fallback provider, then discover the fallback was inert.** DeepSeek
   was wired in as a parachute via a wrapper class. It never fired, because
   DeepSeek's failure mode is not an exception: it returns an **empty string**,
   and CrewAI only blows up several steps later with `Invalid response from LLM
   call - None or empty`. Fixed by treating an empty/whitespace response as a
   failure inside the wrapper, exactly like a raised exception.

## The judgment calls

- **Did NOT subclass `crewai.LLM`.** It is a factory: it returns a
  provider-specific object (`OpenAICompletion`), so a subclass silently loses
  your added fields. Wrapped `BaseLLM` and delegated instead
  (`call`, `supports_stop_words`, `supports_function_calling`,
  `get_context_window_size`). Verified with a 2-line throwaway script BEFORE
  writing it into the real file.

- **Did NOT keep DeepSeek as primary**, even though it has no 8000 cap and
  therefore "solved" the truncation. Two runs showed it returning empty or
  short content intermittently on long prompts. A provider that is roomy but
  flaky is worse than one that is tight but predictable. Groq leads, DeepSeek
  catches. Made it one env var (`LLM_PROVIDER`) so the trade is reversible.

- **Did NOT hardcode the API key** the user pasted in chat. Put it in `.env`
  (confirmed gitignored first) and read it with `os.getenv`.

- **Did NOT trust my own grep.** `grep -c "PRIMARY"` reported "3 fallback
  triggers" that were really the words "PRIMARY ROOT CAUSE HYPOTHESIS" in the
  task description. Re-grepped for the actual log prefix `[llm] PRIMARY`: zero.
  Nearly reported a fabricated failure count.

## The reusable rules

> In a sequential multi-agent chain, the prompt grows at every stage, so budget
> output per agent in reverse order of position, and cap the upstream agents'
> verbosity too: their words are subtracted from the last agent's room.

> A fallback that only catches exceptions is half a fallback. An LLM's most
> common failure is a successful response with empty content.
