"""Ticket parsing, normalization, validation, deduplication and path safety."""

from __future__ import annotations

import pytest

from jira_qa_crew.exceptions import TicketInputError
from jira_qa_crew.services.tickets import parse_ticket_input, safe_path_segment


@pytest.mark.parametrize(
    "raw",
    [
        "VWO-48,VWO-49",
        "VWO-48 VWO-49",
        "VWO-48\nVWO-49",
        "VWO-48; VWO-49",
        "  vwo-48 ,\n vwo-49  ",
        "VWO-48,\n\tVWO-49;",
    ],
)
def test_accepts_every_separator_and_upper_cases(raw):
    assert parse_ticket_input(raw).valid == ["VWO-48", "VWO-49"]


def test_removes_duplicates_and_keeps_first_order():
    parsed = parse_ticket_input("VWO-50, VWO-48, vwo-50, VWO-48")
    assert parsed.valid == ["VWO-50", "VWO-48"]
    assert parsed.duplicates == ["VWO-50", "VWO-48"]


def test_separates_invalid_tokens_instead_of_guessing():
    parsed = parse_ticket_input("VWO-48, not-a-key, 12345, ABC-")
    assert parsed.valid == ["VWO-48"]
    assert parsed.invalid == ["not-a-key", "12345", "ABC-"]


def test_respects_the_ticket_limit_and_reports_what_it_dropped():
    parsed = parse_ticket_input("AB-1 AB-2 AB-3 AB-4", max_tickets=2)
    assert parsed.valid == ["AB-1", "AB-2"]
    assert parsed.dropped_over_limit == ["AB-3", "AB-4"]


def test_single_letter_project_keys_are_rejected_like_jira_does():
    # Jira project keys are at least two characters, so "A-1" is not a key.
    assert parse_ticket_input("A-1").invalid == ["A-1"]


def test_rejects_oversized_input():
    with pytest.raises(TicketInputError):
        parse_ticket_input("VWO-1 " * 5000, max_chars=100)


def test_custom_key_pattern_is_honoured():
    parsed = parse_ticket_input("PROJ-1, X-2", key_pattern=r"^PROJ-\d+$")
    assert parsed.valid == ["PROJ-1"]
    assert parsed.invalid == ["X-2"]


def test_empty_input_yields_nothing_valid():
    parsed = parse_ticket_input("   ")
    assert not parsed.has_valid


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VWO-48", "VWO-48"),
        ("../../etc/passwd", "etc_passwd"),
        ("..", "unknown"),
        ("a/b", "a_b"),
        ("", "unknown"),
        ("VWO 48!", "VWO_48"),
    ],
)
def test_path_segments_cannot_traverse(raw, expected):
    assert safe_path_segment(raw) == expected
