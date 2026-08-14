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


def test_iter_user_data_export_streams_all_top_level_sections(monkeypatch):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value={"created_at": now}))
    memory_service = MagicMock()
    memory_service.export_memories.return_value = [MagicMock(model_dump=MagicMock(return_value={"id": "mem1"}))]
    memory_service.iter_export_memories.return_value = iter(
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
        "people": [{"id": "person1"}],
        "action_items": [{"id": "task1"}],
        "task_data": {
            **{name: [{"id": f"{name}-1"}] for name in data_export.TASK_EXPORT_COLLECTIONS},
            **{
                export_name: [{"id": f"{parent}-{child}-1", "parent_id": f"{parent}-1"}]
                for export_name, parent, child in data_export.TASK_NESTED_EXPORT_COLLECTIONS
            },
        },
        "chat_messages": [{"id": "msg1", "created_at": "2026-01-02T03:04:05+00:00"}],
    }
    memory_service.iter_export_memories.assert_called_once_with("uid1", include_archive=True)
    data_export.get_standalone_action_items.assert_called_once_with("uid1", limit=1000, offset=0)
    data_export.conversations_db.iter_all_conversations.assert_called_once_with("uid1", include_discarded=True)
    data_export.chat_db.iter_all_messages.assert_called_once_with("uid1")


def test_iter_user_data_export_uses_empty_profile_object(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", MagicMock(return_value=None))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_export_memories=MagicMock(return_value=iter([])))),
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


def test_iter_user_data_export_yields_before_heavy_reads(monkeypatch):
    get_profile = MagicMock(return_value={})
    monkeypatch.setattr(data_export, "get_user_profile", get_profile)
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
        MagicMock(return_value=iter([])),
    )
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", MagicMock(return_value=iter([])))

    chunks = data_export.iter_user_data_export("uid1")

    assert next(chunks) == "{\n"
    get_profile.assert_not_called()


def test_json_default_raises_type_error_for_unsupported_types():
    with pytest.raises(TypeError, match="Type <class 'set'> not serializable"):
        data_export._json_default(set())


def test_iter_user_data_export_does_not_call_list_export(monkeypatch):
    """Large-account export must stream via iter_export_memories, not list materialization."""
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
    memory_service.iter_export_memories.return_value = iter([memory])

    def _boom(*_args, **_kwargs):
        raise AssertionError("export_memories list path must not be used by data export")

    memory_service.export_memories.side_effect = _boom
    monkeypatch.setattr(data_export, "MemoryService", MagicMock(return_value=memory_service))

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert payload["memories"] == [{"id": "mem-stream"}]
    memory_service.iter_export_memories.assert_called_once_with("uid1", include_archive=True)
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
        MagicMock(return_value=MagicMock(iter_export_memories=MagicMock(return_value=iter([])))),
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

    memory_service = MagicMock(iter_export_memories=_failing_iter)
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

    assert not spool.closed
    assert "".join(stream) == "export-body"
    assert spool.closed


def test_memory_spool_is_streamed_in_bounded_chunks(monkeypatch):
    large_content = "x" * (140 * 1024)
    memory = MagicMock(model_dump=MagicMock(return_value={"id": "large", "content": large_content}))
    monkeypatch.setattr(
        data_export,
        "MemoryService",
        MagicMock(return_value=MagicMock(iter_export_memories=MagicMock(return_value=iter([memory])))),
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
    memory_service = MagicMock(iter_export_memories=MagicMock(return_value=iter(exported_memories)))
    get_action_items = MagicMock(side_effect=action_item_pages)
    monkeypatch.setattr(data_export, "MemoryService", MagicMock(return_value=memory_service))
    monkeypatch.setattr(data_export, "get_standalone_action_items", get_action_items)

    payload = json.loads("".join(data_export.iter_user_data_export("uid1")))

    assert len(payload["memories"]) == 1001
    assert payload["memories"][-1] == {"id": "mem-1000"}
    assert len(payload["action_items"]) == 1001
    assert payload["action_items"][-1] == {"id": "task-1000"}
    memory_service.iter_export_memories.assert_called_once_with("uid1", include_archive=True)
    assert get_action_items.call_args_list == [
        call("uid1", limit=1000, offset=0),
        call("uid1", limit=1000, offset=1000),
    ]
