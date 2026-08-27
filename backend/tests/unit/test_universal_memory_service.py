"""Focused behavioral checks for the universal MemoryService seam."""

from unittest.mock import MagicMock

import pytest

from tests.unit.test_memory_service_parity import (
    _load_memory_service,
    _sample_memory_dict,
)


class _Snapshot:
    def __init__(self, payload=None, *, exists=True, reference=None):
        self._payload = payload
        self.exists = exists
        self.reference = reference

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


class _BatchStatusDb(_Db):
    def __init__(self, docs=None):
        super().__init__(docs)
        self.get_all_calls = []

    def get_all(self, refs):
        refs = list(refs)
        self.get_all_calls.append([ref.path for ref in refs])
        for ref in refs:
            payload = self.docs.get(ref.path)
            yield _Snapshot(payload, exists=payload is not None, reference=ref)


class _ReversedBatchStatusDb(_BatchStatusDb):
    def get_all(self, refs):
        refs = list(refs)
        self.get_all_calls.append([ref.path for ref in refs])
        for ref in reversed(refs):
            payload = self.docs.get(ref.path)
            yield _Snapshot(payload, exists=payload is not None, reference=ref)


def _memory(service_mod, memory_id, *, content=None):
    payload = _sample_memory_dict(memory_id)
    if content is not None:
        payload["content"] = content
    return service_mod.MemoryDB.model_validate(payload)


def _locked_memory(service_mod, memory_id="locked", *, content="LOCKED_SECRET_CONTENT"):
    return _memory(service_mod, memory_id, content=content).model_copy(update={"is_locked": True})


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
    service.history.read = MagicMock(return_value=[])
    service.history.get = MagicMock(return_value=_historical(service_mod, "memory-1"))
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


def test_memory_enabled_off_blocks_intake_like_mode_off(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    monkeypatch.setenv("MEMORY_ENABLED", "on")
    service.ensure_canonical_mutation_ready("uid-test")
    monkeypatch.setenv("MEMORY_ENABLED", "off")
    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.ensure_canonical_mutation_ready("uid-test")
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Memory writes are globally paused"


def test_prompt_cache_invalidation_also_invalidates_owner_rejection_feedback(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    clear_rejections = MagicMock()
    monkeypatch.setattr(service_mod, "clear_rejected_memory_feedback_cache", clear_rejections)

    service._invalidate_prompt_cache("uid-test")

    clear_rejections.assert_called_once_with("uid-test")


def test_historical_adapter_uses_injected_firestore_client(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service.read("uid-test", limit=3)

    # The production helper receives the injected client rather than falling
    # back to database.memories' global Firestore proxy.
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(service_mod.memories_db, "list_memory_updated_or_created_index", capture)
    service.read("uid-test", limit=3)
    assert calls[-1][1]["firestore_client"] is db


def test_mixed_read_deduplicates_canonical_public_identity(service_mod, monkeypatch):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    canonical = _memory(service_mod, "same", content="canonical")
    service._canonical.read = MagicMock(return_value=[canonical])
    service.history.read = MagicMock(
        return_value=[_historical(service_mod, "same", content="old"), _historical(service_mod, "legacy")]
    )

    result = service.read("uid-test", limit=10)
    assert {item.id for item in result} == {"same", "legacy"}
    assert next(item for item in result if item.id == "same").content == "canonical"


def test_mixed_read_does_not_hydrate_canonical_identity_from_historical_stub(service_mod, monkeypatch):
    """Index stubs share migrated ids. Hydrating the suppressed prefix would
    replace the canonical row with the grandfathered document, or drop it."""
    service = service_mod.MemoryService(db_client=_Db())
    canonical = _memory(service_mod, "same", content="canonical")
    service._canonical.read = MagicMock(return_value=[canonical])
    colliding_stub = service_mod.HistoricalMemoryRecord(
        memory=_memory(service_mod, "same", content=""),
        locator=service_mod.MemoryLocator("uid-test", "legacy", "same"),
        hydrated=False,
    )
    legacy_stub = service_mod.HistoricalMemoryRecord(
        memory=_memory(service_mod, "legacy", content=""),
        locator=service_mod.MemoryLocator("uid-test", "legacy", "legacy"),
        hydrated=False,
    )
    service.history.read = MagicMock(return_value=[colliding_stub, legacy_stub])

    def hydrate_page_stubs(_uid, records, *, budget=None):
        del budget
        assert [record.memory.id for record in records] == ["legacy"]
        return [_historical(service_mod, "legacy", content="legacy-full")]

    monkeypatch.setattr(service.history, "hydrate_records", hydrate_page_stubs)

    result = service.read("uid-test", limit=10)
    assert {item.id for item in result} == {"same", "legacy"}
    assert next(item for item in result if item.id == "same").content == "canonical"
    assert next(item for item in result if item.id == "legacy").content == "legacy-full"


def test_canonical_read_preserves_lock_and_returns_only_a_preview(service_mod, monkeypatch):
    backend = service_mod.CanonicalMemoryBackend(db_client=_Db())
    secret = "LOCKED_SECRET_CONTENT_" * 10
    monkeypatch.setattr(
        service_mod,
        "read_canonical_memories",
        lambda *args, **kwargs: [_locked_memory(service_mod, content=secret)],
    )

    result = backend.read("uid-test")

    assert len(result) == 1
    assert result[0].is_locked is True
    assert result[0].content != secret
    assert len(result[0].content) < len(secret)
    assert result[0].content.endswith("...")


def test_canonical_search_excludes_locked_rows(service_mod, monkeypatch):
    backend = service_mod.CanonicalMemoryBackend(db_client=_Db())
    monkeypatch.setattr(
        service_mod,
        "search_canonical_memories",
        lambda *args, **kwargs: [
            {
                "memory_id": "locked",
                "content": "LOCKED_SEARCH_SECRET",
                "tier": "short_term",
                "is_locked": True,
            },
            {
                "memory_id": "visible",
                "content": "VISIBLE_SEARCH_CONTENT",
                "tier": "short_term",
                "is_locked": False,
            },
        ],
    )

    result = backend.search("uid-test", "search")

    assert [match.memory.id for match in result] == ["visible"]
    assert all("LOCKED_SEARCH_SECRET" not in match.memory.content for match in result)


def test_fetch_rejects_a_locked_canonical_memory(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    monkeypatch.setattr(service_mod, "read_canonical_memory_item", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        service_mod,
        "memory_item_to_memorydb",
        lambda _item: _locked_memory(service_mod),
    )

    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.fetch("uid-test", "locked")

    assert exc_info.value.status_code == 402


@pytest.mark.parametrize("operation", ["update", "delete", "delete_batch", "external_delete"])
def test_locked_canonical_memory_rejects_every_mutation(service_mod, monkeypatch, operation):
    service = service_mod.MemoryService(db_client=_Db())
    canonical_item = object()
    monkeypatch.setattr(service_mod, "read_canonical_memory_item", lambda *args, **kwargs: canonical_item)
    monkeypatch.setattr(
        service_mod,
        "memory_item_to_memorydb",
        lambda _item: _locked_memory(service_mod),
    )
    service._canonical.update_content = MagicMock()
    service._canonical.delete = MagicMock()
    service._canonical.delete_batch = MagicMock()
    service._write_historical_override = MagicMock()
    service._write_historical_overrides = MagicMock()

    with pytest.raises(service_mod.HTTPException) as exc_info:
        if operation == "update":
            service.update_content("uid-test", "locked", "changed")
        elif operation == "delete":
            service.delete("uid-test", "locked")
        elif operation == "delete_batch":
            service.delete_batch("uid-test", ["locked"])
        else:
            service.delete_external_memory(
                "uid-test",
                "locked",
                memory_system=service_mod.MemorySystem.CANONICAL,
                consumer="developer_api",
                operation="delete",
                delete_vector=False,
            )

    assert exc_info.value.status_code == 402
    service._canonical.update_content.assert_not_called()
    service._canonical.delete.assert_not_called()
    service._canonical.delete_batch.assert_not_called()
    service._write_historical_override.assert_not_called()
    service._write_historical_overrides.assert_not_called()


def test_mixed_read_batches_canonical_suppression_status_lookups(service_mod, monkeypatch):
    db = _BatchStatusDb()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(
        return_value=[_historical(service_mod, "legacy-a"), _historical(service_mod, "legacy-b")]
    )

    result = service.read("uid-test", limit=10)

    assert {item.id for item in result} == {"legacy-a", "legacy-b"}
    assert len(db.get_all_calls) == 1
    assert db.get_all_calls[0] == [
        "users/uid-test/memory_items/legacy-a",
        "users/uid-test/memory_items/legacy-b",
        "users/uid-test/memory_historical_overrides/legacy-a",
        "users/uid-test/memory_historical_overrides/legacy-b",
    ]


def test_mixed_read_maps_unordered_batch_snapshots_by_reference_path(service_mod):
    db = _ReversedBatchStatusDb({'users/uid-test/memory_items/legacy-a': {'status': 'tombstoned'}})
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(
        return_value=[_historical(service_mod, 'legacy-a'), _historical(service_mod, 'legacy-b')]
    )

    result = service.read('uid-test', limit=10)

    assert [memory.id for memory in result] == ['legacy-b']


def test_mixed_read_fails_closed_for_malformed_present_canonical_identity(service_mod):
    db = _BatchStatusDb({'users/uid-test/memory_items/legacy-a': {'status': 'unknown'}})
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(return_value=[_historical(service_mod, 'legacy-a')])

    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.read('uid-test', limit=10)

    assert exc_info.value.status_code == 503


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
    service.read.assert_called_once_with(
        "uid-test",
        limit=service_mod.HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW,
        offset=0,
        include_pending_processing=False,
        now=None,
    )
    service._canonical.write.assert_not_called()


def test_offset_merge_fetches_a_complete_bounded_prefix(service_mod):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    canonical = [_memory(service_mod, f"canonical-{index:04d}") for index in range(260)]
    historical = [_historical(service_mod, f"legacy-{index:04d}") for index in range(260)]
    service._canonical.read = MagicMock(return_value=canonical)
    service.history.read = MagicMock(return_value=historical)
    service._canonical_status = MagicMock(return_value=None)

    page = service.read("uid-test", limit=10, offset=500)

    assert len(page) == 10
    assert service._canonical.read.call_args.kwargs["limit"] == 510
    assert service.history.read.call_args.kwargs == {
        "limit": 510,
        "offset": 0,
        "device_scope_request": None,
        "hydrate": False,
        "budget": None,
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
    service.history.read = MagicMock(return_value=[_historical(service_mod, memory_id)])

    assert service.read(uid, limit=10) == []


def test_adaptive_merge_scan_surfaces_visible_rows_behind_suppressed_prefix(service_mod, monkeypatch):
    from datetime import datetime, timezone

    from database.memory_collections import MemoryCollections

    uid = "uid-test"
    service = service_mod.MemoryService(db_client=_Db())
    older_canonical = _memory(service_mod, "canonical-old").model_copy(
        update={"updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    )
    suppressed = []
    for index in range(5):
        memory_id = f"suppressed-{index}"
        path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
        service.db_client.docs[path] = {"status": "tombstoned"}
        suppressed.append(
            service_mod.HistoricalMemoryRecord(
                memory=_memory(service_mod, memory_id).model_copy(
                    update={"updated_at": datetime(2026, 1, 20 - index, tzinfo=timezone.utc)}
                ),
                locator=service_mod.MemoryLocator(uid, "legacy", memory_id),
            )
        )
    visible = [
        service_mod.HistoricalMemoryRecord(
            memory=_memory(service_mod, "visible-new").model_copy(
                update={"updated_at": datetime(2026, 1, 10, tzinfo=timezone.utc)}
            ),
            locator=service_mod.MemoryLocator(uid, "legacy", "visible-new"),
        )
    ]
    all_historical = suppressed + visible
    read_limits: list[int] = []

    def fake_history_read(_uid, *, limit, offset, device_scope_request=None, **_kwargs):
        del _uid, offset, device_scope_request
        read_limits.append(limit)
        return all_historical[:limit]

    service._canonical.read = MagicMock(return_value=[older_canonical])
    service.history.read = MagicMock(side_effect=fake_history_read)

    origin = MagicMock()
    suppression = MagicMock()
    monkeypatch.setattr(service_mod.MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL, "labels", origin)
    monkeypatch.setattr(service_mod.MEMORY_HISTORICAL_SUPPRESSION_TOTAL, "labels", suppression)
    origin_inc = MagicMock()
    suppression_inc = MagicMock()
    origin.return_value.inc = origin_inc
    suppression.return_value.inc = suppression_inc

    page = service.read(uid, limit=1)

    assert [memory.id for memory in page] == ["visible-new"]
    assert read_limits[0] == 1
    assert max(read_limits) > 1
    assert [call.kwargs["origin"] for call in origin.call_args_list] == ["canonical", "historical"]
    assert [call.args[0] for call in origin_inc.call_args_list] == [1, 1]
    assert [call.kwargs["reason"] for call in suppression.call_args_list] == ["canonical_state"]
    assert suppression_inc.call_args.args[0] == 5


def test_adaptive_merge_scan_does_not_double_count_suppression_across_retries(service_mod, monkeypatch):
    from datetime import datetime, timezone

    from database.memory_collections import MemoryCollections

    uid = "uid-test"
    service = service_mod.MemoryService(db_client=_Db())
    suppressed = []
    for index in range(3):
        memory_id = f"tomb-{index}"
        path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
        service.db_client.docs[path] = {"status": "tombstoned"}
        suppressed.append(
            service_mod.HistoricalMemoryRecord(
                memory=_memory(service_mod, memory_id).model_copy(
                    update={"updated_at": datetime(2026, 2, 10 - index, tzinfo=timezone.utc)}
                ),
                locator=service_mod.MemoryLocator(uid, "legacy", memory_id),
            )
        )
    visible = service_mod.HistoricalMemoryRecord(
        memory=_memory(service_mod, "kept").model_copy(
            update={"updated_at": datetime(2026, 2, 1, tzinfo=timezone.utc)}
        ),
        locator=service_mod.MemoryLocator(uid, "legacy", "kept"),
    )
    rows = suppressed + [visible]

    def fake_history_read(_uid, *, limit, offset, device_scope_request=None, **_kwargs):
        del _uid, offset, device_scope_request
        return rows[:limit]

    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(side_effect=fake_history_read)
    suppression = MagicMock()
    monkeypatch.setattr(service_mod.MEMORY_HISTORICAL_SUPPRESSION_TOTAL, "labels", suppression)
    suppression_inc = MagicMock()
    suppression.return_value.inc = suppression_inc

    page = service.read(uid, limit=1)

    assert [memory.id for memory in page] == ["kept"]
    assert service.history.read.call_count >= 2
    assert suppression.call_count == 1
    assert suppression_inc.call_args.args[0] == 3


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
        is_read=None,
        is_dismissed=None,
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
    monkeypatch.setattr(
        service_mod,
        "iter_authoritative_product_memory_items",
        lambda **_kwargs: iter(()),
    )
    rows = [_historical(service_mod, f"legacy-{index}") for index in range(10_001)]
    service.history.iter_all_live = MagicMock(return_value=iter(rows))

    exported = service.export_memories("uid-test")

    assert len(exported) == 10_001
    service.history.iter_all_live.assert_called_once_with("uid-test", page_size=500)


def test_export_includes_active_restricted_user_owned_canonical_memory(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    item = MagicMock(
        memory_id="restricted-1",
        status=service_mod.MemoryItemStatus.active,
        tier=service_mod.MemoryTier.long_term,
        sensitivity_labels=["restricted"],
    )
    expected = _memory(service_mod, "restricted-1")
    monkeypatch.setattr(
        service_mod,
        "iter_authoritative_product_memory_items",
        lambda **_kwargs: iter((item,)),
    )
    monkeypatch.setattr(service_mod, "memory_item_to_memorydb", lambda _item: expected)
    service.history.iter_all_live = MagicMock(return_value=iter([]))

    assert service.export_memories("uid-test") == [expected]


def test_export_preserves_full_locked_historical_content(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    raw = _sample_memory_dict("locked-export")
    raw["is_locked"] = True
    raw["content"] = "locked content " * 20

    record = service_mod.HistoricalMemoryRecord(
        memory=service_mod.HistoricalMemoryAdapter._historical_memory(raw, include_locked_content=True),
        locator=service_mod.MemoryLocator("uid-test", "legacy", "locked-export"),
    )
    service.history.iter_all_live = MagicMock(return_value=iter([record]))
    monkeypatch.setattr(
        service_mod,
        "iter_authoritative_product_memory_items",
        lambda **_kwargs: iter(()),
    )

    exported = service.export_memories("uid-test")

    assert len(exported) == 1
    assert exported[0].content == raw["content"]


def test_export_honors_historical_tombstone_override(service_mod, monkeypatch):
    from database.memory_collections import MemoryCollections

    memory_id = "legacy-tombstoned-export"
    path = f"{MemoryCollections(uid='uid-test').memory_historical_overrides}/{memory_id}"
    service = service_mod.MemoryService(db_client=_Db({path: {"status": "tombstoned"}}))
    service.history.iter_all_live = MagicMock(return_value=iter([_historical(service_mod, memory_id)]))
    monkeypatch.setattr(
        service_mod,
        "iter_authoritative_product_memory_items",
        lambda **_kwargs: iter(()),
    )

    assert service.export_memories("uid-test") == []


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
    service.history.ids = MagicMock(return_value=["legacy-1", "legacy-2"])
    cleanup = MagicMock(side_effect=lambda uid, **kwargs: db.events.append(("cleanup", uid)))
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup_all", cleanup)

    service.delete_all("uid-test")
    assert db.events[0][0] in {"set", "batch_commit"}
    assert any(event == ("canonical_delete", "uid-test") for event in db.events)
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
    service.history.search = MagicMock(
        return_value=[
            service_mod.MemorySearchMatch(_memory(service_mod, "same", content="old"), 0.8),
            service_mod.MemorySearchMatch(_memory(service_mod, "legacy"), 0.7),
        ]
    )

    result = service.search("uid-test", "query", limit=10)
    assert [match.memory.id for match in result] == ["same", "legacy"]
    assert result[0].memory.content == "canonical"


def test_canonical_search_preserves_order_as_relevance_when_provider_omits_score(service_mod, monkeypatch):
    rows = [
        {"memory_id": "first", "content": "first", "tier": "long_term", "date": "2025-01-01T00:00:00+00:00"},
        {"memory_id": "second", "content": "second", "tier": "long_term", "date": "2025-01-01T00:00:00+00:00"},
    ]
    monkeypatch.setattr(service_mod, "search_canonical_memories", lambda *args, **kwargs: rows)

    results = service_mod.CanonicalMemoryBackend(db_client=_Db()).search("uid-test", "query", limit=2)

    assert [match.memory.id for match in results] == ["first", "second"]
    assert results[0].score > results[1].score


def test_historical_missing_updated_at_uses_created_at_for_sort_and_validation(service_mod):
    raw = _sample_memory_dict("missing-updated")
    expected = raw["created_at"]
    raw.pop("updated_at")

    record = service_mod.HistoricalMemoryAdapter._adapt("uid-test", raw)

    assert record is not None
    assert record.memory.updated_at == expected


def test_historical_missing_uid_falls_back_to_the_owning_path(service_mod):
    raw = _sample_memory_dict("missing-uid")
    raw.pop("uid")

    record = service_mod.HistoricalMemoryAdapter._adapt("uid-test", raw)

    assert record is not None
    assert record.memory.uid == "uid-test"


def test_historical_stored_uid_wins_over_the_path_fallback(service_mod):
    raw = _sample_memory_dict("stored-uid")
    raw["uid"] = "uid-stored"

    record = service_mod.HistoricalMemoryAdapter._adapt("uid-test", raw)

    assert record is not None
    assert record.memory.uid == "uid-stored"


def test_device_scope_keeps_device_neutral_historical_rows(service_mod):
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(return_value=[_historical(service_mod, "neutral")])
    request = service_mod.DeviceScopeRequest(device_scope="current", client_device_id="macos_abcd1234")

    assert [item.id for item in service.read("uid-test", device_scope_request=request)] == ["neutral"]


def test_index_stub_respects_visibility_and_capture_device(service_mod):
    adapter = service_mod.HistoricalMemoryAdapter()
    created = "2026-01-01T00:00:00+00:00"
    unknown = adapter._stub_from_index(
        "uid-test",
        {"id": "bad-vis", "created_at": created, "visibility": "secret"},
    )
    assert unknown is None

    private = adapter._stub_from_index(
        "uid-test",
        {"id": "priv", "created_at": created, "visibility": "private"},
    )
    assert private is not None
    assert private.memory.visibility == "private"

    scoped = service_mod.DeviceScopeRequest(device_scope="current", client_device_id="device-a")
    other_device = adapter._stub_from_index(
        "uid-test",
        {
            "id": "other",
            "created_at": created,
            "capture_device_ids": ["device-b"],
        },
    )
    assert other_device is not None
    assert adapter.matches_device(other_device, scoped) is False

    matching = adapter._stub_from_index(
        "uid-test",
        {
            "id": "mine",
            "created_at": created,
            "capture_device_ids": ["device-a"],
        },
    )
    assert matching is not None
    assert adapter.matches_device(matching, scoped) is True


def test_fetch_applies_device_scope_to_canonical_items(service_mod, monkeypatch):
    item = MagicMock(primary_capture_device="device-a", capture_device_ids=[], evidence=[])
    expected = _memory(service_mod, "canonical-device")
    monkeypatch.setattr(service_mod, "read_canonical_memory_item", lambda *args, **kwargs: item)
    monkeypatch.setattr(service_mod, "memory_item_to_memorydb", lambda _item: expected)
    service = service_mod.MemoryService(db_client=_Db())

    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.fetch(
            "uid-test",
            "canonical-device",
            device_scope_request=service_mod.DeviceScopeRequest(device_scope="current", client_device_id="device-b"),
        )

    assert exc_info.value.status_code == 404


def test_delete_batch_validates_every_id_before_any_write(service_mod, monkeypatch):
    """A later missing/locked id cannot leave an earlier valid id deleted."""
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    valid = _historical(service_mod, "valid")
    locked = _historical(service_mod, "locked")
    locked = locked.memory.model_copy(update={"is_locked": True})
    monkeypatch.setattr(
        service.history,
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
    monkeypatch.setattr(service_mod, "memory_item_to_memorydb", lambda item: item)
    historical = _historical(service_mod, "legacy")
    monkeypatch.setattr(
        service_mod,
        "read_canonical_memory_item",
        lambda _uid, memory_id, **_kwargs: canonical_item if memory_id == "canonical" else None,
    )
    monkeypatch.setattr(service, "_canonical_status", MagicMock(return_value=None))
    events = []
    monkeypatch.setattr(service.history, "get", MagicMock(return_value=historical))
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
        ("override", ["canonical", "legacy"], service_mod.MemoryItemStatus.tombstoned),
        ("canonical_batch", ["canonical"]),
        ("cleanup", "legacy"),
    ]


def test_delete_batch_retries_already_tombstoned_historical_identity(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=_Db())
    historical = _historical(service_mod, "legacy")
    monkeypatch.setattr(service_mod, "read_canonical_memory_item", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_canonical_status", MagicMock(return_value=service_mod.MemoryItemStatus.tombstoned))
    monkeypatch.setattr(service.history, "get", MagicMock(return_value=historical))
    overrides = MagicMock()
    cleanup = MagicMock()
    monkeypatch.setattr(service, "_write_historical_overrides", overrides)
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", cleanup)
    service._canonical.delete_batch = MagicMock()

    service.delete_batch("uid-test", ["legacy"])

    service._canonical.delete_batch.assert_not_called()
    overrides.assert_called_once_with("uid-test", ["legacy"], service_mod.MemoryItemStatus.tombstoned)
    cleanup.assert_called_once_with("uid-test", "legacy", db_client=service.db_client)


def test_retract_conversation_suppresses_and_cleans_historical_memories(service_mod, monkeypatch):
    historical = _historical(service_mod, "legacy", content="old conversation")
    historical = historical.memory.model_copy(update={"conversation_id": "conversation-1"})
    historical = service_mod.HistoricalMemoryRecord(
        memory=historical,
        locator=service_mod.MemoryLocator("uid-test", "legacy", "legacy"),
    )
    service = service_mod.MemoryService(db_client=_Db())
    monkeypatch.setattr(
        service_mod,
        "retract_conversation_sourced_memories",
        lambda *args, **kwargs: {"retracted_memory_ids": ["canonical"]},
    )
    service.history.all_live = MagicMock(return_value=[historical])
    overrides = MagicMock()
    cleanup = MagicMock()
    monkeypatch.setattr(service, "_write_historical_overrides", overrides)
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", cleanup)

    service.retract_conversation_memories("uid-test", "conversation-1")

    overrides.assert_called_once_with("uid-test", ["canonical", "legacy"], service_mod.MemoryItemStatus.tombstoned)
    cleanup.assert_called_once_with("uid-test", "legacy", db_client=service.db_client)


def test_retract_irreversible_callback_fires_immediately_after_canonical_commit(service_mod, monkeypatch):
    historical = _historical(service_mod, "legacy")
    historical = service_mod.HistoricalMemoryRecord(
        memory=historical.memory.model_copy(update={"conversation_id": "conversation-1"}),
        locator=historical.locator,
    )
    service = service_mod.MemoryService(db_client=_Db())
    events: list[str] = []

    def retract(*_args, **_kwargs):
        events.append("canonical")
        return {"retracted_memory_ids": ["canonical"]}

    def write_overrides(*_args, **_kwargs):
        events.append("suppress")

    def cleanup(*_args, **_kwargs):
        events.append("cleanup")

    monkeypatch.setattr(service_mod, "retract_conversation_sourced_memories", retract)
    service.history.all_live = MagicMock(return_value=[historical])
    monkeypatch.setattr(service, "_write_historical_overrides", write_overrides)
    monkeypatch.setattr(service_mod.HistoricalMemoryAdapter, "cleanup", cleanup)

    service.retract_conversation_memories(
        "uid-test",
        "conversation-1",
        on_authoritative_commit=lambda: events.append("callback"),
    )

    assert events == ["canonical", "callback", "suppress", "cleanup"]


def test_retract_irreversible_callback_still_fires_when_later_suppression_fails(service_mod, monkeypatch):
    historical = _historical(service_mod, "legacy")
    historical = service_mod.HistoricalMemoryRecord(
        memory=historical.memory.model_copy(update={"conversation_id": "conversation-1"}),
        locator=historical.locator,
    )
    service = service_mod.MemoryService(db_client=_Db())
    events: list[str] = []

    monkeypatch.setattr(
        service_mod,
        "retract_conversation_sourced_memories",
        lambda *_args, **_kwargs: {"retracted_memory_ids": ["canonical"]},
    )
    service.history.all_live = MagicMock(return_value=[historical])

    def write_overrides(*_args, **_kwargs):
        events.append("suppress_failed")
        raise service_mod.HTTPException(status_code=503, detail="Canonical memory suppression unavailable")

    monkeypatch.setattr(service, "_write_historical_overrides", write_overrides)
    monkeypatch.setattr(
        service_mod.HistoricalMemoryAdapter,
        "cleanup",
        MagicMock(side_effect=AssertionError("cleanup must not run")),
    )

    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.retract_conversation_memories(
            "uid-test",
            "conversation-1",
            on_authoritative_commit=lambda: events.append("callback"),
        )

    assert exc_info.value.status_code == 503
    assert events == ["callback", "suppress_failed"]
