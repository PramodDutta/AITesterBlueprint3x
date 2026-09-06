"""Fixtures for the RAG suite (Subsystem B).

The chatbot suite scores one thing: the reply. A RAG suite scores two, the
retrieval and the answer, so every test here asks the pipeline once and reuses
that single response. Re-querying per metric would triple the token bill and
let the two halves disagree about what was retrieved.
"""
from __future__ import annotations

import functools

import pytest

from targers.rag import RagClient


@pytest.fixture(scope="session")
def rag() -> RagClient:
    return RagClient()


@pytest.fixture(scope="session")
def ask(rag):
    """Memoised query: one HTTP call per question for the whole session."""

    @functools.lru_cache(maxsize=256)
    def _ask(question: str, top_k: int = 4):
        return rag.ask(question, top_k=top_k)

    return _ask


@pytest.fixture(autouse=True)
def _skip_if_rag_down(request, rag):
    if "needs_rag" not in request.keywords:
        return
    if not _rag_up(rag):
        pytest.skip(
            "RAG Explorer is not reachable - start Subsystem B first: "
            "uvicorn app:app --port 8202 --env-file .env"
        )


@functools.lru_cache(maxsize=1)
def _rag_up(client: RagClient) -> bool:
    return client.is_up()
