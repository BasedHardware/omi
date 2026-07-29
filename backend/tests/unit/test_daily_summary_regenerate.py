"""
Unit tests for the daily-summary regenerate path.

Focuses on the behavior that's easiest to regress: update_daily_summary
must force the stored payload's id back to the existing doc id, even if
the freshly-generated summary carries a different (newly-allocated) UUID.
"""

import os
import sys
import types
from unittest.mock import MagicMock

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        partial = ".".join(parts[:i])
        if partial not in sys.modules:
            mod = types.ModuleType(partial)
            mod.__path__ = []  # mark as package so subimports resolve
            sys.modules[partial] = mod
    return sys.modules[name]


# redis_db is imported by database.daily_summaries; stub the redis driver so the
# import doesn't try to open a real connection.
redis_stub = _stub_module("redis")
redis_stub.Redis = MagicMock(return_value=MagicMock())

import database.daily_summaries as daily_summaries  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


def _summary_path(uid: str, summary_id: str) -> str:
    return f"users/{uid}/{daily_summaries.DAILY_SUMMARIES_COLLECTION}/{summary_id}"


def test_update_daily_summary_forces_id_to_existing_doc_id(monkeypatch):
    """
    Regression: generator always allocates a fresh UUID. update_daily_summary
    must pin the stored payload's id back to the existing summary_id so
    readers that key off summary['id'] keep finding the same row.
    """
    store = FakeDocumentStore()
    monkeypatch.setattr(daily_summaries, "_store", lambda: store)

    daily_summaries.update_daily_summary(
        "uid-abc",
        "existing-summary-id",
        {
            "id": "freshly-generated-uuid-from-llm",
            "date": "2026-06-02",
            "headline": "Updated",
        },
    )

    payload = store.get(_summary_path("uid-abc", "existing-summary-id")).to_dict()
    assert payload["id"] == "existing-summary-id", (
        "update_daily_summary must overwrite the generator's UUID with the "
        "existing doc id so regenerate replaces in place"
    )
    assert payload["date"] == "2026-06-02"
    assert payload["headline"] == "Updated"


def test_update_daily_summary_preserves_other_fields(monkeypatch):
    """All non-id fields pass through unchanged."""
    store = FakeDocumentStore()
    monkeypatch.setattr(daily_summaries, "_store", lambda: store)

    daily_summaries.update_daily_summary(
        "uid-abc",
        "existing-summary-id",
        {
            "id": "x",
            "date": "2026-06-02",
            "headline": "H",
            "overview": "O",
            "day_emoji": "🎉",
            "stats": {"total_conversations": 7},
            "regenerated_at": "2026-06-02T12:00:00",
            "visibility": "shared",
        },
    )

    payload = store.get(_summary_path("uid-abc", "existing-summary-id")).to_dict()
    assert payload["stats"] == {"total_conversations": 7}
    assert payload["regenerated_at"] == "2026-06-02T12:00:00"
    assert payload["visibility"] == "shared"
    assert payload["day_emoji"] == "🎉"
