"""Hermetic unit tests verifying defensive boundary guards in database.memory_apply_store."""

from datetime import datetime, timezone
import os
from unittest.mock import MagicMock
import pytest

from database.memory_apply_store import (
    apply_long_term_patch_firestore,
    atomic_bump_source_generation,
    cleanup_expired_memory_deletion_receipts,
    privacy_deletion_receipt_id,
    replace_conversation_source_firestore,
    tombstone_memory_items_firestore,
)
from models.memory_apply import MemoryControlState
from models.memory_operations import MemoryOperation, MemoryOperationType


def test_privacy_deletion_receipt_id_guards_inputs(monkeypatch):
    """Verify privacy_deletion_receipt_id rejects empty or whitespace-only identifiers."""
    monkeypatch.setenv("ENCRYPTION_SECRET", "x" * 32)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        privacy_deletion_receipt_id("", "mem-1")
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        privacy_deletion_receipt_id("   ", "mem-1")
    with pytest.raises(ValueError, match="memory_id must be a non-empty string"):
        privacy_deletion_receipt_id("usr-1", "")
    with pytest.raises(ValueError, match="memory_id must be a non-empty string"):
        privacy_deletion_receipt_id("usr-1", "   ")

    rid = privacy_deletion_receipt_id("usr-1", "mem-1")
    assert rid.startswith("receipt_")
    assert len(rid) == len("receipt_") + 64


def test_cleanup_expired_receipts_guards_uid_and_client():
    """Verify cleanup_expired_memory_deletion_receipts validates uid and db_client."""
    mock_db = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cleanup_expired_memory_deletion_receipts("", db_client=mock_db)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        cleanup_expired_memory_deletion_receipts("   ", db_client=mock_db)
    with pytest.raises(ValueError, match="db_client must not be None"):
        cleanup_expired_memory_deletion_receipts("usr-1", db_client=None)


def test_cleanup_expired_receipts_guards_limit_type():
    """Verify cleanup_expired_memory_deletion_receipts validates limit type."""
    mock_db = MagicMock()
    with pytest.raises(TypeError, match="limit must be an integer"):
        cleanup_expired_memory_deletion_receipts("usr-1", db_client=mock_db, limit="10")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="limit must be an integer"):
        cleanup_expired_memory_deletion_receipts("usr-1", db_client=mock_db, limit=True)  # type: ignore[arg-type]


def test_cleanup_expired_receipts_normalizes_timestamps():
    """Verify cleanup_expired_memory_deletion_receipts normalizes ISO strings and naive datetimes."""
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()
    mock_db.collection.return_value = mock_coll
    mock_coll.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = iter([])

    # Empty string raises ValueError
    with pytest.raises(ValueError, match="timestamp string cannot be empty or whitespace"):
        cleanup_expired_memory_deletion_receipts("usr-1", db_client=mock_db, now="")

    # Malformed ISO string raises ValueError
    with pytest.raises(ValueError, match="Invalid ISO timestamp string"):
        cleanup_expired_memory_deletion_receipts("usr-1", db_client=mock_db, now="bad-timestamp")

    # Invalid type raises TypeError
    with pytest.raises(TypeError, match="now must be a datetime, ISO timestamp string, or None"):
        cleanup_expired_memory_deletion_receipts("usr-1", db_client=mock_db, now=12345)  # type: ignore[arg-type]

    # Valid ISO string succeeds
    deleted = cleanup_expired_memory_deletion_receipts("usr-1", db_client=mock_db, now="2026-09-30T12:00:00Z")
    assert deleted == 0


def test_apply_long_term_patch_firestore_guards_inputs():
    """Verify apply_long_term_patch_firestore validates uid, operation_id, and patch_payload."""
    mock_db = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        apply_long_term_patch_firestore(uid="", operation_id="op-1", patch_payload={}, db_client=mock_db)
    with pytest.raises(ValueError, match="operation_id must be a non-empty string"):
        apply_long_term_patch_firestore(uid="usr-1", operation_id="", patch_payload={}, db_client=mock_db)
    with pytest.raises(TypeError, match="patch_payload must be a dictionary"):
        apply_long_term_patch_firestore(uid="usr-1", operation_id="op-1", patch_payload=None, db_client=mock_db)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="db_client must not be None"):
        apply_long_term_patch_firestore(uid="usr-1", operation_id="op-1", patch_payload={}, db_client=None)


def test_replace_conversation_source_firestore_guards_inputs():
    """Verify replace_conversation_source_firestore validates required identifiers."""
    mock_db = MagicMock()
    dummy_op = MagicMock(spec=MemoryOperation)
    dummy_control = MemoryControlState(
        uid="usr-1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        linearized_sequence=1,
    )

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        replace_conversation_source_firestore(
            uid="",
            conversation_id="conv-1",
            replacement_id="rep-1",
            replacement_digest="dig-1",
            replacement_operation=dummy_op,
            observed_control=dummy_control,
            expected_source_items=[],
            expected_reactivation_items=[],
            writes=[],
            db_client=mock_db,
        )

    with pytest.raises(ValueError, match="conversation_id must be a non-empty string"):
        replace_conversation_source_firestore(
            uid="usr-1",
            conversation_id="",
            replacement_id="rep-1",
            replacement_digest="dig-1",
            replacement_operation=dummy_op,
            observed_control=dummy_control,
            expected_source_items=[],
            expected_reactivation_items=[],
            writes=[],
            db_client=mock_db,
        )

    with pytest.raises(ValueError, match="db_client must not be None"):
        replace_conversation_source_firestore(
            uid="usr-1",
            conversation_id="conv-1",
            replacement_id="rep-1",
            replacement_digest="dig-1",
            replacement_operation=dummy_op,
            observed_control=dummy_control,
            expected_source_items=[],
            expected_reactivation_items=[],
            writes=[],
            db_client=None,
        )


def test_tombstone_memory_items_firestore_guards_inputs():
    """Verify tombstone_memory_items_firestore validates uid, reason, and db_client."""
    mock_db = MagicMock()
    dummy_control = MemoryControlState(
        uid="usr-1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        linearized_sequence=1,
    )
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        tombstone_memory_items_firestore(
            uid="",
            reason="user delete",
            observed_control=dummy_control,
            expected_items=[],
            preserved_evidence_ids=[],
            deletion_gate_token="token-1",
            db_client=mock_db,
        )

    with pytest.raises(ValueError, match="reason must be a non-empty string"):
        tombstone_memory_items_firestore(
            uid="usr-1",
            reason="",
            observed_control=dummy_control,
            expected_items=[],
            preserved_evidence_ids=[],
            deletion_gate_token="token-1",
            db_client=mock_db,
        )

    with pytest.raises(ValueError, match="db_client must not be None"):
        tombstone_memory_items_firestore(
            uid="usr-1",
            reason="user delete",
            observed_control=dummy_control,
            expected_items=[],
            preserved_evidence_ids=[],
            deletion_gate_token="token-1",
            db_client=None,
        )


def test_atomic_bump_source_generation_guards_inputs():
    """Verify atomic_bump_source_generation validates uid and db_client."""
    mock_db = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        atomic_bump_source_generation("", db_client=mock_db)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        atomic_bump_source_generation("   ", db_client=mock_db)
    with pytest.raises(ValueError, match="db_client must not be None"):
        atomic_bump_source_generation("usr-1", db_client=None)
