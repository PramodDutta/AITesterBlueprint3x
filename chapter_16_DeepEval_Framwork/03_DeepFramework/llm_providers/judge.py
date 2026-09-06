"""The judge LLM: openai/gpt-oss-120b served by Groq.

Every metric in this framework is scored by a *second* model, never by the
model under test. Groq speaks the OpenAI API, so DeepEval's LocalModel wraps
it directly and handles the JSON-schema parsing each metric needs.
"""
from __future__ import annotations

import os
import random
import threading
import time

from deepeval.models import LocalModel

from token_meter import record_usage
from dotenv import load_dotenv

load_dotenv()

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-oss-120b")
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "https://api.groq.com/openai/v1")

# Free-tier Groq accounts cap output tokens per minute (OTPM 1000 on this key).
# A metric suite fires judge calls back to back, so a burst will 429. One
# process-wide lock plus backoff turns a hard failure into a slow pass.
_LOCK = threading.Lock()
_MAX_RETRIES = 5


def _is_rate_limit(err: Exception) -> bool:
    """Detect a rate limit through whatever wrapper it arrives in.

    Groq raises RateLimitError, but DeepEval's own tenacity retry swallows it
    and re-raises `RetryError[<Future ... raised RateLimitError>]`. Matching
    only "rate_limit" misses that spelling entirely, so match the class name
    and the wrapper too.
    """
    text = str(err).lower()
    needles = ("rate_limit", "ratelimit", "429", "too many requests",
               "retryerror", "tokens per minute", "otpm")
    return any(n in text for n in needles)


class GroqJudge(LocalModel):
    """LocalModel plus serialisation and backoff for free-tier rate limits."""

    def _call(self, fn, *args, **kwargs):
        for attempt in range(_MAX_RETRIES):
            try:
                with _LOCK:
                    return fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 - provider raises many types
                if not _is_rate_limit(e) or attempt == _MAX_RETRIES - 1:
                    raise
                # Groq resets the per-minute window, so wait out the window
                # rather than hammering it. Jitter avoids lockstep retries.
                # Groq resets on a 60s window; short retries just burn attempts.
                delay = min(70, 25 * (attempt + 1)) + random.uniform(0, 5)
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def load_model(self, *args, **kwargs):
        """Wrap the OpenAI client once so every judge call reports its usage.

        LocalModel.generate throws the usage object away - it only returns
        (content, cost). Hooking the client is the one place the token counts
        are still reachable.
        """
        client = super().load_model(*args, **kwargs)
        if not getattr(client, "_meter_hooked", False):
            original = client.chat.completions.create

            def create(*a, **k):
                response = original(*a, **k)
                record_usage("judge", getattr(response, "usage", None))
                return response

            client.chat.completions.create = create
            client._meter_hooked = True
        return client

    def generate(self, *args, **kwargs):
        return self._call(super().generate, *args, **kwargs)

    async def a_generate(self, *args, **kwargs):
        # Metrics run with async_mode=False in this framework, so the sync
        # path above is the one that carries load. This keeps parity if a
        # caller flips async_mode back on.
        return await super().a_generate(*args, **kwargs)


def build_judge() -> GroqJudge:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to 03_DeepFramework/.env"
        )
    return GroqJudge(
        model=JUDGE_MODEL,
        api_key=api_key,
        base_url=JUDGE_BASE_URL,
        temperature=0.0,   # a judge must be as reproducible as possible
        format="json",     # every metric parses the reply as JSON
    )


def judge_name() -> str:
    return JUDGE_MODEL
