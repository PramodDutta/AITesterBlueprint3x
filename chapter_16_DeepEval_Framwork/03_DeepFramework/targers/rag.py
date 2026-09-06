"""Client for Subsystem B - the RAG Explorer (the second app under test).

Unlike the chatbot, this target exposes its retrieval. That extra visibility
is what makes contextual precision, recall and relevancy measurable at all:
without the chunks, you can only score the final answer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

from token_meter import METER

load_dotenv()

RAG_URL = os.getenv("RAG_URL", "http://localhost:8202").rstrip("/")
TIMEOUT = float(os.getenv("RAG_TIMEOUT", "90"))


@dataclass
class RagReply:
    answer: str
    retrieval_context: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    hits: list[dict] = field(default_factory=list)
    mode: str = "unknown"
    model: str = "unknown"


class RagClient:
    def __init__(self, base_url: str = RAG_URL):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        r = requests.get(f"{self.base_url}/api/health", timeout=10)
        r.raise_for_status()
        return r.json()

    def is_up(self) -> bool:
        try:
            return self.health().get("status") == "ok"
        except Exception:  # noqa: BLE001
            return False

    def stats(self) -> dict:
        r = requests.get(f"{self.base_url}/api/stats", timeout=10)
        r.raise_for_status()
        return r.json()

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        r = requests.post(
            f"{self.base_url}/api/search",
            json={"query": query, "top_k": top_k},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("hits", [])

    def ask(self, question: str, top_k: int = 4, history: list[dict] | None = None) -> RagReply:
        payload: dict = {"message": question, "top_k": top_k}
        if history:
            payload["history"] = history
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()

        usage = d.get("usage")
        if usage:
            METER.record(
                "target",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

        return RagReply(
            answer=d.get("answer") or "",
            retrieval_context=d.get("retrieval_context") or [],
            sources=d.get("sources") or [],
            hits=d.get("hits") or [],
            mode=d.get("mode", "unknown"),
            model=d.get("model", "unknown"),
        )
