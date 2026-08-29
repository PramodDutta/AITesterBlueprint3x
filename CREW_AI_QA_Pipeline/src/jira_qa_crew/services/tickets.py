"""Ticket input parsing, normalization, validation and deduplication.

Accepts commas, spaces, newlines and semicolons in any combination, which is
what people actually paste out of Jira.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..exceptions import TicketInputError

_SPLIT_RE = re.compile(r"[,\s;]+")


@dataclass
class ParsedTickets:
    """Result of parsing the ticket box. Nothing is silently discarded."""

    valid: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    dropped_over_limit: list[str] = field(default_factory=list)

    @property
    def has_valid(self) -> bool:
        return bool(self.valid)


def parse_ticket_input(
    raw: str,
    key_pattern: str = r"^[A-Z][A-Z0-9_]+-\d+$",
    max_tickets: int = 20,
    max_chars: int = 4000,
) -> ParsedTickets:
    """Turn free-form input into an ordered, unique list of Jira keys.

    Order is preserved (first occurrence wins) so results appear in the order
    the user typed them.
    """
    if raw is None:
        raise TicketInputError("No ticket input was provided")
    if len(raw) > max_chars:
        raise TicketInputError(
            f"Ticket input is too long ({len(raw)} characters, limit {max_chars})"
        )

    try:
        pattern = re.compile(key_pattern)
    except re.error as exc:
        raise TicketInputError(f"Invalid Jira key pattern: {exc}") from exc

    result = ParsedTickets()
    seen: set[str] = set()

    for token in _SPLIT_RE.split(raw.strip()):
        if not token:
            continue
        key = token.strip().upper()
        if not pattern.match(key):
            result.invalid.append(token.strip())
            continue
        if key in seen:
            result.duplicates.append(key)
            continue
        seen.add(key)
        if len(result.valid) >= max_tickets:
            result.dropped_over_limit.append(key)
            continue
        result.valid.append(key)

    return result


def safe_path_segment(value: str) -> str:
    """Make a filesystem-safe segment out of a ticket key.

    Ticket input must never be able to escape the run directory, so anything
    outside ``[A-Za-z0-9._-]`` is replaced and traversal is stripped.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", (value or "").strip())
    cleaned = cleaned.replace("..", "_").strip("._-")
    return cleaned or "unknown"
