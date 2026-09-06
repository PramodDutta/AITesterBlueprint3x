"""Executes one catalog metric and returns a JSON-serialisable result.

The dashboard and pytest share metrics_catalog, so a card here uses the same
metric object and the same threshold as the corresponding test file. What you
see on the grid is what `pytest` asserts.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests
from deepeval.test_case import Turn

from metrics_catalog import MetricSpec
from targers.chatbot import ChatbotClient
from targers.rag import RagClient
from token_meter import METER

RAG_URL = os.getenv("RAG_URL", "http://localhost:8202").rstrip("/")


_RAG = RagClient()


def prompt_of(item) -> str:
    """Datasets carry their prompt under three different attribute names."""
    if isinstance(item, str):
        return item
    for attr in ("input", "prompt"):
        if hasattr(item, attr):
            return getattr(item, attr)
    return str(item)


def _ask_target(spec, chatbot: ChatbotClient, text: str) -> str:
    """Route the question to whichever app this metric is pointed at."""
    if spec.target == "rag":
        return _RAG.ask(text).answer
    return chatbot.chat(text).reply


def _rag_query(question: str, top_k: int = 3) -> dict:
    r = requests.post(
        f"{RAG_URL}/api/chat", json={"message": question, "top_k": top_k}, timeout=90
    )
    r.raise_for_status()
    d = r.json()
    return {
        "answer": d.get("answer") or "",
        "retrieval_context": d.get("retrieval_context") or [],
    }


def _build_conversation(chatbot: ChatbotClient, golden) -> list[Turn]:
    """Drive a real multi-turn chat and capture it as DeepEval Turns."""
    turns: list[Turn] = []
    history: list[dict] = []
    for user_msg in golden.user_turns:
        reply = chatbot.chat(user_msg, history=history).reply
        turns.append(Turn(role="user", content=user_msg))
        turns.append(Turn(role="assistant", content=reply))
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": reply})
    return turns


def _one_case(spec: MetricSpec, metric, chatbot: ChatbotClient, item) -> dict:
    """Score a single dataset item. Returns a per-case row."""
    if spec.kind == "conversational":
        turns = _build_conversation(chatbot, item)
        tc = spec.build_case(turns)
        label = item.name
        actual = turns[-1].content if turns else ""
    elif spec.kind == "retrieval":
        payload = _rag_query(item.input)
        tc = spec.build_case(item, payload)
        label = item.input
        actual = payload["answer"]
    else:
        label = prompt_of(item)
        actual = _ask_target(spec, chatbot, label)
        tc = spec.build_case(item, actual)

    metric.measure(tc)
    score = metric.score
    return {
        "label": label,
        "actual_output": actual,
        "score": score,
        "passed": bool(metric.is_successful()),
        "reason": metric.reason or "",
    }


def run_spec(
    spec: MetricSpec,
    judge,
    chatbot: ChatbotClient,
    sample: int = 1,
    offset: int = 0,
) -> dict:
    """Run `sample` cases through one metric and aggregate."""
    started = time.perf_counter()
    METER.start_run()
    items = spec.cases()
    if not items:
        return _error(spec, "dataset for this metric is empty", started)

    window = items[offset : offset + max(1, sample)] or items[:1]
    rows: list[dict] = []
    try:
        metric = spec.build_metric(judge)
        for item in window:
            rows.append(_one_case(spec, metric, chatbot, item))
    except Exception as e:  # noqa: BLE001 - surface provider errors on the card
        return _error(spec, f"{type(e).__name__}: {e}", started, rows)

    scores = [r["score"] for r in rows if r["score"] is not None]
    avg = sum(scores) / len(scores) if scores else None
    return {
        "key": spec.key,
        "scale_hint": spec.scale_hint,
        "status": "pass" if all(r["passed"] for r in rows) else "fail",
        "score": avg,
        "threshold": spec.threshold,
        "reason": rows[0]["reason"] if rows else "",
        "rows": rows,
        "cases_run": len(rows),
        "cases_total": len(items),
        "tokens": METER.run_snapshot(),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "judge": getattr(judge, "name", "judge"),
        "error": None,
    }


def _error(spec: MetricSpec, message: str, started: float, rows: list | None = None) -> dict:
    return {
        "key": spec.key,
        "scale_hint": spec.scale_hint,
        "status": "error",
        "score": None,
        "threshold": spec.threshold,
        "reason": message,
        "rows": rows or [],
        "cases_run": len(rows or []),
        "cases_total": len(spec.cases()),
        "tokens": METER.run_snapshot(),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "judge": "",
        "error": message,
    }
