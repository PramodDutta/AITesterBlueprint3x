"""Structured output that survives providers without JSON-schema support.

CrewAI's ``output_pydantic`` asks the provider to enforce a JSON schema. Not
every provider can: DeepSeek, for example, accepts ``response_format:
json_object`` but rejects ``json_schema`` outright with HTTP 400 "This
response_format type is unavailable now".

So we run in one of two modes:

``schema``  - let the provider enforce the schema (best, when supported)
``prompt``  - clear ``output_pydantic``, put the schema in the prompt, and
              validate the returned JSON here in Python

The mode is detected at runtime from the provider's own error, then remembered
for the rest of the run so no call is wasted twice.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

#: Substrings that identify "this provider cannot enforce a JSON schema".
SCHEMA_REJECTION_MARKERS = (
    "response_format",
    "json_schema",
    "unsupported_value",
    "structured output",
)

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)

#: Schema keys that help a human but only cost tokens in a prompt.
_NOISE_KEYS = frozenset({"description", "title", "default", "examples"})

#: Markers for "the provider returned a successful but empty completion".
#: This is DeepSeek's characteristic failure on long generations: not an API
#: error, just no content, which CrewAI surfaces a few frames later.
EMPTY_RESPONSE_MARKERS = (
    "none or empty",
    "invalid response from llm call",
    "empty response",
)

JSON_MODE_INSTRUCTION = """

### OUTPUT FORMAT (mandatory)
Reply with a single JSON object and nothing else. No prose before it, no prose
after it, no markdown fence. It must validate against this JSON schema:

{schema}

Use only the field names in the schema. Omit a field rather than inventing a
value for it.
"""


def schema_rejected(exc: BaseException) -> bool:
    """True when the provider refused the request because of the schema.

    Deliberately narrow: a rate limit or an auth failure must NOT be mistaken
    for a schema problem, or we would silently downgrade enforcement.
    """
    text = str(exc).lower()
    if "400" not in text and "invalid_request" not in text and "unsupported" not in text:
        return False
    return any(marker in text for marker in SCHEMA_REJECTION_MARKERS)


def is_empty_response(exc: BaseException) -> bool:
    """True when the provider answered successfully but with no content.

    Worth retrying: it is transient, unlike a schema rejection or a bad key.
    """
    text = str(exc).lower()
    return any(marker in text for marker in EMPTY_RESPONSE_MARKERS)


def compact_schema(schema: object, _keys_are_names: bool = False) -> object:
    """Strip prompt-only noise from a JSON schema.

    Descriptions and titles are useful in documentation and useless in a
    prompt that already explains the task. Removing them cuts these schemas
    by roughly two thirds, which matters when the provider is also being
    asked to generate a long object.

    The subtlety: inside ``properties`` and ``$defs`` the dictionary keys are
    FIELD NAMES, not schema keywords. A naive filter deletes a real field
    called ``title`` or ``description`` and silently corrupts the contract,
    so those mappings are recursed into without filtering their keys.
    """
    if isinstance(schema, dict):
        if _keys_are_names:
            return {key: compact_schema(value) for key, value in schema.items()}
        return {
            key: compact_schema(
                value,
                _keys_are_names=key in {"properties", "$defs", "definitions", "patternProperties"},
            )
            for key, value in schema.items()
            if key not in _NOISE_KEYS
        }
    if isinstance(schema, list):
        return [compact_schema(item) for item in schema]
    return schema


def json_mode_instruction(model: type[BaseModel]) -> str:
    """The prompt suffix that replaces provider-side schema enforcement."""
    schema = compact_schema(model.model_json_schema())
    return JSON_MODE_INSTRUCTION.format(schema=json.dumps(schema, separators=(",", ":")))


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model response.

    Handles a bare object, a ```json fenced block, and an object with prose
    wrapped around it. Returns ``None`` when there is nothing parseable.
    """
    if not text or not text.strip():
        return None

    candidates: list[str] = []
    stripped = text.strip()
    candidates.append(stripped)
    candidates.extend(match.strip() for match in _FENCE_RE.findall(text))

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
    return None


def looks_truncated(text: str) -> bool:
    """True when the response starts as JSON but never finishes.

    A cut-off completion is a different problem from a model that answered in
    prose, and it needs a different instruction on the retry, so it is worth
    telling apart. Counts brackets outside of string literals.
    """
    stripped = (text or "").strip()
    if not stripped.startswith(("{", "[")):
        return False

    depth = 0
    in_string = False
    escaped = False
    for char in stripped:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
    return in_string or depth > 0


def parse_model(text: str, model: type[TModel]) -> TModel | None:
    """Validate a model response into ``model``, or return ``None``.

    Logs *why* it failed. Without this, a parse failure is indistinguishable
    from a provider outage in the logs, which makes the pipeline very hard to
    debug against a new model.
    """
    payload = extract_json(text)
    if payload is None:
        if looks_truncated(text):
            logger.warning(
                "the %s response was cut off mid-JSON (%s chars); ends with: %r",
                model.__name__,
                len(text or ""),
                (text or "")[-160:],
            )
        else:
            logger.warning(
                "no JSON object found in the %s response (%s chars); starts with: %r",
                model.__name__,
                len(text or ""),
                (text or "")[:200],
            )
        return None
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "response did not validate against %s: %s | keys: %s",
            model.__name__,
            "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]
            ),
            sorted(payload)[:15],
        )
        return None
