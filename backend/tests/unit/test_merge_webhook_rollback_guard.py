"""Unit test for conversation merge webhook rollback guard (#22413).

Ensures that derived effects (such as the conversation_created developer webhook)
are deferred during merge processing and not emitted if review overlay transfer
conflicts and triggers target cleanup/rollback.
Also asserts per-effect error isolation during deferred effects emission.
"""

import os
import sys
from unittest.mock import MagicMock
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import utils.conversations.merge_conversations as merge


@pytest.fixture(scope="module", autouse=True)
def _warm_merge_imports():
    """perform_merge_async does heavy local imports at call time.
    Charge them to module setup so the fast-unit CPU-time guard measures
    only the call phase."""
    import utils.conversations.process_conversation  # noqa: F401
    import utils.notifications  # noqa: F401


def _setup_merge_mocks(monkeypatch, *, transfer_side_effect=None, custom_effects_observer=None):
    sources = {
        "c1": {
            "id": "c1",
            "created_at": "2026-10-19T00:00:00Z",
            "started_at": None,
            "finished_at": None,
            "language": "en",
            "source": "omi",
            "status": "completed",
            "transcript_segments": [],
            "photos": [],
            "audio_files": [],
            "deleted": False,
        },
        "c2": {
            "id": "c2",
            "created_at": "2026-10-19T00:06:00Z",
            "started_at": None,
            "finished_at": None,
            "language": "en",
            "source": "omi",
            "status": "completed",
            "transcript_segments": [],
            "photos": [],
            "audio_files": [],
            "deleted": False,
        },
    }

    monkeypatch.setattr(merge.conversations_db, "get_conversation", lambda uid, cid: sources.get(cid))
    monkeypatch.setattr(merge, "_normalize_conversation_timestamps", lambda convs: convs)
    monkeypatch.setattr(merge, "_merge_transcript_segments", lambda convs: [])
    monkeypatch.setattr(merge, "_collect_all_photos", lambda uid, convs: [])
    monkeypatch.setattr(merge, "_copy_audio_chunks_for_merge", lambda uid, convs, new_id: [])
    monkeypatch.setattr(merge, "_determine_visibility", lambda convs: "private")
    monkeypatch.setattr(merge, "_shared_client_device_provenance", lambda convs: (None, None))
    monkeypatch.setattr(merge, "is_audio_merge_dispatch_enabled", lambda: False)

    # Hermetic mock for Conversation instance
    mock_conv = MagicMock(
        **{
            "model_dump.return_value": {"id": "new-merge-id", "language": "en", "photos": []},
            "id": "new-merge-id",
            "language": "en",
            "photos": [],
        }
    )
    monkeypatch.setattr(merge, "Conversation", lambda **kw: mock_conv)

    # Mock lifecycle and lease heartbeat
    monkeypatch.setattr(merge.lifecycle_service, "create_processing_conversation", MagicMock(return_value=True))
    monkeypatch.setattr(merge.lifecycle_service, "complete", MagicMock(return_value=True))
    monkeypatch.setattr(merge.lifecycle_service.jobs_db, "renew_processing_lease", lambda *a, **kw: True)
    monkeypatch.setattr(merge.lifecycle_service, "_processing_lease_renewal_interval", lambda: 100.0)

    # Patch notification module
    import utils.notifications as notif_mod
    monkeypatch.setattr(notif_mod, "send_merge_completed_message", MagicMock())

    monkeypatch.setattr(merge, "_delete_conversation_and_related_data", MagicMock())

    derived_effects_fn = MagicMock()

    def fake_process_conversation(uid, lang, conv, **kwargs):
        observer = kwargs.get("derived_effects_observer")
        if observer is not None:
            if custom_effects_observer:
                custom_effects_observer(observer)
            else:
                observer(derived_effects_fn)
        return conv

    pc_mod = sys.modules["utils.conversations.process_conversation"]
    monkeypatch.setattr(pc_mod, "process_conversation", fake_process_conversation)

    mock_transfer = MagicMock()
    if transfer_side_effect:
        mock_transfer.side_effect = transfer_side_effect
    else:
        mock_transfer.return_value = True

    from database import review_overlay_merge
    monkeypatch.setattr(review_overlay_merge, "transfer", mock_transfer)

    mock_handle_failure = MagicMock()
    monkeypatch.setattr(merge, "_handle_merge_failure", mock_handle_failure)

    return derived_effects_fn, mock_handle_failure, mock_transfer


def test_merge_defers_derived_effects_on_transfer_conflict(monkeypatch):
    class ReviewConflict(Exception):
        pass

    derived_effects_fn, mock_handle_failure, _ = _setup_merge_mocks(
        monkeypatch, transfer_side_effect=ReviewConflict("anchor moved")
    )

    merge.perform_merge_async("test-uid", ["c1", "c2"], reprocess=True)

    # Derived effects (webhooks, etc.) must NOT be emitted when transfer fails
    assert not derived_effects_fn.called
    assert mock_handle_failure.called


def test_merge_emits_derived_effects_when_transfer_succeeds(monkeypatch):
    derived_effects_fn, mock_handle_failure, _ = _setup_merge_mocks(monkeypatch)

    merge.perform_merge_async("test-uid", ["c1", "c2"], reprocess=True)

    # Derived effects must be emitted once transfer succeeds and failure handling cannot delete target
    assert derived_effects_fn.called
    assert not mock_handle_failure.called


def test_merge_emits_remaining_effects_when_one_fails(monkeypatch):
    effect1 = MagicMock(side_effect=Exception("transient webhook failure"))
    effect2 = MagicMock()

    def feed_two_effects(observer):
        observer(effect1)
        observer(effect2)

    _, mock_handle_failure, _ = _setup_merge_mocks(monkeypatch, custom_effects_observer=feed_two_effects)

    merge.perform_merge_async("test-uid", ["c1", "c2"], reprocess=True)

    # Per-effect error isolation: effect1 failing must not abort effect2
    assert effect1.called
    assert effect2.called
    assert not mock_handle_failure.called
