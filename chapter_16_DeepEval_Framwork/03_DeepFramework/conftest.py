"""Shared fixtures for the DeepEval chatbot suite.

Two session fixtures carry the whole suite:
  chatbot - an HTTP client for Subsystem A, the app under test
  judge   - openai/gpt-oss-120b on Groq, the model that scores every metric

Both are session-scoped: building them per test would open a new client for
every parametrised case and burn rate limit for nothing.
"""
from __future__ import annotations

import functools

import pytest
from dotenv import load_dotenv

from llm_providers.judge import build_judge, judge_name
from targers.chatbot import ChatbotClient

load_dotenv()


def pytest_configure(config):
    for marker, help_text in [
        ("chatbot", "targets Subsystem A, the ShopSphere chatbot"),
        ("quality", "answer quality: relevancy, faithfulness, hallucination, correctness"),
        ("safety", "safety: bias, toxicity, PII leakage"),
        ("slow", "makes real LLM calls; costs tokens and time"),
        ("needs_chatbot", "skipped unless the chatbot is reachable"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {help_text}")


@pytest.fixture(scope="session")
def chatbot() -> ChatbotClient:
    return ChatbotClient()


@pytest.fixture(scope="session")
def judge():
    return build_judge()


@pytest.fixture(scope="session")
def judge_model_name() -> str:
    return judge_name()


@pytest.fixture(autouse=True)
def _skip_if_chatbot_down(request, chatbot):
    """Skip rather than fail when Subsystem A is not running.

    A red suite should mean "the bot behaved badly", never "I forgot to start
    the server". Cached so we probe /health once per session, not per test.
    """
    if "needs_chatbot" not in request.keywords:
        return
    if not _chatbot_up(chatbot):
        pytest.skip(
            "chatbot is not reachable at its base URL - start Subsystem A first: "
            "uvicorn app:app --app-dir backend --port 8201 --env-file .env"
        )


@functools.lru_cache(maxsize=1)
def _chatbot_up(client: ChatbotClient) -> bool:
    return client.is_up()
