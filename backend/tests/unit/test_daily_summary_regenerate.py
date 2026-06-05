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


# Stub google.cloud.firestore so importing database._client doesn't try to
# initialize a real Firestore client (which needs credentials).
firestore_stub = _stub_module("google.cloud.firestore")
firestore_stub.Client = MagicMock(return_value=MagicMock())
firestore_stub.Query = MagicMock()


class _BaseFilter:  # database.daily_summaries imports FieldFilter from this path
    pass


fbq_stub = _stub_module("google.cloud.firestore_v1.base_query")
fbq_stub.FieldFilter = MagicMock()

import database.daily_summaries as daily_summaries  # noqa: E402


def test_update_daily_summary_forces_id_to_existing_doc_id():
    """
    Regression: generator always allocates a fresh UUID. update_daily_summary
    must pin the stored payload's id back to the existing summary_id so
    readers that key off summary['id'] keep finding the same row.
    """
    captured = {}

    fake_set = MagicMock(side_effect=lambda payload: captured.setdefault("payload", payload))
    fake_doc = MagicMock(set=fake_set)
    fake_collection = MagicMock(document=MagicMock(return_value=fake_doc))
    fake_user_doc = MagicMock(collection=MagicMock(return_value=fake_collection))

    original_db = daily_summaries.db
    try:
        daily_summaries.db = MagicMock(
            collection=MagicMock(return_value=MagicMock(document=MagicMock(return_value=fake_user_doc)))
        )

        daily_summaries.update_daily_summary(
            "uid-abc",
            "existing-summary-id",
            {
                "id": "freshly-generated-uuid-from-llm",
                "date": "2026-06-02",
                "headline": "Updated",
            },
        )
    finally:
        daily_summaries.db = original_db

    payload = captured["payload"]
    assert payload["id"] == "existing-summary-id", (
        "update_daily_summary must overwrite the generator's UUID with the "
        "existing doc id so regenerate replaces in place"
    )
    assert payload["date"] == "2026-06-02"
    assert payload["headline"] == "Updated"


def test_update_daily_summary_preserves_other_fields():
    """All non-id fields pass through unchanged."""
    captured = {}

    fake_set = MagicMock(side_effect=lambda payload: captured.setdefault("payload", payload))
    fake_doc = MagicMock(set=fake_set)
    fake_collection = MagicMock(document=MagicMock(return_value=fake_doc))
    fake_user_doc = MagicMock(collection=MagicMock(return_value=fake_collection))

    original_db = daily_summaries.db
    try:
        daily_summaries.db = MagicMock(
            collection=MagicMock(return_value=MagicMock(document=MagicMock(return_value=fake_user_doc)))
        )

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
    finally:
        daily_summaries.db = original_db

    payload = captured["payload"]
    assert payload["stats"] == {"total_conversations": 7}
    assert payload["regenerated_at"] == "2026-06-02T12:00:00"
    assert payload["visibility"] == "shared"
    assert payload["day_emoji"] == "🎉"


if __name__ == "__main__":
    test_update_daily_summary_forces_id_to_existing_doc_id()
    test_update_daily_summary_preserves_other_fields()
    print("OK")
