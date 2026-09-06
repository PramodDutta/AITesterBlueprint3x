"""ChromaDB persistent vector store."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import chromadb
from chromadb.config import Settings

from .ingest import Chunk

DB_DIR = os.getenv("CHROMA_DIR", str(Path(__file__).resolve().parent.parent / "chroma_db"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "ecommerce_kb")


@dataclass
class Hit:
    id: str
    source: str
    text: str
    score: float
    metadata: dict


class VectorStore:
    def __init__(self, path: str = DB_DIR, collection: str = COLLECTION_NAME):
        Path(path).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.collection.name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> int:
        if not chunks:
            return 0
        self.collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=[list(e) for e in embeddings],
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "source": c.source,
                    "index": c.index,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                }
                for c in chunks
            ],
        )
        return len(chunks)

    def search(self, query_embedding: Sequence[float], top_k: int = 4) -> list[Hit]:
        result = self.collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[Hit] = []
        if not result["ids"] or not result["ids"][0]:
            return hits
        for hit_id, doc, meta, dist in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            hits.append(
                Hit(
                    id=hit_id,
                    source=meta.get("source", "?"),
                    text=doc,
                    score=1.0 - float(dist),
                    metadata=meta,
                )
            )
        return hits

    def stats(self) -> dict[str, Any]:
        count = self.collection.count()
        sources: dict[str, int] = {}
        if count > 0:
            sample = self.collection.get(limit=count, include=["metadatas"])
            for m in sample.get("metadatas") or []:
                src = m.get("source", "?")
                sources[src] = sources.get(src, 0) + 1
        return {"chunks": count, "sources": sources, "collection": self.collection.name}

    def list_chunks(self, source: str | None = None, limit: int = 200) -> list[dict]:
        result = self.collection.get(
            limit=limit,
            include=["documents", "metadatas"],
            where={"source": source} if source else None,
        )
        items: list[dict] = []
        for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"]):
            items.append({
                "id": cid,
                "source": meta.get("source", "?"),
                "index": meta.get("index", 0),
                "text": doc,
                "metadata": meta,
            })
        items.sort(key=lambda x: (x["source"], x["index"]))
        return items
