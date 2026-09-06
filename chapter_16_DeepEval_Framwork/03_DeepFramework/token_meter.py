"""Counts tokens spent per metric run, split by who spent them.

Two different bills are hiding inside one dashboard card:
  target - tokens the app under test burned answering the question
  judge  - tokens the evaluator burned scoring that answer

They are usually not close. A judge that explains its reasoning can cost
several times what the answer itself cost, which is the number people are
surprised by when they first put an eval suite in CI.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Bucket:
    calls: int = 0
    prompt: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "prompt": self.prompt,
            "completion": self.completion,
            "total": self.total,
        }


class TokenMeter:
    """Process-wide counter with a resettable 'current run' window."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.run: dict[str, Bucket] = {"target": Bucket(), "judge": Bucket()}
        self.session: dict[str, Bucket] = {"target": Bucket(), "judge": Bucket()}

    def record(self, source: str, prompt: int, completion: int) -> None:
        if source not in ("target", "judge"):
            source = "judge"
        with self._lock:
            for scope in (self.run, self.session):
                b = scope[source]
                b.calls += 1
                b.prompt += prompt or 0
                b.completion += completion or 0

    def start_run(self) -> None:
        with self._lock:
            self.run = {"target": Bucket(), "judge": Bucket()}

    def _shape(self, scope: dict[str, Bucket]) -> dict:
        target, judge = scope["target"], scope["judge"]
        return {
            "target": target.as_dict(),
            "judge": judge.as_dict(),
            "total": target.total + judge.total,
            "calls": target.calls + judge.calls,
        }

    def run_snapshot(self) -> dict:
        with self._lock:
            return self._shape(self.run)

    def session_snapshot(self) -> dict:
        with self._lock:
            return self._shape(self.session)

    def reset_session(self) -> None:
        with self._lock:
            self.session = {"target": Bucket(), "judge": Bucket()}


METER = TokenMeter()


def record_usage(source: str, usage) -> None:
    """Record an OpenAI-shaped `usage` object, ignoring missing fields."""
    if usage is None:
        return
    METER.record(
        source,
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )
