import pytest
from services.frame_request_retention import run_frame_request_retention_maintenance
from services import frame_request_retention
from .test_frame_request_retention_pagination import _Client
from services.frame_request_retention import FrameCleanupPage

@pytest.fixture(autouse=True)
def _plain_firestore_transactions(monkeypatch):
    monkeypatch.setattr(frame_request_retention.firestore, "transactional", lambda function: function)

def test_run_frame_request_retention_maintenance_invalid_limits():
    with pytest.raises(ValueError, match="maintenance limits must be positive"):
        run_frame_request_retention_maintenance(user_limit=0)
    with pytest.raises(ValueError, match="maintenance limits must be positive"):
        run_frame_request_retention_maintenance(rows_per_user=0)


def test_run_frame_request_retention_maintenance_lease_failure(monkeypatch):
    client = _Client(["a"])
    monkeypatch.setattr(frame_request_retention, "_acquire_lease", lambda *_args, **_kwargs: None)
    result = run_frame_request_retention_maintenance(
        user_limit=1,
        rows_per_user=2,
        firestore_client=client,
    )
    assert result == {
        "users_scanned": 0,
        "rows_pruned": 0,
        "pixels_cleaned": 0,
        "metadata_deleted": 0,
        "vision_outputs_stripped": 0,
        "users_page_full": 0,
        "accounts_with_errors": 0,
        "lease_skipped": 1,
    }


def test_run_frame_request_retention_maintenance_happy_path_and_counters(monkeypatch):
    client = _Client(["a", "b", "c"])
    monkeypatch.setattr(frame_request_retention, "prune_expired_frame_requests", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_frame_request_pixels",
        lambda *_args, **_kwargs: FrameCleanupPage(processed=3, cleaned=3),
    )
    monkeypatch.setattr(
        frame_request_retention,
        "delete_expired_frame_request_metadata",
        lambda *_args, **_kwargs: FrameCleanupPage(processed=4, cleaned=4),
    )
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_expired_frame_vision_outputs",
        lambda *_args, **_kwargs: FrameCleanupPage(processed=1, cleaned=1),
    )
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_ambiguous_frame_upload_pixels",
        lambda *_args, **_kwargs: FrameCleanupPage(processed=2, cleaned=2),
    )
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_conversation_frame_deletion_outbox",
        lambda *_args, **_kwargs: FrameCleanupPage(processed=0, cleaned=0),
    )
    monkeypatch.setattr(
        frame_request_retention, "prune_expired_conversation_keyframe_jobs", lambda *_args, **_kwargs: 0
    )
    monkeypatch.setattr(frame_request_retention, "emit_posthog_event", lambda *_args, **_kwargs: None)

    result = frame_request_retention.run_frame_request_retention_maintenance(
        user_limit=2,
        rows_per_user=10,
        firestore_client=client,
    )

    assert result["users_scanned"] == 2
    assert result["rows_pruned"] == 4
    assert result["pixels_cleaned"] == 10
    assert result["metadata_deleted"] == 8
    assert result["vision_outputs_stripped"] == 2
    assert result["users_page_full"] == 1
    assert result["accounts_with_errors"] == 0
    assert result["lease_skipped"] == 0
