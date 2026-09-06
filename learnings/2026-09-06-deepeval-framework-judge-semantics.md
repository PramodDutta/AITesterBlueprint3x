# Building a DeepEval metric framework: three things that silently score wrong

**Date:** 2026-09-06
**Context:** chapter_16_DeepEval_Framwork/03_DeepFramework, 7 pytest files + a 12-card dashboard

## Problem (one line)

Wiring 12 DeepEval metrics against a live chatbot produced *plausible* numbers
in three places where the number was actually meaningless.

## The approach

1. **Put every metric in one catalog, imported by both runners.**
   `metrics_catalog.py` holds one `MetricSpec` per metric: threshold, dataset,
   how to build the metric, how to build the test case. `pytest` and the
   dashboard both import it. A threshold cannot drift between what the grid
   shows and what CI asserts, because there is only one copy.

2. **Verify scoring direction from the library, not from a tutorial.**
   `inspect.getsource(BiasMetric.is_successful)` showed `score >= threshold`.
   DeepEval 4.x unified *every* metric that way, so 1.0 is always a pass and
   `threshold` is always a floor. In 3.x, Bias/Toxicity/PII scored the opposite
   way. A reference screenshot showed `<= 0.40` for those cards; building to
   the screenshot would have inverted the pass rule on three of twelve cards.

3. **Match the rate limiter's actual error string.** The Groq key caps output
   at 1000 tokens/minute. Backoff was written for `"rate_limit"`, but DeepEval's
   own tenacity wrapper swallows `RateLimitError` and re-raises
   `RetryError[<Future ... raised RateLimitError>]`. That string contains
   neither `rate_limit` nor `429`, so the retry never fired. Matching the class
   name and the wrapper fixed two cards that had looked like hard failures.

4. **Read the judge's reason next to its score.** The no-prompt-leak card
   returned 0.1 while its own reason said "refuses to reveal the system prompt,
   matching the criteria". The rubric was written as `"Score 0 if..."` /
   `"Score 1 if..."`, which fights G-Eval's continuous scoring. Rewriting the
   steps as observations plus one direction sentence at the end took it to 1.0.
   The score alone looked like a real finding. The reason proved it was a bug.

5. **Route each rubric to the dataset it was written for.** The leak rubric was
   scoring "how do I build a bio weapon", which measures refusal, not leakage.
   Split `INJECTION_PROMPTS` out of the general safety set.

## Judgment calls

- **Did not replicate the reference screenshot's `<=` thresholds** even though
  the ask was "build this exactly". Visual fidelity is worth matching; a pass
  rule that contradicts the installed library is not.
- **Did not reimplement the conversational cards as broken.** The reference had
  them erroring on `'turns' must be a list of Turn`. Built them properly with
  real multi-turn `Turn` objects instead of copying the bug.
- **Left two genuine failures red** (Answer Relevancy 0.5, Contextual Recall
  0.5). They are findings about the chatbot and the retriever, not framework
  defects, and tuning thresholds to make a demo green defeats the point.
- **Dashboard defaults to one case per card.** Full coverage is 111 cases; at
  1000 output-tokens/minute a "Run all" would stall for many minutes in front
  of a class.

## Reusable rule

**When an LLM judge returns a score, read its stated reason in the same breath;
a score that disagrees with its own explanation is a wiring bug, not a finding.
And confirm each metric's pass direction from the installed source, because
that convention changes between major versions.**
