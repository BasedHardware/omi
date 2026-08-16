"""Tests for strict exact conversation-reference parsing and hydrated date filtering."""

import os
from datetime import datetime, timezone

os.environ.setdefault("TYPESENSE_HOST", "localhost")
os.environ.setdefault("TYPESENSE_HOST_PORT", "8108")
os.environ.setdefault("TYPESENSE_PROTOCOL", "http")
os.environ.setdefault("TYPESENSE_API_KEY", "test-key")

import pytest

from utils.conversations.search import conversation_matches_date_range, parse_exact_conversation_reference

CONVERSATION_ID = "e8c05000-52f0-4a95-951c-ccd715523429"


@pytest.mark.parametrize(
    "reference",
    [
        CONVERSATION_ID,
        CONVERSATION_ID.upper(),
        f"https://h.omi.me/conversations/{CONVERSATION_ID}",
        f"https://H.OMI.ME/conversations/{CONVERSATION_ID.upper()}",
    ],
)
def test_parse_exact_conversation_reference_accepts_canonical_id_and_share_url(reference):
    assert parse_exact_conversation_reference(reference) == CONVERSATION_ID


@pytest.mark.parametrize(
    "reference",
    [
        CONVERSATION_ID[:-1],
        f"https://h.omi.me/conversations/{CONVERSATION_ID}/extra",
        f"https://h.omi.me/conversations/{CONVERSATION_ID}/",
        f"http://h.omi.me/conversations/{CONVERSATION_ID}",
        f"https://h.omi.me.evil.example/conversations/{CONVERSATION_ID}",
        f"https://user@h.omi.me/conversations/{CONVERSATION_ID}",
        f"https://h.omi.me:443/conversations/{CONVERSATION_ID}",
        f"https://h.omi.me/conversations/{CONVERSATION_ID}?source=chat",
        f"https://h.omi.me/conversations/{CONVERSATION_ID}#transcript",
        "find the conversation e8c05000",
    ],
)
def test_parse_exact_conversation_reference_rejects_ambiguous_references(reference):
    assert parse_exact_conversation_reference(reference) is None


@pytest.mark.parametrize(
    "created_at,expected",
    [
        (datetime(2026, 1, 15, tzinfo=timezone.utc), True),
        ("2026-01-15T00:00:00+00:00", True),
        (datetime(2025, 12, 31, tzinfo=timezone.utc), False),
        (None, False),
    ],
)
def test_conversation_matches_date_range_uses_created_at(created_at, expected):
    assert (
        conversation_matches_date_range(
            {"created_at": created_at},
            start_date=int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()),
            end_date=int(datetime(2026, 1, 31, tzinfo=timezone.utc).timestamp()),
        )
        is expected
    )
