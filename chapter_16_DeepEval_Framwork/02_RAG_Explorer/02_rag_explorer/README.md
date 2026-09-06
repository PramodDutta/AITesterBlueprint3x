# Subsystem B — RAG Explorer

A complete, locally-runnable RAG pipeline showcasing every stage:

```
ingest → chunk → embed (Nomic via Ollama) → store (ChromaDB) → retrieve → answer (Groq)
```

## Why "Explorer"

Most RAG demos hide retrieval behind the chat reply. This one **exposes every stage**: you see the raw chunks, the embeddings model, the retrieved hits with scores, and the grounded answer. That makes it auditable — exactly what DeepEval needs to evaluate retrieval, faithfulness, and grounding metrics.

## Port

`8202`

## Prerequisites

- **Ollama** with `nomic-embed-text` pulled:
  ```bash
  ollama pull nomic-embed-text
  ```
- `GROQ_API_KEY` for live answers (mock mode works without it).

## Run

```bash
cd 02_rag_explorer
pip install -r requirements.txt
export GROQ_API_KEY=gsk_...
uvicorn app:app --reload --port 8202
```

Open <http://localhost:8202>.

## Pages

| Path | What |
|------|------|
| `/` | Pipeline dashboard (stage diagram, store stats) |
| `/ingest` | Seed bundled corpus, upload PDF/MD/TXT, view all chunks |
| `/search` | Pure retrieval — query goes through embeddings only, view ranked hits |
| `/chat` | Full RAG chat with the retrieval panel exposed below the reply |

## API

| Verb | Path | Body |
|------|------|------|
| GET | `/api/health` | — |
| POST | `/api/ingest/seed?reset=true|false` | — |
| POST | `/api/ingest/upload` | multipart `file` |
| POST | `/api/ingest/reset` | — |
| POST | `/api/search` | `{query, top_k}` |
| POST | `/api/chat` | `{message, top_k, history?}` |
| GET | `/api/chunks?source=…` | — |
| GET | `/api/stats` | — |

## What is in the bundled corpus

5 e-commerce knowledge files in `data/ecommerce/`:

- `refund_policy.md`
- `shipping_policy.md`
- `return_policy.md`
- `product_catalog.md`
- `faq.md`

These are intentionally rich enough to stress-test retrieval, faithfulness, and hallucination metrics from Subsystem C.
