import json
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, call

import pytest

from services.users import data_export

_REAL_ITER_USER_NESTED_SUBCOLLECTION = data_export._iter_user_nested_subcollection


@pytest.fixture(autouse=True)
def _isolate_firestore_collection_iterators(monkeypatch):
    """Default every collection seam to a finite hermetic iterator.

    Individual tests override the relevant seam when they need records. This
    prevents an omitted nested-collection setup from reaching real Firestore
    retry logic and hanging only when the service was imported with production
    dependencies in the full backend suite.
    """
    monkeypatch.setattr(data_export, "_iter_user_subcollection", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export, "_iter_user_nested_subcollection", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversation_photos", MagicMock(return_value=[]))


def test_iter_user_data_export_streams_all_top_level_sections(monkeypatch):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={"created_at": now}))
    memory_service = MagicMock()
    memory_service.export_memories.return_value = [MagicMock(model_dump=MagicMock(return_value={"id": "mem1"}))]
    memory_service.iter_portability_export_memories.return_value = iter(
        [MagicMock(model_dump=MagicMock(return_value={"id": "mem1"}))]
    )
    monkeypatch.setattr(data_export, "MemoryService", MagicMock(return_value=memory_service))
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[{"id": "person1"}]))
    monkeypatch.setattr(
        data_export,
        "get_standalone_action_items",
        MagicMock(return_value=[{"id": "task1"}]),
    )
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        MagicMock(side_effect=lambda _uid, name: iter([{"id": f"{name}-1"}])),
    )
    monkeypatch.setattr(
        data_export,
        "_iter_user_nested_subcollection",
        MagicMock(
            side_effect=lambda _uid, parent, child: iter([{"id": f"{parent}-{child}-1", "parent_id": f"{parent}-1"}])
        ),
    )
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([{"id": "conv1", "is_locked": True}, {"id": "conv2"}])),
    )
    monkeypatch.setattr(
        data_export.chat_db,
        "iter_all_messages",
        MagicMock(return_value=iter([{"id": "msg1", "created_at": now}])),
    )

    body = "".join(data_export.iter_user_data_export("uid1"))
    payload = json.loads(body)

    assert payload == {
        "profile": {"created_at": "2026-01-02T03:04:05+00:00"},
        "conversations": [{"id": "conv1", "is_locked": True}, {"id": "conv2"}],
        "memories": [{"id": "mem1"}],
        "memory_review_data": {name: [{"id": f"{name}-1"}] for name in data_export.MEMORY_REVIEW_EXPORT_COLLECTIONS},
        "memory_ledger_data": {name: [{"id": f"{name}-1"}] for name in data_export.MEMORY_LEDGER_EXPORT_COLLECTIONS},
        "jit_data": {name: [{"id": f"{name}-1"}] for name in data_export.JIT_EXPORT_COLLECTIONS},
        "people": [{"id": "person1"}],
        "action_items": [{"id": "task1"}],
        "frame_vision_receipts": [{"id": "frame_vision_receipts-1"}],
        "conversation_keyframe_jobs": [{"id": "conversation_keyframe_jobs-1"}],
        "task_data": {
            **{name: [{"id": f"{name}-1"}] for name in data_export.TASK_EXPORT_COLLECTIONS},
            **{name: [{"id": f"{name}-1"}] for name in data_export.MEMORY_SWEEP_EXPORT_COLLECTIONS},
            **{
                export_name: [{"id": f"{parent}-{child}-1", "parent_id": f"{parent}-1"}]
                for export_name, parent, child in data_export.TASK_NESTED_EXPORT_COLLECTIONS
            },
        },
        "chat_messages": [{"id": "msg1", "created_at": "2026-01-02T03:04:05+00:00"}],
    }
    memory_service.iter_portability_export_memories.assert_called_once_with("uid1", include_archive=True)
    data_export.get_standalone_action_items.assert_called_once_with("uid1", limit=1000, offset=0)
    data_export.conversations_db.iter_all_conversations.assert_called_once_with("uid1", include_discarded=True)
    data_export.chat_db.iter_all_messages.assert_called_once_with("uid1")


def test_iter_user_data_export_includes_all_jit_history_collections(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: iter([{"id": f"{name}-1"}]) if name in data_export.JIT_EXPORT_COLLECTIONS else iter([]),
    )

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert set(payload["jit_data"]) == set(data_export.JIT_EXPORT_COLLECTIONS)
    assert payload["jit_data"]["jit_trigger_feedback"] == [{"id": "jit_trigger_feedback-1"}]


def test_iter_user_data_export_includes_review_and_correction_history(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: (
            iter([{"id": f"{name}-1", "candidate": {"content": "portable"}}])
            if name in data_export.MEMORY_REVIEW_EXPORT_COLLECTIONS
            else iter([])
        ),
    )

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert set(payload["memory_review_data"]) == set(data_export.MEMORY_REVIEW_EXPORT_COLLECTIONS)
    assert payload["memory_review_data"]["memory_review_queue"][0]["candidate"]["content"] == "portable"


def test_iter_user_data_export_includes_retained_ledger_history(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: (
            iter([{"id": f"{name}-1"}]) if name in data_export.MEMORY_LEDGER_EXPORT_COLLECTIONS else iter([])
        ),
    )

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert set(payload["memory_ledger_data"]) == set(data_export.MEMORY_LEDGER_EXPORT_COLLECTIONS)
    assert payload["memory_ledger_data"]["memory_commits"] == [{"id": "memory_commits-1"}]


def test_iter_user_data_export_uses_empty_profile_object(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value=None))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "_iter_user_subcollection", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([])),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert payload["profile"] == {}


def test_iter_user_data_export_includes_frame_metadata_and_photo_bytes(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: iter(
            [
                {
                    "request_id": "frame-1",
                    "state": "attached",
                    "conversation_id": "conv-1",
                    "storage_id": "storage-1",
                    "content_type": "image/jpeg",
                }
            ]
            if name == "frame_requests"
            else []
        ),
    )
    monkeypatch.setattr(data_export, "download_frame_request_pixels", lambda *_args: b"image-bytes")
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert payload["frame_requests"][0]["request_id"] == "frame-1"
    assert payload["frame_requests"][0]["image_manifest"] == {
        "conversation_id": "conv-1",
        "photo_id": "frame-1",
        "content_type": "image/jpeg",
        "created_at": None,
        "storage_id": "storage-1",
        "bytes_available": True,
        "bytes_base64": "aW1hZ2UtYnl0ZXM=",
    }


def test_retained_image_read_failure_aborts_portability_export(monkeypatch):
    def unavailable(*_args):
        raise RuntimeError("object store temporarily unavailable")

    monkeypatch.setattr(data_export, "download_frame_request_pixels", unavailable)

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {
                "id": "photo-1",
                "storage_id": "storage-1",
                "content_type": "image/jpeg",
            },
        )


@pytest.mark.parametrize("inline", ["not-base64!", 123])
def test_malformed_retained_inline_image_aborts_portability_export(inline):
    with pytest.raises(data_export.PortabilityExportIncomplete, match="inline image bytes"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "base64": inline, "content_type": "image/jpeg"},
        )


@pytest.mark.parametrize("inline", ["===", "b", "not valid base64!!!"])
def test_invalid_base64_retained_inline_image_aborts_portability_export(inline):
    with pytest.raises(data_export.PortabilityExportIncomplete, match="inline image bytes are malformed"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "base64": inline, "content_type": "image/jpeg"},
        )


def test_empty_decoded_base64_retained_inline_image_aborts_portability_export(monkeypatch):
    monkeypatch.setattr(data_export.base64, "b64decode", lambda *args, **kwargs: b"")

    with pytest.raises(data_export.PortabilityExportIncomplete, match="inline image bytes are empty"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "base64": "validbase64", "content_type": "image/jpeg"},
        )


def test_empty_inline_marker_falls_back_to_permanent_storage(monkeypatch):
    download = MagicMock(return_value=b"stored-image")
    monkeypatch.setattr(data_export, "download_frame_request_pixels", download)

    result = data_export._export_photo_manifest(
        "uid1",
        "conv-1",
        {
            "id": "photo-1",
            "base64": "",
            "storage_id": "storage-1",
            "content_type": "image/jpeg",
        },
    )

    assert result["bytes_available"] is True
    assert result["bytes_base64"] == "c3RvcmVkLWltYWdl"
    download.assert_called_once_with("uid1", "storage-1")


def test_non_empty_malformed_inline_data_does_not_fall_back_to_storage(monkeypatch):
    download = MagicMock(return_value=b"stored-image")
    monkeypatch.setattr(data_export, "download_frame_request_pixels", download)

    with pytest.raises(data_export.PortabilityExportIncomplete, match="inline image bytes"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {
                "id": "photo-1",
                "base64": "not-base64!",
                "storage_id": "storage-1",
                "content_type": "image/jpeg",
            },
        )

    download.assert_not_called()


def test_empty_retained_object_aborts_portability_export(monkeypatch):
    monkeypatch.setattr(data_export, "download_frame_request_pixels", lambda *_args: b"")

    with pytest.raises(data_export.PortabilityExportIncomplete, match="object is empty"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "storage_id": "storage-1", "content_type": "image/jpeg"},
        )


@pytest.mark.parametrize("storage_id", [None, "", 123])
def test_missing_or_malformed_retained_image_reference_aborts_portability_export(storage_id):
    with pytest.raises(data_export.PortabilityExportIncomplete, match="reference is missing or malformed"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "storage_id": storage_id, "content_type": "image/jpeg"},
        )


def test_referenced_image_failure_is_raised_before_export_stream_is_returned(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: iter(
            [{"request_id": "frame-1", "state": "attached", "storage_id": "storage-1"}]
            if name == "frame_requests"
            else []
        ),
    )

    def unavailable(*_args):
        raise RuntimeError("retained object unavailable")

    monkeypatch.setattr(data_export, "download_frame_request_pixels", unavailable)

    with pytest.raises(RuntimeError, match="retained object unavailable"):
        data_export.iter_user_data_export("uid1")


@pytest.mark.parametrize("state", ["uploaded", "attached"])
def test_retained_frame_without_storage_reference_fails_before_stream(monkeypatch, state):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: iter([{"request_id": "frame-1", "state": state}]) if name == "frame_requests" else iter([]),
    )

    with pytest.raises(data_export.PortabilityExportIncomplete, match="reference is missing or malformed"):
        data_export.iter_user_data_export("uid1")


@pytest.mark.parametrize("cleanup_state", ["deleted", "not_required"])
def test_terminal_frame_with_converged_cleanup_exports_metadata_despite_audit_storage_id(
    monkeypatch,
    cleanup_state,
):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        "_iter_user_subcollection",
        lambda _uid, name: iter(
            [
                {
                    "request_id": "frame-cleaned",
                    "state": "expired",
                    "storage_id": "deleted-object-audit-id",
                    "cleanup_state": cleanup_state,
                }
            ]
            if name == "frame_requests"
            else []
        ),
    )
    download = MagicMock(side_effect=AssertionError("deleted pixels must not be downloaded"))
    monkeypatch.setattr(data_export, "download_frame_request_pixels", download)

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert payload["frame_requests"] == [
        {
            "request_id": "frame-cleaned",
            "state": "expired",
            "storage_id": "deleted-object-audit-id",
            "cleanup_state": cleanup_state,
        }
    ]
    download.assert_not_called()


def test_iter_user_data_export_includes_legacy_photo_subcollection_without_marker(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([{"id": "conv-legacy"}])),
    )
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversation_photos",
        MagicMock(
            return_value=[("conv-legacy", {"id": "photo-1", "base64": "aW1hZ2U=", "content_type": "image/jpeg"})]
        ),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert payload["conversation_photo_manifest"][0]["photo_id"] == "photo-1"
    assert payload["conversation_photo_manifest"][0]["bytes_available"] is True


def test_iter_user_data_export_preflights_heavy_reads_before_streaming(monkeypatch):
    get_profile = MagicMock(return_value={})
    monkeypatch.setattr(data_export, "get_user_profile", get_profile)
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([])),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    chunks = data_export.iter_user_data_export("uid1")

    get_profile.assert_called_once_with("uid1")
    assert json.loads("".join(chunks))["profile"] == {}


def test_json_default_raises_type_error_for_unsupported_types():
    with pytest.raises(TypeError, match="Type <class 'set'> not serializable"):
        data_export._json_default(set())


def test_iter_user_data_export_does_not_call_list_export(monkeypatch):
    """Large-account export must use the portability stream, not list materialization."""
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([])),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    memory = MagicMock(model_dump=MagicMock(return_value={"id": "mem-stream"}))
    memory_service = MagicMock()
    memory_service.iter_portability_export_memories.return_value = iter([memory])

    def _boom(*_args, **_kwargs):
        raise AssertionError("export_memories list path must not be used by data export")

    memory_service.export_memories.side_effect = _boom
    monkeypatch.setattr(data_export, "MemoryService", MagicMock(return_value=memory_service))

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert payload["memories"] == [{"id": "mem-stream"}]
    memory_service.iter_portability_export_memories.assert_called_once_with("uid1", include_archive=True)
    memory_service.export_memories.assert_not_called()


def test_nested_task_export_carries_owning_parent_id(monkeypatch):
    child = MagicMock(id='event-1')
    child.to_dict.return_value = {'kind': 'progress'}
    parent = MagicMock(id='workstream-1')
    parent.reference.collection.return_value.stream.return_value = [child]
    parent_collection = MagicMock()
    parent_collection.stream.return_value = [parent]
    user_document = MagicMock()
    user_document.collection.return_value = parent_collection
    users_collection = MagicMock()
    users_collection.document.return_value = user_document
    mock_db = MagicMock()
    mock_db.collection.return_value = users_collection
    monkeypatch.setattr(data_export.database_client, 'db', mock_db)

    records = list(_REAL_ITER_USER_NESTED_SUBCOLLECTION('uid1', 'workstreams', 'events'))

    assert records == [{'kind': 'progress', 'id': 'event-1', 'parent_id': 'workstream-1'}]
    mock_db.collection.assert_called_once_with('users')
    users_collection.document.assert_called_once_with('uid1')
    user_document.collection.assert_called_once_with('workstreams')
    parent.reference.collection.assert_called_once_with('events')


def test_iter_user_data_export_skips_none_conversations_and_formats_arrays(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([{"id": "conv1"}, None, {"id": "conv2"}])),
    )
    monkeypatch.setattr(
        data_export.chat_db,
        "iter_all_messages",
        MagicMock(return_value=iter([{"id": "msg1"}, {"id": "msg2"}])),
    )

    body = "".join(data_export.iter_user_data_export("uid1"))
    payload = json.loads(body)

    assert payload["conversations"] == [{"id": "conv1"}, {"id": "conv2"}]
    assert payload["chat_messages"] == [{"id": "msg1"}, {"id": "msg2"}]


def test_iter_user_data_export_does_not_emit_partial_memories_on_iteration_failure(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([])),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    good = MagicMock(model_dump=MagicMock(return_value={"id": "mem-ok"}))

    def _failing_iter(_uid, *, include_archive=True):
        yield good
        raise RuntimeError("memory page unavailable")

    memory_service = MagicMock(iter_portability_export_memories=_failing_iter)
    monkeypatch.setattr(data_export, "MemoryService", MagicMock(return_value=memory_service))

    with pytest.raises(RuntimeError, match="memory page unavailable"):
        data_export.iter_user_data_export("uid1")

    data_export.get_user_profile.assert_not_called()


def test_iter_user_data_export_closes_completed_memory_spool(monkeypatch):
    spool = StringIO("[]")
    monkeypatch.setattr(data_export, "_spool_export_memories_json", MagicMock(return_value=spool))
    monkeypatch.setattr(
        data_export,
        "_iter_user_data_export_from_spool",
        MagicMock(return_value=iter(["export-body"])),
    )

    stream = data_export.iter_user_data_export("uid1")

    assert spool.closed
    assert "".join(stream) == "export-body"


def test_memory_spool_is_streamed_in_bounded_chunks(monkeypatch):
    large_content = "x" * (140 * 1024)
    memory = MagicMock(model_dump=MagicMock(return_value={"id": "large", "content": large_content}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([memory])))),
    )

    spool = data_export._spool_export_memories_json("uid1")
    try:
        chunks = []
        while chunk := spool.read(64 * 1024):
            chunks.append(chunk)
    finally:
        spool.close()

    assert len(chunks) >= 3
    assert max(map(len, chunks)) <= 64 * 1024
    assert json.loads("".join(chunks)) == [{"id": "large", "content": large_content}]


def test_frame_export_pulls_incrementally_instead_of_materializing_collection(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([])))
    pulled = 0

    def rows(_uid, name):
        nonlocal pulled
        if name != "frame_requests":
            return iter([])

        def generate():
            nonlocal pulled
            for index in range(100_000):
                pulled += 1
                yield {"request_id": f"frame-{index}", "state": "pruned"}

        return generate()

    monkeypatch.setattr(data_export, "_iter_user_subcollection", rows)
    stream = data_export._iter_user_data_export_from_spool("uid1", StringIO("[]"))

    for chunk in stream:
        if '"frame_requests"' in chunk:
            break

    assert pulled == 1
    assert next(stream) == "[\n"
    assert pulled == 1


def test_conversation_photo_manifest_spills_to_disk_instead_of_accumulating(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, "get_standalone_action_items", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db, "iter_all_conversations", MagicMock(return_value=iter([{"id": "conv-1"}]))
    )
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversation_photos",
        MagicMock(
            return_value=[
                (
                    "conv-1",
                    {
                        "id": "photo-1",
                        "base64": "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eA==",
                    },
                )
            ]
        ),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))
    real_spooled_file = data_export.tempfile.SpooledTemporaryFile
    created = []

    def tiny_spool(*_args, **kwargs):
        kwargs["max_size"] = 128
        spool = real_spooled_file(**kwargs)
        created.append(spool)
        return spool

    monkeypatch.setattr(data_export.tempfile, "SpooledTemporaryFile", tiny_spool)

    payload = json.loads("".join(data_export._iter_user_data_export_from_spool("uid1", StringIO("[]"))))

    assert (
        payload["conversation_photo_manifest"][0]["bytes_base64"]
        == "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eA=="
    )
    assert created[0]._rolled is True
    assert created[0].closed is True


def test_iter_user_data_export_paginates_complete_collections(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={}))
    monkeypatch.setattr(data_export, "get_people", MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        MagicMock(return_value=iter([])),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    exported_memories = [MagicMock(model_dump=MagicMock(return_value={"id": f"mem-{i}"})) for i in range(1001)]
    action_item_pages = [
        [{"id": f"task-{i}"} for i in range(1000)],
        [{"id": "task-1000"}],
    ]
    memory_service = MagicMock(iter_portability_export_memories=MagicMock(return_value=iter(exported_memories)))
    get_action_items = MagicMock(side_effect=action_item_pages)
    monkeypatch.setattr(data_export, "MemoryService", MagicMock(return_value=memory_service))
    monkeypatch.setattr(data_export, "get_standalone_action_items", get_action_items)

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert len(payload["memories"]) == 1001
    assert payload["memories"][-1] == {"id": "mem-1000"}
    assert len(payload["action_items"]) == 1001
    assert payload["action_items"][-1] == {"id": "task-1000"}
    memory_service.iter_portability_export_memories.assert_called_once_with("uid1", include_archive=True)
    assert get_action_items.call_args_list == [
        call("uid1", limit=1000, offset=0),
        call("uid1", limit=1000, offset=1000),
    ]


def test_legacy_conversation_photo_without_any_bytes_reference_exports_metadata():
    """A broken legacy photo row (empty inline marker, no storage_id) must not
    permanently deny the user their export — there are no durable bytes to
    omit. Frame requests keep the fail-closed contract via require_bytes."""

    manifest = data_export._export_photo_manifest(
        "uid1",
        "conv-1",
        {"id": "photo-legacy", "base64": "", "content_type": "image/jpeg"},
        require_bytes=False,
    )

    assert manifest["bytes_available"] is False
    assert manifest["bytes_unavailable_reason"] == "no_retained_bytes_reference"


def test_export_photo_manifest_require_bytes_missing_reference():
    with pytest.raises(
        data_export.PortabilityExportIncomplete, match="retained image bytes reference is missing or malformed"
    ):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "base64": "", "storage_id": ""},
            require_bytes=True,
        )


def test_export_photo_manifest_malformed_inline_bytes_type():
    with pytest.raises(data_export.PortabilityExportIncomplete, match="retained inline image bytes are malformed"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "base64": 123},
            require_bytes=True,
        )


def test_export_photo_manifest_malformed_inline_bytes_encoding():
    with pytest.raises(data_export.PortabilityExportIncomplete, match="retained inline image bytes are malformed"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "base64": "invalid base64!"},
            require_bytes=True,
        )


def test_export_photo_manifest_valid_inline_bytes():
    import base64

    valid_base64 = base64.b64encode(b"test pixels").decode("ascii")
    manifest = data_export._export_photo_manifest(
        "uid1",
        "conv-1",
        {"id": "photo-1", "base64": valid_base64},
        require_bytes=True,
    )
    assert manifest["bytes_available"] is True
    assert manifest["bytes_base64"] == valid_base64


def test_export_photo_manifest_empty_storage_object(monkeypatch):
    monkeypatch.setattr(data_export, "download_frame_request_pixels", MagicMock(return_value=b""))
    with pytest.raises(data_export.PortabilityExportIncomplete, match="retained image object is empty"):
        data_export._export_photo_manifest(
            "uid1",
            "conv-1",
            {"id": "photo-1", "storage_id": "storage-1"},
            require_bytes=True,
        )
    data_export.download_frame_request_pixels.assert_called_once_with("uid1", "storage-1")


def test_export_photo_manifest_valid_storage_object(monkeypatch):
    monkeypatch.setattr(
        data_export, "download_frame_request_pixels", MagicMock(return_value=b"test pixels from storage")
    )
    manifest = data_export._export_photo_manifest(
        "uid1",
        "conv-1",
        {"id": "photo-1", "storage_id": "storage-1"},
        require_bytes=True,
    )
    assert manifest["bytes_available"] is True
    import base64

    assert manifest["bytes_base64"] == base64.b64encode(b"test pixels from storage").decode("ascii")
    data_export.download_frame_request_pixels.assert_called_once_with("uid1", "storage-1")
