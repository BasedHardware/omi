"""Resilience tests for short_term_memories and sync_bridges database modules.

Covers:
- Input guards for empty / whitespace uid, short_term_id, source_id
- Graceful handling of concurrent deletion (NotFound) in mark_consolidated
- Uninterrupted cascade deletion in tombstone_source when concurrent NotFound occurs
- Input guards and NotFound handling in mark_sync_bridge_cleaned
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

import database.short_term_memories as stm
import database.sync_bridges as sb


def _make_fake_doc(doc_id: str, data: dict, update_side_effect=None):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    if update_side_effect:
        doc.reference.update.side_effect = update_side_effect
    return doc


# =====================================================================
# short_term_memories: mark_consolidated
# =====================================================================


@pytest.mark.parametrize("invalid_uid", ["", "   ", "\t\n", None])
def test_mark_consolidated_guards_invalid_uid(monkeypatch, invalid_uid):
    mock_db = MagicMock()
    monkeypatch.setattr(stm, "db", mock_db)

    # Must return cleanly without attempting collection/document operations
    stm.mark_consolidated(invalid_uid, "st-1", "commit-1")
    mock_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_short_term_id", ["", "   ", "\t\n", None])
def test_mark_consolidated_guards_invalid_short_term_id(monkeypatch, invalid_short_term_id):
    mock_db = MagicMock()
    monkeypatch.setattr(stm, "db", mock_db)

    stm.mark_consolidated("user-1", invalid_short_term_id, "commit-1")
    mock_db.collection.assert_not_called()


def test_mark_consolidated_catches_notfound_on_concurrent_deletion(monkeypatch):
    doc_ref = MagicMock()
    doc_ref.get.return_value.exists = True
    doc_ref.update.side_effect = NotFound("404 No document to update")

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
    monkeypatch.setattr(stm, "db", fake_db)

    # Must not raise NotFound when concurrent deletion happens between get() and update()
    stm.mark_consolidated("user-1", "st-1", "commit-1")
    doc_ref.update.assert_called_once()


# =====================================================================
# short_term_memories: tombstone_source
# =====================================================================


@pytest.mark.parametrize("invalid_uid", ["", "   ", "\t\n", None])
def test_tombstone_source_guards_invalid_uid(monkeypatch, invalid_uid):
    mock_db = MagicMock()
    monkeypatch.setattr(stm, "db", mock_db)

    result = stm.tombstone_source(invalid_uid, "source-1")
    assert result == []
    mock_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_source_id", ["", "   ", "\t\n", None])
def test_tombstone_source_guards_invalid_source_id(monkeypatch, invalid_source_id):
    mock_db = MagicMock()
    monkeypatch.setattr(stm, "db", mock_db)

    result = stm.tombstone_source("user-1", invalid_source_id)
    assert result == []
    mock_db.collection.assert_not_called()


def test_tombstone_source_continues_cascade_when_individual_doc_not_found(monkeypatch):
    # Two shadow memory docs reference source-1.
    # doc-1 raises NotFound concurrently during update.
    # doc-2 succeeds.
    doc1 = _make_fake_doc(
        "doc-1",
        {
            "evidence": [{"source_id": "source-1", "content": "fact 1"}],
        },
        update_side_effect=NotFound("404 No document to update"),
    )
    doc2 = _make_fake_doc(
        "doc-2",
        {
            "evidence": [{"source_id": "source-1", "content": "fact 2"}],
        },
    )

    fake_coll = MagicMock()
    fake_coll.stream.return_value = [doc1, doc2]

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value = fake_coll
    monkeypatch.setattr(stm, "db", fake_db)

    tombstoned = stm.tombstone_source("user-1", "source-1")

    # doc1 failed with NotFound but doc2 must be processed
    assert tombstoned == ["doc-2"]
    doc1.reference.update.assert_called_once()
    doc2.reference.update.assert_called_once()


# =====================================================================
# sync_bridges: mark_sync_bridge_cleaned
# =====================================================================


@pytest.mark.parametrize("invalid_uid", ["", "   ", "\t\n", None])
def test_mark_sync_bridge_cleaned_guards_invalid_uid(invalid_uid):
    client = MagicMock()
    result = sb.mark_sync_bridge_cleaned(invalid_uid, "donor-1", 1, "target-1", firestore_client=client)
    assert result is False
    client.collection.assert_not_called()


@pytest.mark.parametrize("invalid_source_id", ["", "   ", "\t\n", None])
def test_mark_sync_bridge_cleaned_guards_invalid_source_id(invalid_source_id):
    client = MagicMock()
    result = sb.mark_sync_bridge_cleaned("user-1", invalid_source_id, 1, "target-1", firestore_client=client)
    assert result is False
    client.collection.assert_not_called()


def test_mark_sync_bridge_cleaned_returns_false_on_missing_doc(monkeypatch):
    client = MagicMock()
    ref = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = ref

    snapshot = MagicMock()
    snapshot.exists = False
    snapshot.to_dict.return_value = None
    ref.get.return_value = snapshot

    monkeypatch.setattr(sb, "run_transactional", lambda cl, fn, **kw: fn(MagicMock()))

    result = sb.mark_sync_bridge_cleaned("user-1", "donor-1", 1, "target-1", firestore_client=client)
    assert result is False


def test_mark_sync_bridge_cleaned_catches_notfound_in_transaction(monkeypatch):
    client = MagicMock()
    ref = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = ref

    ref.get.side_effect = NotFound("404 Document not found")

    monkeypatch.setattr(sb, "run_transactional", lambda cl, fn, **kw: fn(MagicMock()))

    # Must catch NotFound and return False cleanly
    result = sb.mark_sync_bridge_cleaned("user-1", "donor-1", 1, "target-1", firestore_client=client)
    assert result is False


def test_mark_sync_bridge_cleaned_catches_notfound_from_run_transactional(monkeypatch):
    client = MagicMock()

    def _failing_transactional(*args, **kwargs):
        raise NotFound("404 Document not found during commit")

    monkeypatch.setattr(sb, "run_transactional", _failing_transactional)

    result = sb.mark_sync_bridge_cleaned("user-1", "donor-1", 1, "target-1", firestore_client=client)
    assert result is False
