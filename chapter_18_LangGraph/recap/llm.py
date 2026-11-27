"""Shared LLM factory for scripts 008-010. Reads chapter_18_LangGraph/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

CHAPTER_ROOT = Path(__file__).resolve().parents[1]   # recap/ -> chapter_18_LangGraph/
load_dotenv(CHAPTER_ROOT / ".env")
load_dotenv()


def has_llm() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def get_llm(**settings):
    if not has_llm():
        raise SystemExit(
            "GROQ_API_KEY is not set. Copy chapter_18_LangGraph/.env.sample to .env "
            "and add a free key from https://console.groq.com/keys"
        )
    from langchain_groq import ChatGroq
    return ChatGroq(model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"), temperature=0, **settings)