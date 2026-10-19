"""Unit test for conversation merge webhook rollback guard (#22413).

Ensures that derived effects (such as the conversation_created developer webhook)
are deferred during merge processing and not emitted if review overlay transfer
conflicts and triggers target cleanup/rollback.
"""

import os
from unittest.mock import MagicMock, call
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import utils.conversations.merge_conversations as merge
from utils.conversations.processing_trigger import ProcessingTrigger


def _setup_merge_mocks(monkeypatch, *, transfer_side_effect=None):
    mock_source_1 = {
        "id": "c1",
        "created_at": "2026-10-19T00:00:00Z",
        "started_at": "2026-10-19T00:00:00Z",
        "finished_at": "2026-10-19T00:05:00Z",
        "language": "en",
        "source": "omi",
        "transcript_segments": [],
        "photos": [],
        "audio_files": [],
        "deleted": False,
    }
    mock_source_2 = {
        "id": "c2",
        "created_at": "2026-10-19T00:06:00Z",
        "started_at": "2026-10-19T00:06:00Z",
        "finished_at": "2026-10-19T00:10:00Z",
        "language": "en",
        "source": "omi",
        "transcript_segments": [],
        "photos": [],
        "audio_files": [],
        "deleted": False,
    }

    def _get_conv(uid, conv_id):
        if conv_id == "c1":
            return dict(mock_source_1)
        if conv_id == "c2":
            return dict(mock_source_2)
        return None

    monkeypatch.setattr(merge.conversations_db, "get_conversation", _get_conv)
    monkeypatch.setattr(merge, "_copy_audio_chunks_for_merge", lambda uid, convs, new_id: [])
    monkeypatch.setattr(merge.lifecycle_service, "create_processing_conversation", MagicMock())
    monkeypatch.setattr(merge.lifecycle_service, "complete", MagicMock())
    monkeypatch.setattr(merge, "send_merge_completed_message", MagicMock())
    monkeypatch.setattr(merge, "_delete_conversation_and_related_data", MagicMock())

    derived_effects_fn = MagicMock()

    def fake_process_conversation(uid, lang, conv, **kwargs):
        observer = kwargs.get("derived_effects_observer")
        if observer is not None:
            observer(derived_effects_fn)
        return conv

    monkeypatch.setattr("utils.conversations.process_conversation.process_conversation", fake_process_conversation)

    mock_transfer = MagicMock()
    if transfer_side_effect:
        mock_transfer.side_effect = transfer_side_effect
    else:
        mock_transfer.return_value = True

    import database.review_overlay_merge as rom

    monkeypatch.setattr(rom, "transfer", mock_transfer)

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
