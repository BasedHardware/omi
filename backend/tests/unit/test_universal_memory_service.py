"""Focused behavioral checks for the universal MemoryService seam."""

from unittest.mock import MagicMock

import pytest

from tests.unit.test_memory_service_parity import (
    _load_memory_service,
    _sample_memory_dict,
)


class _Snapshot:
    def __init__(self, payload=None, *, exists=True):
        self._payload = payload
        self.exists = exists

    def to_dict(self):
        return self._payload


class _Ref:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, **_kwargs):
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(dict(self.db.docs[self.path]))

    def set(self, payload, merge=False, **_kwargs):
        if merge and self.path in self.db.docs:
            self.db.docs[self.path].update(payload)
        else:
            self.db.docs[self.path] = dict(payload)
        self.db.events.append(("set", self.path))


class _Batch:
    def __init__(self, db):
        self.db = db
        self.ops = []

    def set(self, ref, payload, merge=False):
        self.ops.append((ref, payload, merge))

    def commit(self):
        for ref, payload, merge in self.ops:
            ref.set(payload, merge=merge)
        self.db.events.append(("batch_commit", len(self.ops)))


class _Db:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.events = []

    def document(self, path):
        return _Ref(self, path)

    def batch(self):
        return _Batch(self)


def _memory(service_mod, memory_id, *, content=None):
    payload = _sample_memory_dict(memory_id)
    if content is not None:
        payload["content"] = content
    return service_mod.MemoryDB.model_validate(payload)


def _historical(service_mod, memory_id, *, content=None):
    return service_mod.HistoricalMemoryRecord(
        memory=_memory(service_mod, memory_id, content=content),
        locator=service_mod.MemoryLocator("uid-test", "legacy", memory_id),
    )


@pytest.fixture
def service_mod(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "read")
    return _load_memory_service(monkeypatch)


def test_global_write_pause_blocks_intake_but_not_reads_or_privacy_delete(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    service._canonical.read = MagicMock(return_value=[])
    service._history.read = MagicMock(return_value=[])
    service._history.get = MagicMock(return_value=_historical(service_mod, "memory-1"))
    monkeypatch.setattr(service_mod, "read_canonical_memory_item", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_canonical_status", MagicMock(return_value=None))
    service._canonical.write = MagicMock()
    service._canonical.delete = MagicMock()
    service._write_historical_override = MagicMock()
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", MagicMock())
    monkeypatch.setenv("MEMORY_MODE", "off")

    assert service.read("uid-test") == []
    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.write("uid-test", {"content": "blocked"})
    assert exc_info.value.status_code == 503
    service.delete("uid-test", "memory-1")
    service._canonical.write.assert_not_called()
    service._canonical.delete.assert_not_called()
    service._write_historical_override.assert_called_once_with(
        "uid-test", "memory-1", service_mod.MemoryItemStatus.tombstoned
    )


def test_historical_adapter_uses_injected_firestore_client(service_mod, monkeypatch):
    db = _Db()
    monkeypatch.setattr(service_mod.memories_db, "get_memories", lambda *args, **kwargs: [])
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service.read("uid-test", limit=3)

    # The production helper receives the injected client rather than falling
    # back to database.memories' global Firestore proxy.
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(service_mod.memories_db, "get_memories", capture)
    service.read("uid-test", limit=3)
    assert calls[-1][1]["firestore_client"] is db


def test_mixed_read_deduplicates_canonical_public_identity(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    canonical = _memory(service_mod, "same", content="canonical")
    service._canonical.read = MagicMock(return_value=[canonical])
    service._history.read = MagicMock(
        return_value=[_historical(service_mod, "same", content="old"), _historical(service_mod, "legacy")]
    )

    result = service.read("uid-test", limit=10)
    assert {item.id for item in result} == {"same", "legacy"}
    assert next(item for item in result if item.id == "same").content == "canonical"


def test_default_product_search_includes_historical_rows_without_materializing(service_mod):
    from models.product_memory import MemoryAccessPolicy

    service = service_mod.MemoryService(db_client=_Db())
    service.read = MagicMock(
        side_effect=[
            [
                _memory(service_mod, "canonical", content="coffee canonical"),
                _memory(service_mod, "historical", content="coffee historical"),
            ],
            [],
        ]
    )
    service._canonical.write = MagicMock()

    result = service.default_product_search(
        "uid-test",
        "coffee",
        policy=MemoryAccessPolicy.for_omi_chat(),
    )

    assert [item["memory_id"] for item in result["items"]] == ["canonical", "historical"]
    assert result["total_count"] == 2
    service._canonical.write.assert_not_called()


def test_offset_merge_fetches_a_complete_bounded_prefix(service_mod):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    canonical = [_memory(service_mod, f"canonical-{index:04d}") for index in range(260)]
    historical = [_historical(service_mod, f"legacy-{index:04d}") for index in range(260)]
    service._canonical.read = MagicMock(return_value=canonical)
    service._history.read = MagicMock(return_value=historical)
    service._canonical_status = MagicMock(return_value=None)

    page = service.read("uid-test", limit=10, offset=500)

    assert len(page) == 10
    assert service._canonical.read.call_args.kwargs["limit"] == 510
    assert service._history.read.call_args.kwargs == {
        "limit": 10,
        "offset": 500,
        "device_scope_request": None,
    }


def test_offset_merge_fails_closed_beyond_compatibility_window(service_mod):
    service = service_mod.MemoryService(db_client=_Db())

    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.read("uid-test", limit=2, offset=4999)

    assert exc_info.value.status_code == 413


def test_tombstone_override_suppresses_historical_row_before_pagination(service_mod):
    from database.memory_collections import MemoryCollections

    uid = "uid-test"
    memory_id = "old-deleted"
    path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
    db = _Db({path: {"status": "tombstoned"}})
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service._history.read = MagicMock(return_value=[_historical(service_mod, memory_id)])

    assert service.read(uid, limit=10) == []


def test_new_write_is_canonical_only_for_arbitrary_uid(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    legacy_create = MagicMock()
    monkeypatch.setattr(service_mod.memories_db, "create_memory", legacy_create)
    service._canonical.write = MagicMock(return_value="new-id")

    assert service.write("uid-arbitrary", {"id": "new-id", "content": "new"}) == "new-id"
    service._canonical.write.assert_called_once()
    legacy_create.assert_not_called()
    assert db.docs == {}


def test_legacy_mutation_materializes_stable_id_then_cleans_up(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.write = MagicMock(return_value="legacy-id")
    service._canonical.update_content = MagicMock(return_value=_memory(service_mod, "legacy-id", content="edited"))
    monkeypatch.setattr(service_mod.memories_db, "get_memory", lambda *args, **kwargs: _sample_memory_dict("legacy-id"))
    cleanup = MagicMock()
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", cleanup)
    legacy_edit = MagicMock()
    monkeypatch.setattr(service_mod.memories_db, "edit_memory", legacy_edit)

    result = service.update_content("uid-test", "legacy-id", "edited")
    assert result.content == "edited"
    assert service._canonical.write.call_args.args[1]["id"] == "legacy-id"
    service._canonical.update_content.assert_called_once_with("uid-test", "legacy-id", "edited")
    cleanup.assert_called_once()
    legacy_edit.assert_not_called()
    assert db.docs["users/uid-test/memory_historical_overrides/legacy-id"]["status"] == "active"


def test_legacy_review_refinement_preserves_structured_changes_in_canonical_authority(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.write = MagicMock(return_value="legacy-id")
    updated = MagicMock()
    refine = MagicMock(return_value=updated)
    monkeypatch.setattr(service_mod, "refine_canonical_memory", refine)
    monkeypatch.setattr(
        service_mod, "memory_item_to_memorydb", MagicMock(return_value=_memory(service_mod, "legacy-id"))
    )
    monkeypatch.setattr(service_mod.memories_db, "get_memory", lambda *args, **kwargs: _sample_memory_dict("legacy-id"))
    cleanup = MagicMock()
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", cleanup)

    changes = {"content": {"to": "corrected"}, "location": {"to": "Paris"}}
    result = service.refine("uid-test", "legacy-id", changes)

    assert result.id == "legacy-id"
    refine.assert_called_once_with("uid-test", "legacy-id", changes, db_client=db)
    cleanup.assert_called_once_with("uid-test", "legacy-id", db_client=db)


def test_legacy_baseline_mutation_materializes_then_updates_canonical_metadata(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.write = MagicMock(return_value="legacy-id")
    service._canonical.update_product_fields = MagicMock(return_value=_memory(service_mod, "legacy-id"))
    monkeypatch.setattr(service_mod.memories_db, "get_memory", lambda *args, **kwargs: _sample_memory_dict("legacy-id"))
    cleanup = MagicMock()
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", cleanup)

    service.update_baseline("uid-test", "legacy-id", True)

    service._canonical.update_product_fields.assert_called_once_with(
        "uid-test",
        "legacy-id",
        tags=None,
        category=None,
        is_baseline=True,
    )
    cleanup.assert_called_once_with("uid-test", "legacy-id", db_client=db)


def test_historical_id_inventory_is_complete_by_default(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    expected = [f"legacy-{index}" for index in range(10_005)]
    monkeypatch.setattr(service_mod.memories_db, "get_memory_ids", MagicMock(return_value=expected))

    assert service.list_historical_memory_ids("uid-test") == expected


def test_export_has_no_silent_record_cap(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    monkeypatch.setattr(service_mod, "fetch_authoritative_product_memory_items", lambda **_kwargs: [])
    rows = [_historical(service_mod, f"legacy-{index}") for index in range(10_001)]
    service._history.all_live = MagicMock(return_value=rows)

    exported = service.export_memories("uid-test")

    assert len(exported) == 10_001
    service._history.all_live.assert_called_once_with("uid-test", page_size=500)


def test_export_includes_active_restricted_user_owned_canonical_memory(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    item = MagicMock(
        memory_id="restricted-1",
        status=service_mod.MemoryItemStatus.active,
        tier=service_mod.MemoryTier.long_term,
        sensitivity_labels=["restricted"],
    )
    expected = _memory(service_mod, "restricted-1")
    monkeypatch.setattr(service_mod, "fetch_authoritative_product_memory_items", lambda **_kwargs: [item])
    monkeypatch.setattr(service_mod, "memory_item_to_memorydb", lambda _item: expected)
    service._history.all_live = MagicMock(return_value=[])

    assert service.export_memories("uid-test") == [expected]


def test_canonical_materialization_failure_never_falls_back_to_legacy_write(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.write = MagicMock(side_effect=RuntimeError("canonical unavailable"))
    monkeypatch.setattr(service_mod.memories_db, "get_memory", lambda *args, **kwargs: _sample_memory_dict("legacy-id"))
    legacy_edit = MagicMock()
    monkeypatch.setattr(service_mod.memories_db, "edit_memory", legacy_edit)

    with pytest.raises(RuntimeError, match="canonical unavailable"):
        service.update_content("uid-test", "legacy-id", "edited")
    legacy_edit.assert_not_called()


def test_delete_all_commits_historical_tombstones_before_cleanup(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.delete_all = MagicMock(side_effect=lambda uid: db.events.append(("canonical_delete", uid)))
    service._history.ids = MagicMock(return_value=["legacy-1", "legacy-2"])
    cleanup = MagicMock(side_effect=lambda uid, **kwargs: db.events.append(("cleanup", uid)))
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup_all", cleanup)

    service.delete_all("uid-test")
    assert db.events[0] == ("canonical_delete", "uid-test")
    assert db.events[-1] == ("cleanup", "uid-test")
    assert any(event[0] == "batch_commit" for event in db.events)
    assert db.docs["users/uid-test/memory_historical_overrides/legacy-1"]["status"] == "tombstoned"
    cleanup.assert_called_once()


def test_search_deduplicates_canonical_and_historical_candidates(service_mod):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.search = MagicMock(
        return_value=[service_mod.MemorySearchMatch(_memory(service_mod, "same", content="canonical"), 0.9)]
    )
    service._history.search = MagicMock(
        return_value=[
            service_mod.MemorySearchMatch(_memory(service_mod, "same", content="old"), 0.8),
            service_mod.MemorySearchMatch(_memory(service_mod, "legacy"), 0.7),
        ]
    )

    result = service.search("uid-test", "query", limit=10)
    assert [match.memory.id for match in result] == ["same", "legacy"]
    assert result[0].memory.content == "canonical"


def test_device_scope_keeps_device_neutral_historical_rows(service_mod):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service._history.read = MagicMock(return_value=[_historical(service_mod, "neutral")])
    request = service_mod.DeviceScopeRequest(device_scope="current", client_device_id="macos_abcd1234")

    assert [item.id for item in service.read("uid-test", device_scope_request=request)] == ["neutral"]


def test_delete_batch_validates_every_id_before_any_write(service_mod, monkeypatch):
    """A later missing/locked id cannot leave an earlier valid id deleted."""
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    valid = _historical(service_mod, "valid")
    locked = _historical(service_mod, "locked")
    locked = locked.memory.model_copy(update={"is_locked": True})
    monkeypatch.setattr(
        service._history,
        "get",
        MagicMock(
            side_effect=lambda _uid, memory_id: (
                valid
                if memory_id == "valid"
                else service_mod.HistoricalMemoryRecord(
                    memory=locked,
                    locator=service_mod.MemoryLocator("uid-test", "legacy", "locked"),
                )
            )
        ),
    )
    monkeypatch.setattr(service_mod, "read_canonical_memory_item", lambda *args, **kwargs: None)
    service._canonical.write = MagicMock()
    service._canonical.delete_batch = MagicMock()
    monkeypatch.setattr(service, "_canonical_status", MagicMock(return_value=None))

    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.delete_batch("uid-test", ["valid", "locked"])

    assert exc_info.value.status_code == 402
    service._canonical.write.assert_not_called()
    service._canonical.delete_batch.assert_not_called()


def test_delete_batch_tombstones_historical_without_materializing_then_cleans(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    canonical_item = _memory(service_mod, "canonical")
    historical = _historical(service_mod, "legacy")
    monkeypatch.setattr(
        service_mod,
        "read_canonical_memory_item",
        lambda _uid, memory_id, **_kwargs: canonical_item if memory_id == "canonical" else None,
    )
    monkeypatch.setattr(service, "_canonical_status", MagicMock(return_value=None))
    events = []
    monkeypatch.setattr(service._history, "get", MagicMock(return_value=historical))
    monkeypatch.setattr(
        service, "_materialize_legacy", MagicMock(side_effect=AssertionError("privacy delete must not materialize"))
    )
    service._canonical.delete_batch = MagicMock(
        side_effect=lambda _uid, ids: events.append(("canonical_batch", list(ids)))
    )
    monkeypatch.setattr(
        service,
        "_write_historical_overrides",
        MagicMock(side_effect=lambda _uid, ids, status: events.append(("override", list(ids), status))),
    )
    monkeypatch.setattr(
        service_mod.HistoricalMemoryAdapter,
        "cleanup",
        MagicMock(side_effect=lambda _uid, memory_id, **_kwargs: events.append(("cleanup", memory_id))),
    )

    service.delete_batch("uid-test", ["canonical", "legacy", "legacy"])

    assert events == [
        ("canonical_batch", ["canonical"]),
        ("override", ["canonical", "legacy"], service_mod.MemoryItemStatus.tombstoned),
        ("cleanup", "legacy"),
    ]
