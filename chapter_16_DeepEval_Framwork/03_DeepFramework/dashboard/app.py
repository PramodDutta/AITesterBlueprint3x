"""DeepEval Dashboard - Subsystem C's control panel.

Runs the same metrics the pytest suite asserts, one card at a time, and shows
the score, the judge's reason and the latency for each.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from fastapi import Request  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from dashboard.runner import RAG_URL, run_spec  # noqa: E402
from llm_providers.judge import build_judge, judge_name  # noqa: E402
from metrics_catalog import ALL_SPECS, CATEGORIES, SPECS_BY_KEY  # noqa: E402
from targers.chatbot import CHATBOT_URL, ChatbotClient  # noqa: E402
from token_meter import METER  # noqa: E402

load_dotenv(ROOT / ".env")

HERE = Path(__file__).resolve().parent
app = FastAPI(title="DeepEval Dashboard", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
templates = Jinja2Templates(directory=str(HERE / "templates"))

chatbot = ChatbotClient()
_judge = None


def get_judge():
    global _judge
    if _judge is None:
        _judge = build_judge()
    return _judge


class RunRequest(BaseModel):
    key: str
    sample: int = 1
    offset: int = 0


def _card(spec) -> dict:
    return {
        "key": spec.key,
        "number": spec.number,
        "title": spec.title,
        "blurb": spec.blurb,
        "question": spec.question,
        "threshold": spec.threshold,
        "scale_hint": spec.scale_hint,
        "category": spec.category,
        "target": spec.target,
        "kind": spec.kind,
        "test_file": spec.test_file,
        "cases_total": len(spec.cases()),
        "needs": spec.needs,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cards": [_card(s) for s in ALL_SPECS],
            "categories": CATEGORIES,
            "chatbot_url": CHATBOT_URL,
            "rag_url": RAG_URL,
            "judge_model": judge_name(),
        },
    )


@app.get("/api/catalog")
def api_catalog():
    return {"cards": [_card(s) for s in ALL_SPECS], "categories": CATEGORIES}


@app.get("/api/status")
def api_status():
    def probe(url: str, path: str) -> bool:
        try:
            return requests.get(f"{url}{path}", timeout=4).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    return {
        "chatbot": {"url": CHATBOT_URL, "up": probe(CHATBOT_URL, "/health")},
        "rag": {"url": RAG_URL, "up": probe(RAG_URL, "/api/health")},
        "judge": {"model": judge_name(), "up": bool(os.getenv("GROQ_API_KEY"))},
    }


@app.get("/api/tokens")
def api_tokens():
    """Cumulative token spend for this dashboard process."""
    return METER.session_snapshot()


@app.post("/api/tokens/reset")
def api_tokens_reset():
    METER.reset_session()
    return METER.session_snapshot()


@app.post("/api/run")
def api_run(req: RunRequest):
    spec = SPECS_BY_KEY.get(req.key)
    if spec is None:
        return {"error": f"unknown metric '{req.key}'"}
    return run_spec(spec, get_judge(), chatbot, sample=req.sample, offset=req.offset)
