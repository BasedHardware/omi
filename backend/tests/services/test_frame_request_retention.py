from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from services.frame_request_retention import (
    run_frame_request_retention_maintenance,
    _acquire_lease,
    _release_lease,
    _load_user_page,
    _store_user_cursor,
    FrameCleanupPage,
)


@pytest.fixture
def mock_firestore():
    client = MagicMock()
    return client


@patch("services.frame_request_retention.get_firestore_client")
@patch("services.frame_request_retention.emit_posthog_event")
@patch("services.frame_request_retention._acquire_lease")
@patch("services.frame_request_retention._release_lease")
@patch("services.frame_request_retention._load_user_page")
@patch("services.frame_request_retention._store_user_cursor")
@patch("services.frame_request_retention.account_deletion_blocks_user_work")
@patch("services.frame_request_retention.prune_expired_conversation_keyframe_jobs")
@patch("services.frame_request_retention.prune_expired_frame_requests")
@patch("services.frame_request_retention.cleanup_frame_request_pixels")
@patch("services.frame_request_retention.delete_expired_frame_request_metadata")
@patch("services.frame_request_retention.cleanup_expired_frame_vision_outputs")
@patch("services.frame_request_retention.cleanup_ambiguous_frame_upload_pixels")
@patch("services.frame_request_retention.cleanup_conversation_frame_deletion_outbox")
def test_run_maintenance_no_lease(
    cleanup_conversation_frame_deletion_outbox,
    cleanup_ambiguous_frame_upload_pixels,
    cleanup_expired_frame_vision_outputs,
    delete_expired_frame_request_metadata,
    cleanup_frame_request_pixels,
    prune_expired_frame_requests,
    prune_expired_conversation_keyframe_jobs,
    account_deletion_blocks_user_work,
    _store_user_cursor,
    _load_user_page,
    _release_lease,
    _acquire_lease,
    emit_posthog_event,
    get_firestore_client,
    mock_firestore,
):
    get_firestore_client.return_value = mock_firestore
    _acquire_lease.return_value = None

    result = run_frame_request_retention_maintenance(user_limit=10, rows_per_user=10)

    assert result["lease_skipped"] == 1
    _load_user_page.assert_not_called()
    emit_posthog_event.assert_not_called()


def test_run_maintenance_invalid_limits():
    with pytest.raises(ValueError):
        run_frame_request_retention_maintenance(user_limit=0, rows_per_user=10)


def test_acquire_lease(mock_firestore):
    mock_transaction = MagicMock()
    mock_firestore.transaction.return_value = mock_transaction

    mock_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_ref

    mock_snapshot = MagicMock()
    mock_snapshot.exists = False
    mock_ref.get.return_value = mock_snapshot

    now = datetime.now(timezone.utc)

    generation = _acquire_lease(mock_firestore, owner="test-owner", now=now)
    assert generation == 1
    mock_transaction.set.assert_called_once()


def test_acquire_lease_active(mock_firestore):
    mock_transaction = MagicMock()
    mock_firestore.transaction.return_value = mock_transaction

    mock_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_ref

    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    now = datetime.now(timezone.utc)
    mock_snapshot.to_dict.return_value = {"lease_expires_at": now + timedelta(minutes=5)}
    mock_ref.get.return_value = mock_snapshot

    generation = _acquire_lease(mock_firestore, owner="test-owner", now=now)
    assert generation is None
    mock_transaction.set.assert_not_called()


def test_release_lease(mock_firestore):
    mock_transaction = MagicMock()
    mock_firestore.transaction.return_value = mock_transaction

    mock_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_ref

    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {"lease_owner": "test-owner", "lease_generation": 1}
    mock_ref.get.return_value = mock_snapshot

    success = _release_lease(mock_firestore, owner="test-owner", generation=1)
    assert success is True
    mock_transaction.update.assert_called_once()


def test_release_lease_wrong_owner(mock_firestore):
    mock_transaction = MagicMock()
    mock_firestore.transaction.return_value = mock_transaction

    mock_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_ref

    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {"lease_owner": "wrong-owner", "lease_generation": 1}
    mock_ref.get.return_value = mock_snapshot

    success = _release_lease(mock_firestore, owner="test-owner", generation=1)
    assert success is False
    mock_transaction.update.assert_not_called()


@patch("services.frame_request_retention.get_firestore_client")
@patch("services.frame_request_retention.emit_posthog_event")
@patch("services.frame_request_retention._acquire_lease")
@patch("services.frame_request_retention._release_lease")
@patch("services.frame_request_retention._load_user_page")
@patch("services.frame_request_retention._store_user_cursor")
@patch("services.frame_request_retention.account_deletion_blocks_user_work")
@patch("services.frame_request_retention.prune_expired_conversation_keyframe_jobs")
@patch("services.frame_request_retention.prune_expired_frame_requests")
@patch("services.frame_request_retention.cleanup_frame_request_pixels")
@patch("services.frame_request_retention.delete_expired_frame_request_metadata")
@patch("services.frame_request_retention.cleanup_expired_frame_vision_outputs")
@patch("services.frame_request_retention.cleanup_ambiguous_frame_upload_pixels")
@patch("services.frame_request_retention.cleanup_conversation_frame_deletion_outbox")
def test_run_maintenance_success(
    cleanup_conversation_frame_deletion_outbox,
    cleanup_ambiguous_frame_upload_pixels,
    cleanup_expired_frame_vision_outputs,
    delete_expired_frame_request_metadata,
    cleanup_frame_request_pixels,
    prune_expired_frame_requests,
    prune_expired_conversation_keyframe_jobs,
    account_deletion_blocks_user_work,
    _store_user_cursor,
    _load_user_page,
    _release_lease,
    _acquire_lease,
    emit_posthog_event,
    get_firestore_client,
    mock_firestore,
):
    get_firestore_client.return_value = mock_firestore
    _acquire_lease.return_value = 1

    mock_user = MagicMock()
    mock_user.id = "user-123"
    _load_user_page.return_value = ([mock_user], "next-cursor", [])

    account_deletion_blocks_user_work.return_value = False

    prune_expired_frame_requests.return_value = 10
    cleanup_frame_request_pixels.return_value = FrameCleanupPage(processed=10, cleaned=5)
    delete_expired_frame_request_metadata.return_value = FrameCleanupPage(processed=10, cleaned=5)
    cleanup_expired_frame_vision_outputs.return_value = FrameCleanupPage(processed=10, cleaned=5)
    cleanup_ambiguous_frame_upload_pixels.return_value = FrameCleanupPage(processed=10, cleaned=5)
    cleanup_conversation_frame_deletion_outbox.return_value = FrameCleanupPage(processed=10, cleaned=5)

    _store_user_cursor.return_value = True

    result = run_frame_request_retention_maintenance(user_limit=10, rows_per_user=100)

    assert result["lease_skipped"] == 0
    assert result["users_scanned"] == 1
    assert result["rows_pruned"] == 10
    assert result["pixels_cleaned"] == 15  # 5 + 5 + 5
    assert result["metadata_deleted"] == 5
    assert result["vision_outputs_stripped"] == 5
    assert result["cursor_committed"] == 1

    _release_lease.assert_called_once()
    _store_user_cursor.assert_called_once()
    emit_posthog_event.assert_called_once()


@patch("services.frame_request_retention.get_firestore_client")
@patch("services.frame_request_retention.emit_posthog_event")
@patch("services.frame_request_retention._acquire_lease")
@patch("services.frame_request_retention._release_lease")
@patch("services.frame_request_retention._load_user_page")
@patch("services.frame_request_retention._store_user_cursor")
@patch("services.frame_request_retention.account_deletion_blocks_user_work")
@patch("services.frame_request_retention.prune_expired_conversation_keyframe_jobs")
@patch("services.frame_request_retention.prune_expired_frame_requests")
@patch("services.frame_request_retention.cleanup_frame_request_pixels")
@patch("services.frame_request_retention.delete_expired_frame_request_metadata")
@patch("services.frame_request_retention.cleanup_expired_frame_vision_outputs")
@patch("services.frame_request_retention.cleanup_ambiguous_frame_upload_pixels")
@patch("services.frame_request_retention.cleanup_conversation_frame_deletion_outbox")
def test_run_maintenance_with_failures(
    cleanup_conversation_frame_deletion_outbox,
    cleanup_ambiguous_frame_upload_pixels,
    cleanup_expired_frame_vision_outputs,
    delete_expired_frame_request_metadata,
    cleanup_frame_request_pixels,
    prune_expired_frame_requests,
    prune_expired_conversation_keyframe_jobs,
    account_deletion_blocks_user_work,
    _store_user_cursor,
    _load_user_page,
    _release_lease,
    _acquire_lease,
    emit_posthog_event,
    get_firestore_client,
    mock_firestore,
):
    get_firestore_client.return_value = mock_firestore
    _acquire_lease.return_value = 1

    mock_user = MagicMock()
    mock_user.id = "user-123"
    _load_user_page.return_value = ([mock_user], "next-cursor", [])

    account_deletion_blocks_user_work.side_effect = Exception("DB error")

    mock_retry_ref = MagicMock()
    mock_retry_col = MagicMock()
    mock_retry_col.document.return_value = mock_retry_ref

    mock_state_ref = MagicMock()
    mock_state_col = MagicMock()
    mock_state_col.document.return_value = mock_state_ref
    mock_state_ref.collection.return_value = mock_retry_col

    mock_firestore.collection.return_value = mock_state_col

    result = run_frame_request_retention_maintenance(user_limit=10, rows_per_user=100)

    assert result["accounts_with_errors"] == 1
    mock_retry_ref.set.assert_called_once()

    prune_expired_frame_requests.assert_not_called()


def test_store_user_cursor(mock_firestore):
    mock_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_ref

    mock_transaction = MagicMock()
    mock_firestore.transaction.return_value = mock_transaction

    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {"lease_owner": "test-owner", "lease_generation": 1}
    mock_ref.get.return_value = mock_snapshot

    success = _store_user_cursor(
        mock_firestore,
        cursor_uid="next-cursor",
        retry_cursor_uid="retry-cursor",
        lease_owner="test-owner",
        lease_generation=1,
    )

    assert success is True
    mock_transaction.set.assert_called_once()


def test_store_user_cursor_without_lease(mock_firestore):
    mock_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_ref

    success = _store_user_cursor(mock_firestore, cursor_uid="next-cursor")

    assert success is True
    mock_ref.set.assert_called_once()


def test_load_user_page(mock_firestore):
    mock_state_ref = MagicMock()
    mock_firestore.collection().document.return_value = mock_state_ref

    mock_state_snapshot = MagicMock()
    mock_state_snapshot.exists = True
    mock_state_snapshot.to_dict.return_value = {"cursor_uid": "user-2", "retry_cursor_uid": ""}
    mock_state_ref.get.return_value = mock_state_snapshot

    mock_retry_query = MagicMock()
    mock_retry_col = MagicMock()
    mock_retry_col.order_by.return_value = mock_retry_query

    mock_state_ref.collection.return_value = mock_retry_col
    mock_retry_query.limit().stream.return_value = []

    mock_users_ref = MagicMock()
    mock_firestore.collection.return_value = mock_users_ref

    mock_query = MagicMock()
    mock_users_ref.order_by.return_value = mock_query
    mock_query.start_after.return_value = mock_query

    mock_user3 = MagicMock()
    mock_user3.id = "user-3"
    mock_user4 = MagicMock()
    mock_user4.id = "user-4"
    mock_user5 = MagicMock()
    mock_user5.id = "user-5"

    mock_query.limit().stream.return_value = [mock_user3, mock_user4, mock_user5]

    users, next_cursor, retry_uids = _load_user_page(mock_firestore, user_limit=2)

    assert len(users) == 2
    assert users[0].id == "user-3"
    assert users[1].id == "user-4"
    assert next_cursor == "user-4"
    assert retry_uids == []


def test_drain_due_pages():
    from services.frame_request_retention import _drain_due_pages

    mock_op = MagicMock()
    mock_op.side_effect = [FrameCleanupPage(processed=10, cleaned=5), FrameCleanupPage(processed=5, cleaned=2)]

    total, more_due = _drain_due_pages(mock_op, page_size=10, max_pages=8)

    assert total == 7
    assert more_due is False
    assert mock_op.call_count == 2


def test_drain_due_pages_max_pages():
    from services.frame_request_retention import _drain_due_pages

    mock_op = MagicMock()
    mock_op.side_effect = [
        FrameCleanupPage(processed=10, cleaned=5),
        FrameCleanupPage(processed=10, cleaned=5),
        FrameCleanupPage(processed=10, cleaned=5),
    ]

    total, more_due = _drain_due_pages(mock_op, page_size=10, max_pages=2)

    assert total == 10
    assert more_due is True
    assert mock_op.call_count == 2
