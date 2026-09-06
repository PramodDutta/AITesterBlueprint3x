# DeepEval on Groq: three silent mis-wirings between subject model and judge model

**Date:** 2026-09-06
**Context:** chapter_15_DeepEval, completing `ask_groq()` in `test_02_Groq_LLama4_Vs_GROQ_Qwen.py`

## Problem (one line)

A DeepEval test that calls one Groq model and scores it with another failed three different
ways, and none of the three errors named the real cause.

## The approach

The task looked like "write four lines of OpenAI SDK code". It was, but the surrounding
config was wrong in ways only a live call would reveal. Steps that worked:

1. **Read the credential before writing against it.** `.env` had only `OPENAI_API_KEY`.
   Checking the first four characters showed `gsk_`, which is a Groq key, not an OpenAI one.
   It sits under that name because DeepEval's `set-local-model` path reads `OPENAI_API_KEY`
   when talking to any OpenAI-compatible endpoint. Never infer the provider from the var name.
2. **Check which SDK is actually installed.** `openai` 3.8.0 was present, `groq` was not.
   Groq speaks the OpenAI API, so the fix was `OpenAI(base_url="https://api.groq.com/openai/v1")`,
   with no new dependency.
3. **Run the call for real, and look at the value.** The function returned
   `'0.0003637653135228902'`. No exception, no warning. `meta-llama/llama-prompt-guard-2-86m`
   is an 86M prompt-injection *classifier*, not a chat model; it answers every prompt with a
   jailbreak probability. A model id that parses and returns 200 OK is not a model that answers.
4. **Ask the provider what exists, rather than trusting the file's comments.** `client.models.list()`
   showed no Llama 4 model on that key at all, only the two prompt-guard classifiers. The file's
   whole premise ("Llama4 vs Qwen") was unbuildable as written, which is a question for the
   author, not something to silently paper over.
5. **Separate the subject failure from the judge failure.** After the subject returned `'4'`,
   the test still failed with "Local API key is not configured". DeepEval reads the judge's key
   from `LOCAL_MODEL_API_KEY`, a *different* name from the one the subject uses, and
   `set-local-model --prompt-api-key` had never persisted it.

## Judgment calls

- **Did not change `GROQ_MODEL` unilaterally.** The user asked only to complete a function.
  Which model the lesson demonstrates changes what the chapter teaches, and the stated intent
  (Llama 4) was unavailable, so there was no safe default. Asked instead.
- **Picked a subject from a different family than the judge.** `qwen/qwen3.8-27b` under a
  `openai/gpt-oss-120b` judge. Judging a model with its own sibling inflates scores through
  self-preference bias, which quietly defeats the point of an eval chapter.
- **Did not tighten `HallucinationMetric(threshold=0.3)`.** DeepEval 4.x inverted the metric's
  direction, so 0.3 is now a weak floor rather than a 30% violation ceiling. Flagged it; changing
  a test's strictness is the author's call.
- **Deleted the `.env` backup immediately.** Root `.gitignore` lists `.env` exactly, which does
  not match `.env.bak.*`. A timestamped backup of a secrets file would have been committable.

## Reusable rule

**When wiring an LLM eval, prove the subject and the judge separately with a live call and read
the returned value, not just the status code.** A credential's variable name does not identify
its provider, and a model id that responds successfully is not necessarily a model that answers.
