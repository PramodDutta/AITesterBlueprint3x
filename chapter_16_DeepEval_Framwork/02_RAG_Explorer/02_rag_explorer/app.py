"""RAG Explorer — FastAPI app showcasing the full RAG pipeline."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from rag.chat import answer_with_rag
from rag.embed import embed_query, embed_texts, model_info
from rag.ingest import chunk_document, load_any, load_directory, chunk_documents
from rag.store import VectorStore

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "ecommerce"
UPLOAD_DIR = ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="ShopSphere RAG Explorer", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

store = VectorStore()


# -------------------- API models --------------------

class IngestPathRequest(BaseModel):
    path: str | None = None
    reset: bool = False


class SearchRequest(BaseModel):
    query: str
    top_k: int = 4


class ChatRequest(BaseModel):
    message: str
    top_k: int = 4
    history: list[dict] | None = None


# -------------------- Pages --------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": store.stats(),
            "embed": model_info(),
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        },
    )


@app.get("/ingest", response_class=HTMLResponse)
def ingest_page(request: Request):
    return templates.TemplateResponse(
        "ingest.html",
        {
            "request": request,
            "stats": store.stats(),
            "data_dir": str(DATA_DIR),
            "available_files": [p.name for p in sorted(DATA_DIR.iterdir())] if DATA_DIR.exists() else [],
            "uploads": [p.name for p in sorted(UPLOAD_DIR.iterdir())],
            "chunks": store.list_chunks(),
        },
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", k: int = 4):
    hits = []
    if q:
        emb = embed_query(q)
        hits = store.search(emb, top_k=k)
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "q": q, "k": k, "hits": hits, "stats": store.stats()},
    )


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "stats": store.stats(),
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        },
    )


# -------------------- API endpoints --------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "stats": store.stats(),
        "embed": model_info(),
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
    }


@app.post("/api/ingest/seed")
def ingest_seed(reset: bool = False):
    """Ingest all docs in data/ecommerce."""
    if reset:
        store.reset()
    if not DATA_DIR.exists():
        raise HTTPException(404, f"data dir not found: {DATA_DIR}")
    docs = load_directory(DATA_DIR)
    chunks = chunk_documents(docs)
    embeddings = embed_texts([c.text for c in chunks])
    added = store.add_chunks(chunks, embeddings)
    return {"added": added, "documents": len(docs), "stats": store.stats()}


@app.post("/api/ingest/upload")
async def ingest_upload(file: UploadFile = File(...), reset: bool = Form(False)):
    if reset:
        store.reset()
    target = UPLOAD_DIR / file.filename
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    doc = load_any(target)
    chunks = chunk_document(doc)
    embeddings = embed_texts([c.text for c in chunks])
    added = store.add_chunks(chunks, embeddings)
    return {
        "added": added,
        "source": doc.source,
        "chunk_count": len(chunks),
        "preview": [c.text[:160] for c in chunks[:3]],
        "stats": store.stats(),
    }


@app.post("/api/ingest/reset")
def ingest_reset():
    store.reset()
    return {"status": "reset", "stats": store.stats()}


@app.post("/api/search")
def api_search(req: SearchRequest):
    emb = embed_query(req.query)
    hits = store.search(emb, top_k=req.top_k)
    return {
        "query": req.query,
        "hits": [
            {
                "id": h.id,
                "source": h.source,
                "score": round(h.score, 4),
                "text": h.text,
                "metadata": h.metadata,
            }
            for h in hits
        ],
    }


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    result = answer_with_rag(req.message, store, top_k=req.top_k, history=req.history)
    return {
        "answer": result.answer,
        "sources": result.sources,
        "retrieval_context": result.retrieval_context,
        "hits": [
            {"id": h.id, "source": h.source, "score": round(h.score, 4), "text": h.text}
            for h in result.hits
        ],
        "mode": result.mode,
        "model": result.model,
        # Echoed so an evaluation harness can bill generation separately
        # from the tokens its judge spends scoring the answer.
        "usage": result.usage,
    }


@app.get("/api/chunks")
def api_chunks(source: str | None = None):
    return {"chunks": store.list_chunks(source=source)}


@app.get("/api/stats")
def api_stats():
    return store.stats()
