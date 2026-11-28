"""Unit tests for timestamp normalization and null retry guards in database.processing_attention."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from database import processing_attention


def test_timing_handles_mixed_naive_aware_and_iso_timestamps():
    """timing() should not raise TypeError when started_at and finished_at mix naive/aware datetimes or ISO strings."""
    naive_start = datetime(2026, 4, 21, 10, 0, 0)
    aware_end = datetime(2026, 4, 21, 10, 2, 30, tzinfo=timezone.utc)

    res_mixed = processing_attention.timing({'started_at': naive_start, 'finished_at': aware_end})
    assert res_mixed['started_at'] == naive_start
    assert res_mixed['duration_seconds'] == 150.0

    res_iso = processing_attention.timing(
        {
            'started_at': '2026-04-21T10:00:00Z',
            'finished_at': '2026-04-21T10:01:15+00:00',
        }
    )
    assert res_iso['duration_seconds'] == 75.0


def test_lease_live_handles_naive_and_iso_timestamps():
    """lease_live() should normalize naive datetimes and ISO-8601 strings before comparing with UTC now."""
    now = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)

    # Naive future lease_expires_at should be treated as UTC and live
    naive_future = datetime(2026, 4, 21, 12, 10, 0)
    assert processing_attention.lease_live({'lease_expires_at': naive_future}, now) is True

    # Naive past lease_expires_at should be expired
    naive_past = datetime(2026, 4, 21, 11, 50, 0)
    assert processing_attention.lease_live({'lease_expires_at': naive_past}, now) is False

    # ISO-8601 string lease_expires_at
    assert processing_attention.lease_live({'lease_expires_at': '2026-04-21T12:05:00Z'}, now) is True

    # Fallback to created_at when lease_expires_at is missing, with naive datetime or ISO string
    naive_recent_created = datetime(2026, 4, 21, 11, 45, 0)  # +1800s -> 12:15:00 > 12:00:00
    assert processing_attention.lease_live({'created_at': naive_recent_created}, now) is True
    assert processing_attention.lease_live({'created_at': '2026-04-21T11:45:00Z'}, now) is True


def test_list_items_and_claim_in_transaction_guard_null_retry_map():
    """Explicit {'retry': None} on an attention item should not raise AttributeError in list_items or claim_in_transaction."""
    item_doc = {
        'id': 'conv-summary:conv-1:abc',
        'conversation_id': 'conv-1',
        'generation': '0:0:',
        'active': True,
        'retryable': False,
        'retry': None,
    }
    conv_doc = {
        'id': 'conv-1',
        'finalization_revision': 0,
        'sync_content_revision': 0,
        'finalization_job_id': '',
        'structured': {'overview': ''},
        'user_title': 'My Conversation',
    }
    failed_claim_doc = {
        'operation_id': 'claim-1:1',
        'state': 'failed',
    }

    item_snap = MagicMock()
    item_snap.to_dict.return_value = dict(item_doc)

    claim_snap = MagicMock()
    claim_snap.exists = True
    claim_snap.to_dict.return_value = dict(failed_claim_doc)

    conv_snap = MagicMock()
    conv_snap.exists = True
    conv_snap.to_dict.return_value = dict(conv_doc)

    # list_items seam: inject the firestore client, route mock children by path segment.
    items_coll = MagicMock()
    items_coll.where.return_value.limit.return_value.stream.return_value = [item_snap]
    claims_coll = MagicMock()
    claims_coll.document.return_value.get.return_value = claim_snap
    conversations_coll = MagicMock()
    conv_ref = MagicMock()
    conv_ref.get.return_value = conv_snap
    conv_ref.collection.side_effect = lambda name: claims_coll
    conversations_coll.document.return_value = conv_ref
    uid_doc = MagicMock()
    uid_doc.collection.side_effect = lambda name: {
        'processing_attention_items': items_coll,
        'conversations': conversations_coll,
    }[name]
    users_coll = MagicMock()
    users_coll.document.return_value = uid_doc
    mock_db = MagicMock()
    mock_db.collection.return_value = users_coll

    items = processing_attention.list_items('uid-1', firestore_client=mock_db)
    assert len(items) == 1
    assert items[0]['retry'] == {'state': 'failed', 'operation_id': 'claim-1:1'}

    # Also test claim_in_transaction when item has {'retry': None, 'retryable': True, 'active': True}
    tx = MagicMock()
    claim_conv_ref = MagicMock()
    claim_conv_ref.id = 'conv-1'
    claim_conv_ref.get.return_value = conv_snap
    claim_conv_ref.collection.side_effect = lambda name: claims_coll

    att_snap = MagicMock()
    att_snap.exists = True
    att_snap.to_dict.return_value = {**item_doc, 'retryable': True, 'retry': None}
    att_ref = MagicMock()
    att_ref.get.return_value = att_snap

    op, owned = processing_attention.claim_in_transaction(tx, claim_conv_ref, 'uid-1', attention_ref=att_ref)
    assert owned is True
    assert op['state'] == 'in_progress'
