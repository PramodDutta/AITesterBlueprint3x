"""RAG chat: retrieve → format → Groq."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

from groq import Groq

from .embed import embed_query
from .store import Hit, VectorStore

GROQ_MODEL = os.getenv("RAG_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

SYSTEM_PROMPT = """You are ShopBot for ShopSphere, an e-commerce store. Answer ONLY using the retrieved context below. If the answer is not in the context, say "I don't have that information in my knowledge base — please contact support@shopsphere.com."

- Be concise (under 150 words).
- Quote exact figures from the context — do not invent numbers, SKUs, or timeframes.
- Cite sources inline like [refund_policy.md].
"""


@dataclass
class RagAnswer:
    answer: str
    sources: list[str]
    retrieval_context: list[str]
    hits: list[Hit]
    mode: str
    model: str
    usage: dict | None = None


def answer_with_rag(
    question: str,
    store: VectorStore,
    top_k: int = 4,
    history: Sequence[dict] | None = None,
) -> RagAnswer:
    q_emb = embed_query(question)
    hits = store.search(q_emb, top_k=top_k)
    retrieval_context = [h.text for h in hits]
    sources = sorted({h.source for h in hits})

    context_block = "\n\n".join(
        f"[{h.source} #{h.metadata.get('index')}]\n{h.text}" for h in hits
    ) or "(no documents retrieved)"

    if not GROQ_API_KEY:
        mock = (
            "[mock mode — set GROQ_API_KEY] Top retrieved chunks: "
            + "; ".join(f"{h.source}#{h.metadata.get('index')}" for h in hits)
        )
        return RagAnswer(
            answer=mock,
            sources=sources,
            retrieval_context=retrieval_context,
            hits=hits,
            mode="mock",
            model="mock",
        )

    client = Groq(api_key=GROQ_API_KEY)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history or []:
        messages.append(h)
    messages.append({
        "role": "user",
        "content": f"Question: {question}\n\nRetrieved context:\n{context_block}",
    })
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=500,
    )
    _u = completion.usage
    return RagAnswer(
        answer=completion.choices[0].message.content,
        usage={
            "prompt_tokens": getattr(_u, "prompt_tokens", 0),
            "completion_tokens": getattr(_u, "completion_tokens", 0),
        } if _u else None,
        sources=sources,
        retrieval_context=retrieval_context,
        hits=hits,
        mode="live",
        model=GROQ_MODEL,
    )
