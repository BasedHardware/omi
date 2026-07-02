from datetime import datetime, timezone
import json
import sys
import types

google_stub = sys.modules.setdefault("google", types.ModuleType("google"))
cloud_stub = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
firestore_stub = sys.modules.setdefault("google.cloud.firestore", types.ModuleType("google.cloud.firestore"))
firestore_stub.transactional = lambda func: func
google_stub.cloud = cloud_stub
cloud_stub.firestore = firestore_stub

from database.memory_vector_repair_pinecone_adapter import (
    VECTOR_REPAIR_PINECONE_NAMESPACE,
    VectorRepairNotReady,
    make_pinecone_vector_deleter,
    make_pinecone_vector_repairer,
)
from database.memory_vector_repair_outbox_worker import (
    VectorRepairOutboxWorkerTickConfig,
    ack_vector_repair_purge_outbox_record,
    lease_vector_repair_purge_outbox_records,
    process_vector_repair_purge_outbox_records,
    run_vector_repair_outbox_worker_tick,
)


def _record(**overrides):
    data = {
        "schema_version": 1,
        "record_id": "rec-1",
        "idempotency_key": "idem-1",
        "uid": "u1",
        "event_type": "vector_repair_purge",
        "status": "pending",
        "vector_id": "vec-1",
        "memory_id": "mem-1",
        "reason": "stale_item_revision",
        "required_projection_commit_id": "projection-2",
        "required_account_generation": 0,
        "attempt_count": 0,
    }
    data.update(overrides)
    return data


def _live_item(**overrides):
    captured_at = datetime(2026, 6, 19, 11, 0, tzinfo=timezone.utc)
    data = {
        "memory_id": "mem-1",
        "uid": "u1",
        "version": 1,
        "tier": "short_term",
        "status": "active",
        "processing_state": "processed",
        "source_state": "active",
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": captured_at,
        "updated_at": captured_at,
        "expires_at": datetime(2026, 6, 20, 11, 0, tzinfo=timezone.utc),
        "item_revision": 2,
        "source_commit_id": "source-2",
        "content_hash": "hash-2",
        "account_generation": 0,
        "content": "fresh memory content",
    }
    data.update(overrides)
    return data


class _Updates:
    def __init__(self):
        self.patches = []

    def __call__(self, record, patch):
        self.patches.append((record["record_id"], dict(patch)))


class _FakeSnapshot:
    def __init__(self, path, data):
        self.reference = _FakeDocumentReference(path, None)
        self.id = path.rsplit("/", 1)[-1]
        self.exists = data is not None
        self._data = dict(data) if data is not None else None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocumentReference:
    def __init__(self, path, store):
        self.path = path
        self._store = store

    def get(self, transaction=None):
        if transaction is not None and hasattr(transaction, "read_paths"):
            transaction.read_paths.append(self.path)
        return _FakeSnapshot(self.path, self._store.get(self.path))

    def update(self, patch):
        self._store[self.path].update(dict(patch))

    def set(self, data):
        self._store[self.path] = dict(data)


class _FakeQuery:
    def __init__(self, store, collection_path, filters=None, limit_count=None):
        self._store = store
        self._collection_path = collection_path
        self._filters = filters or []
        self._limit_count = limit_count

    def where(self, *args, **kwargs):
        field, op, value = args
        return _FakeQuery(self._store, self._collection_path, self._filters + [(field, op, value)], self._limit_count)

    def limit(self, limit_count):
        return _FakeQuery(self._store, self._collection_path, self._filters, limit_count)

    def stream(self):
        matches = []
        prefix = f"{self._collection_path}/"
        for path, data in sorted(self._store.items()):
            if not path.startswith(prefix):
                continue
            if all(self._matches(data, field, op, value) for field, op, value in self._filters):
                matches.append(_FakeSnapshot(path, data))
        return matches[: self._limit_count]

    @staticmethod
    def _matches(data, field, op, value):
        if op == "==":
            return data.get(field) == value
        if op == "<=":
            field_value = data.get(field)
            return field_value is not None and field_value <= value
        raise AssertionError(f"unexpected op {op}")


class _FakeFirestore:
    def __init__(self, docs=None):
        self.store = dict(docs or {})

    def collection(self, path):
        return _FakeQuery(self.store, path)

    def document(self, path):
        return _FakeDocumentReference(path, self.store)


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.read_paths = []
        self.update_paths = []

    def get(self, doc_ref):
        self.read_paths.append(doc_ref.path)
        return doc_ref.get(transaction=self)

    def update(self, doc_ref, patch):
        self.update_paths.append(doc_ref.path)
        doc_ref.update(patch)


class _FakeTransactionalFirestore(_FakeFirestore):
    def __init__(self, docs=None):
        super().__init__(docs)
        self.transactions = []

    def transaction(self):
        transaction = _FakeTransaction(self)
        self.transactions.append(transaction)
        return transaction


class TestWorkerCore:
    def test_worker_tick_disabled_config_does_not_lease_or_call_side_effects(self):
        calls = []
        db = _FakeFirestore(
            {
                "users/u1/memory_outbox/available": _record(
                    record_id="available",
                    outbox_path="users/u1/memory_outbox/available",
                    available_at=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc).isoformat(),
                )
            }
        )

        result = run_vector_repair_outbox_worker_tick(
            db_client=db,
            uid="u1",
            config=VectorRepairOutboxWorkerTickConfig(enabled=False, worker_id="worker-disabled"),
            authoritative_item_loader=lambda record: calls.append("loader"),
            vector_deleter=lambda record: calls.append("delete"),
            vector_repairer=lambda record, item: calls.append("repair"),
            now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
        )

        assert result == {
            "enabled": False,
            "worker_id": "worker-disabled",
            "uid": "u1",
            "leased_count": 0,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "ack_failed_count": 0,
            "actions": [],
            "errors": [],
        }
        assert db.store["users/u1/memory_outbox/available"]["status"] == "pending"
        assert calls == []

    def test_worker_tick_enabled_leases_processes_and_acks_delete_or_repair(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        db = _FakeFirestore(
            {
                "users/u1/memory_outbox/delete": _record(
                    record_id="delete",
                    idempotency_key="delete-key",
                    outbox_path="users/u1/memory_outbox/delete",
                    reason="missing_authoritative_item",
                    vector_id="vec-delete",
                    available_at=now.isoformat(),
                ),
                "users/u1/memory_outbox/repair": _record(
                    record_id="repair",
                    idempotency_key="repair-key",
                    outbox_path="users/u1/memory_outbox/repair",
                    reason="stale_item_revision",
                    vector_id="vec-repair",
                    available_at=now.isoformat(),
                ),
            }
        )
        deleted = []
        repaired = []

        result = run_vector_repair_outbox_worker_tick(
            db_client=db,
            uid="u1",
            config=VectorRepairOutboxWorkerTickConfig(enabled=True, worker_id="worker-a", limit=10),
            authoritative_item_loader=lambda record: _live_item(memory_id=record["memory_id"]),
            vector_deleter=lambda record: deleted.append(record["vector_id"]),
            vector_repairer=lambda record, item: repaired.append((record["vector_id"], item["memory_id"])),
            now=now,
        )

        assert result["enabled"] is True
        assert result["worker_id"] == "worker-a"
        assert result["uid"] == "u1"
        assert result["leased_count"] == 2
        assert result["processed_count"] == 2
        assert result["failed_count"] == 0
        assert result["ack_failed_count"] == 0
        assert result["actions"] == [
            {"record_id": "delete", "idempotency_key": "delete-key", "action": "delete"},
            {"record_id": "repair", "idempotency_key": "repair-key", "action": "repair"},
        ]
        assert deleted == ["vec-delete"]
        assert repaired == [("vec-repair", "mem-1")]
        assert db.store["users/u1/memory_outbox/delete"]["status"] == "completed"
        assert db.store["users/u1/memory_outbox/delete"]["action"] == "delete"
        assert db.store["users/u1/memory_outbox/repair"]["status"] == "completed"
        assert db.store["users/u1/memory_outbox/repair"]["action"] == "repair"

    def test_worker_tick_lease_failure_returns_deterministic_error_before_actions(self):
        class _FailingLeaseFirestore(_FakeFirestore):
            def collection(self, path):
                raise RuntimeError(f"lease failed for {path}")

        calls = []

        result = run_vector_repair_outbox_worker_tick(
            db_client=_FailingLeaseFirestore(),
            uid="u1",
            config=VectorRepairOutboxWorkerTickConfig(enabled=True, worker_id="worker-a"),
            authoritative_item_loader=lambda record: calls.append("loader"),
            vector_deleter=lambda record: calls.append("delete"),
            vector_repairer=lambda record, item: calls.append("repair"),
        )

        assert result["leased_count"] == 0
        assert result["processed_count"] == 0
        assert result["failed_count"] == 0
        assert result["ack_failed_count"] == 0
        assert result["errors"] == [{"stage": "lease", "error": "lease failed for users/u1/memory_outbox"}]
        assert calls == []

    def test_worker_tick_ack_failure_is_counted_after_single_adapter_side_effect(self):
        class _FailingAckDocumentReference(_FakeDocumentReference):
            def update(self, patch):
                if self.path.endswith("/dup-a") and patch.get("status") != "in_progress":
                    raise RuntimeError(f"ack failed for {self.path}")
                super().update(patch)

        class _FailingAckFirestore(_FakeFirestore):
            def document(self, path):
                if path.endswith("/dup-a"):
                    return _FailingAckDocumentReference(path, self.store)
                return super().document(path)

        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        db = _FailingAckFirestore(
            {
                "users/u1/memory_outbox/dup-a": _record(
                    record_id="dup-a",
                    idempotency_key="dup-key",
                    outbox_path="users/u1/memory_outbox/dup-a",
                    available_at=now.isoformat(),
                ),
                "users/u1/memory_outbox/dup-b": _record(
                    record_id="dup-b",
                    idempotency_key="dup-key",
                    outbox_path="users/u1/memory_outbox/dup-b",
                    available_at=now.isoformat(),
                ),
            }
        )
        repaired = []

        result = run_vector_repair_outbox_worker_tick(
            db_client=db,
            uid="u1",
            config=VectorRepairOutboxWorkerTickConfig(enabled=True, worker_id="worker-a", limit=10),
            authoritative_item_loader=lambda record: _live_item(),
            vector_deleter=lambda record: None,
            vector_repairer=lambda record, item: repaired.append(record["record_id"]),
            now=now,
        )

        assert repaired == ["dup-a"]
        assert result["leased_count"] == 2
        assert result["processed_count"] == 0
        assert result["skipped_count"] == 1
        assert result["failed_count"] == 1
        assert result["ack_failed_count"] == 2
        assert result["errors"] == [
            {"stage": "ack", "record_id": "dup-a", "error": "ack failed for users/u1/memory_outbox/dup-a"},
            {"stage": "ack", "record_id": "dup-a", "error": "ack failed for users/u1/memory_outbox/dup-a"},
        ]

    def test_firestore_reader_leases_only_available_pending_vector_repair_records_and_ack_updates_path(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        available = now.isoformat()
        future = datetime(2026, 6, 19, 12, 5, tzinfo=timezone.utc).isoformat()
        db = _FakeFirestore(
            {
                "users/u1/memory_outbox/available": _record(
                    record_id="available", outbox_path="users/u1/memory_outbox/available", available_at=available
                ),
                "users/u1/memory_outbox/completed": _record(
                    record_id="completed", status="completed", available_at=available
                ),
                "users/u1/memory_outbox/in-progress": _record(
                    record_id="in-progress", status="in_progress", available_at=available
                ),
                "users/u1/memory_outbox/future": _record(record_id="future", available_at=future),
                "users/u1/memory_outbox/other-event": _record(
                    record_id="other-event", event_type="other", available_at=available
                ),
            }
        )

        leased = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-a",
            limit=10,
            lease_seconds=30,
            now=now,
        )

        assert [record["record_id"] for record in leased] == ["available"]
        assert leased[0]["status"] == "pending"
        assert db.store["users/u1/memory_outbox/available"]["status"] == "in_progress"
        assert db.store["users/u1/memory_outbox/available"]["lease_owner"] == "worker-a"

        ack_vector_repair_purge_outbox_record(
            db_client=db,
            record=leased[0],
            patch={"status": "completed", "action": "repair"},
            now=now,
        )

        assert db.store["users/u1/memory_outbox/available"]["status"] == "completed"
        assert db.store["users/u1/memory_outbox/available"]["action"] == "repair"
        assert db.store["users/u1/memory_outbox/available"]["updated_at"] == now.isoformat()

    def test_firestore_reader_reclaims_expired_in_progress_lease_after_expiry_only(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        before_expiry = datetime(2026, 6, 19, 11, 59, tzinfo=timezone.utc)
        after_expiry = datetime(2026, 6, 19, 12, 1, tzinfo=timezone.utc)
        path = "users/u1/memory_outbox/expired-lease"
        db = _FakeFirestore(
            {
                path: _record(
                    record_id="expired-lease",
                    outbox_path=path,
                    status="in_progress",
                    available_at=before_expiry.isoformat(),
                    lease_owner="old-worker",
                    lease_expires_at=now.isoformat(),
                )
            }
        )

        not_yet = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-a",
            limit=10,
            lease_seconds=30,
            now=before_expiry,
        )
        reclaimed = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-b",
            limit=10,
            lease_seconds=30,
            now=after_expiry,
        )

        assert not_yet == []
        assert [record["record_id"] for record in reclaimed] == ["expired-lease"]
        assert reclaimed[0]["status"] == "pending"
        assert db.store[path]["status"] == "in_progress"
        assert db.store[path]["lease_owner"] == "worker-b"
        assert db.store[path]["leased_at"] == after_expiry.isoformat()

    def test_firestore_reader_never_reclaims_completed_or_dead_letter_records(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        expired = datetime(2026, 6, 19, 11, 0, tzinfo=timezone.utc).isoformat()
        db = _FakeFirestore(
            {
                "users/u1/memory_outbox/completed": _record(
                    record_id="completed",
                    status="completed",
                    available_at=expired,
                    lease_expires_at=expired,
                ),
                "users/u1/memory_outbox/dead": _record(
                    record_id="dead",
                    status="dead_letter",
                    available_at=expired,
                    lease_expires_at=expired,
                ),
            }
        )

        leased = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-a",
            limit=10,
            lease_seconds=30,
            now=now,
        )

        assert leased == []
        assert db.store["users/u1/memory_outbox/completed"]["status"] == "completed"
        assert db.store["users/u1/memory_outbox/dead"]["status"] == "dead_letter"

    def test_firestore_reader_claim_uses_transaction_when_client_supports_it(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        path = "users/u1/memory_outbox/transactional"
        db = _FakeTransactionalFirestore(
            {path: _record(record_id="transactional", outbox_path=path, available_at=now.isoformat())}
        )

        leased = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-txn",
            limit=1,
            lease_seconds=30,
            now=now,
        )

        assert [record["record_id"] for record in leased] == ["transactional"]
        assert len(db.transactions) == 1
        assert db.transactions[0].read_paths == [path]
        assert db.transactions[0].update_paths == [path]
        assert db.store[path]["status"] == "in_progress"
        assert db.store[path]["lease_owner"] == "worker-txn"

    def test_duplicate_lease_after_claim_does_not_duplicate_worker_action(self):
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        path = "users/u1/memory_outbox/dup"
        db = _FakeFirestore({path: _record(record_id="dup", outbox_path=path, available_at=now.isoformat())})
        deleted = []

        first_lease = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-a",
            limit=10,
            lease_seconds=30,
            now=now,
        )
        second_lease = lease_vector_repair_purge_outbox_records(
            db_client=db,
            uid="u1",
            worker_id="worker-b",
            limit=10,
            lease_seconds=30,
            now=now,
        )

        result = process_vector_repair_purge_outbox_records(
            first_lease + second_lease,
            authoritative_item_loader=lambda record: None,
            vector_deleter=lambda record: deleted.append(record["vector_id"]),
            vector_repairer=lambda record, item: None,
            outbox_updater=lambda record, patch: None,
        )

        assert [record["record_id"] for record in first_lease] == ["dup"]
        assert second_lease == []
        assert deleted == ["vec-1"]
        assert result["processed_count"] == 1

    def test_ack_writer_failure_propagates_deterministically(self):
        class _FailingFirestore(_FakeFirestore):
            def document(self, path):
                raise RuntimeError(f"write failed for {path}")

        try:
            ack_vector_repair_purge_outbox_record(
                db_client=_FailingFirestore(),
                record=_record(record_id="bad", outbox_path="users/u1/memory_outbox/bad"),
                patch={"status": "dead_letter"},
            )
        except RuntimeError as exc:
            assert "users/u1/memory_outbox/bad" in str(exc)
        else:
            raise AssertionError("expected ack writer failure to propagate")

    def test_worker_deletes_stale_vector_when_authoritative_item_is_missing(self):
        deleted = []
        repaired = []
        updates = _Updates()

        result = process_vector_repair_purge_outbox_records(
            [_record(reason="missing_authoritative_item")],
            authoritative_item_loader=lambda record: None,
            vector_deleter=lambda record: deleted.append(record["vector_id"]),
            vector_repairer=lambda record, item: repaired.append((record["vector_id"], item)),
            outbox_updater=updates,
        )

        assert deleted == ["vec-1"]
        assert repaired == []
        assert result["processed_count"] == 1
        assert result["actions"] == [{"record_id": "rec-1", "idempotency_key": "idem-1", "action": "delete"}]
        assert updates.patches[-1][1]["status"] == "completed"
        assert updates.patches[-1][1]["action"] == "delete"

    def test_worker_repairs_stale_live_authoritative_item(self):
        deleted = []
        repaired = []
        updates = _Updates()

        result = process_vector_repair_purge_outbox_records(
            [_record(reason="stale_item_revision")],
            authoritative_item_loader=lambda record: _live_item(),
            vector_deleter=lambda record: deleted.append(record["vector_id"]),
            vector_repairer=lambda record, item: repaired.append((record["vector_id"], item["item_revision"])),
            outbox_updater=updates,
        )

        assert deleted == []
        assert repaired == [("vec-1", 2)]
        assert result["actions"] == [{"record_id": "rec-1", "idempotency_key": "idem-1", "action": "repair"}]
        assert updates.patches[-1][1]["status"] == "completed"
        assert updates.patches[-1][1]["action"] == "repair"

    def test_worker_tombstone_precedence_deletes_even_when_stale_record_could_repair(self):
        deleted = []
        repaired = []

        process_vector_repair_purge_outbox_records(
            [_record(reason="stale_projection_commit")],
            authoritative_item_loader=lambda record: _live_item(status="tombstoned"),
            vector_deleter=lambda record: deleted.append(record["vector_id"]),
            vector_repairer=lambda record, item: repaired.append(record["vector_id"]),
            outbox_updater=lambda record, patch: None,
        )

        assert deleted == ["vec-1"]
        assert repaired == []

    def test_worker_skips_terminal_in_progress_and_duplicate_pending_idempotency_keys(self):
        deleted = []
        updates = _Updates()
        records = [
            _record(record_id="completed", idempotency_key="completed-key", status="completed"),
            _record(record_id="dead", idempotency_key="dead-key", status="dead_letter"),
            _record(record_id="lease", idempotency_key="lease-key", status="in_progress"),
            _record(record_id="dup-a", idempotency_key="dup-key"),
            _record(record_id="dup-b", idempotency_key="dup-key"),
        ]

        result = process_vector_repair_purge_outbox_records(
            records,
            authoritative_item_loader=lambda record: None,
            vector_deleter=lambda record: deleted.append(record["record_id"]),
            vector_repairer=lambda record, item: None,
            outbox_updater=updates,
        )

        assert deleted == ["dup-a"]
        assert result["processed_count"] == 1
        assert result["skipped_count"] == 4
        assert [patch[0] for patch in updates.patches if patch[1]["status"] == "completed"] == ["dup-a"]

    def test_worker_records_retry_and_dead_letter_failure_deterministically(self):
        retry_updates = _Updates()
        dead_updates = _Updates()

        def failing_delete(record):
            raise RuntimeError("pinecone unavailable")

        retry_result = process_vector_repair_purge_outbox_records(
            [_record(record_id="retry", idempotency_key="retry-key", attempt_count=0)],
            authoritative_item_loader=lambda record: None,
            vector_deleter=failing_delete,
            vector_repairer=lambda record, item: None,
            outbox_updater=retry_updates,
            max_attempts=3,
        )
        dead_result = process_vector_repair_purge_outbox_records(
            [_record(record_id="dead", idempotency_key="dead-key", attempt_count=2)],
            authoritative_item_loader=lambda record: None,
            vector_deleter=failing_delete,
            vector_repairer=lambda record, item: None,
            outbox_updater=dead_updates,
            max_attempts=3,
        )

        assert retry_result["failed_count"] == 1
        assert retry_updates.patches[-1][1]["status"] == "pending"
        assert retry_updates.patches[-1][1]["attempt_count"] == 1
        assert retry_updates.patches[-1][1]["last_error"] == "pinecone unavailable"
        assert dead_result["failed_count"] == 1
        assert dead_updates.patches[-1][1]["status"] == "dead_letter"
        assert dead_updates.patches[-1][1]["attempt_count"] == 3
        assert dead_updates.patches[-1][1]["last_error"] == "pinecone unavailable"

    def test_pinecone_adapter_delete_passes_vector_id_and_ns2_namespace_to_injected_deleter(self):
        calls = []
        deleter = make_pinecone_vector_deleter(
            delete_vectors=lambda *, ids, namespace: calls.append({"ids": list(ids), "namespace": namespace})
            or {"ok": True}
        )

        result = deleter(_record(vector_id="memvec:stale"))

        assert VECTOR_REPAIR_PINECONE_NAMESPACE == "ns2"
        assert calls == [{"ids": ["memvec:stale"], "namespace": "ns2"}]
        assert result["action"] == "delete"
        assert result["vector_ids"] == ["memvec:stale"]
        assert result["namespace"] == "ns2"

    def test_pinecone_adapter_repair_upserts_authoritative_memory_vector_with_ns2_metadata_and_embedding(self):
        upserts = []
        repairer = make_pinecone_vector_repairer(
            embed_text=lambda content: [0.1, 0.2, 0.3],
            upsert_vectors=lambda *, vectors, namespace: upserts.append({"vectors": vectors, "namespace": namespace})
            or {"count": 1},
            now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
        )

        result = repairer(_record(required_projection_commit_id="projection-2"), _live_item())

        assert len(upserts) == 1
        assert upserts[0]["namespace"] == "ns2"
        vector = upserts[0]["vectors"][0]
        assert vector["id"].startswith("memvec:")
        assert vector["values"] == [0.1, 0.2, 0.3]
        assert vector["metadata"]["uid"] == "u1"
        assert vector["metadata"]["memory_id"] == "mem-1"
        assert vector["metadata"]["projection_commit_id"] == "projection-2"
        assert vector["metadata"]["account_generation"] == 0
        assert vector["metadata"]["item_revision"] == 2
        assert vector["metadata"]["source_commit_id"] == "source-2"
        assert vector["metadata"]["content_hash"] == "hash-2"
        assert vector["metadata"]["vector_updated_at"] == "2026-06-19T12:00:00+00:00"
        assert result["action"] == "repair"
        assert result["vector_id"] == vector["id"]
        assert result["namespace"] == "ns2"

    def test_pinecone_adapter_repair_not_ready_without_content_or_required_fences_and_has_no_side_effects(self):
        upserts = []
        repairer = make_pinecone_vector_repairer(
            embed_text=lambda content: [0.1],
            upsert_vectors=lambda *, vectors, namespace: upserts.append(vectors),
        )

        for record, item in [
            (_record(required_projection_commit_id=""), _live_item()),
            (_record(), _live_item(content="")),
            (_record(), _live_item(source_commit_id=None)),
            (_record(), _live_item(content_hash=None)),
        ]:
            try:
                repairer(record, item)
            except VectorRepairNotReady as exc:
                assert str(exc)
            else:
                raise AssertionError("expected repair not-ready failure")

        assert upserts == []

    def test_worker_failure_path_records_adapter_failure_and_duplicate_batch_has_one_pinecone_side_effect(self):
        calls = []
        updates = _Updates()

        def failing_delete(*, ids, namespace):
            calls.append((tuple(ids), namespace))
            raise RuntimeError("pinecone delete failed")

        deleter = make_pinecone_vector_deleter(delete_vectors=failing_delete)

        result = process_vector_repair_purge_outbox_records(
            [
                _record(record_id="dup-a", idempotency_key="dup-key", reason="missing_authoritative_item"),
                _record(record_id="dup-b", idempotency_key="dup-key", reason="missing_authoritative_item"),
            ],
            authoritative_item_loader=lambda record: None,
            vector_deleter=deleter,
            vector_repairer=lambda record, item: None,
            outbox_updater=updates,
            max_attempts=3,
        )

        assert calls == [(("vec-1",), "ns2")]
        assert result["failed_count"] == 1
        assert result["skipped_count"] == 1
        assert updates.patches[-1][0] == "dup-a"
        assert updates.patches[-1][1]["status"] == "pending"
        assert updates.patches[-1][1]["attempt_count"] == 1
        assert updates.patches[-1][1]["last_error"] == "pinecone delete failed"


from scripts import vector_repair_outbox_worker_entrypoint as entrypoint


class TestEntrypoint:
    class _Printer:
        def __init__(self):
            self.lines = []

        def __call__(self, line):
            self.lines.append(line)

        def payload(self):
            assert len(self.lines) == 1
            return json.loads(self.lines[0])

    def test_entrypoint_absent_enabled_env_fails_closed_without_tick_or_side_effects(self):
        calls = []
        printer = TestEntrypoint._Printer()

        exit_code = entrypoint.run_vector_repair_outbox_worker_entrypoint(
            env={},
            db_client=object(),
            authoritative_item_loader=lambda record: calls.append("load"),
            vector_deleter=lambda record: calls.append("delete"),
            vector_repairer=lambda record, item: calls.append("repair"),
            tick_runner=lambda **kwargs: calls.append("tick"),
            print_json=printer,
        )

        assert exit_code == 0
        assert calls == []
        assert printer.payload() == {
            "enabled": False,
            "config_valid": True,
            "uid": None,
            "worker_id": None,
            "leased_count": 0,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "ack_failed_count": 0,
            "actions": [],
            "errors": [],
        }

    def test_entrypoint_malformed_enabled_env_is_denied_without_tick(self):
        calls = []
        printer = TestEntrypoint._Printer()

        exit_code = entrypoint.run_vector_repair_outbox_worker_entrypoint(
            env={"MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "yes"},
            db_client=object(),
            authoritative_item_loader=lambda record: calls.append("load"),
            vector_deleter=lambda record: calls.append("delete"),
            vector_repairer=lambda record, item: calls.append("repair"),
            tick_runner=lambda **kwargs: calls.append("tick"),
            print_json=printer,
        )

        payload = printer.payload()
        assert exit_code == 2
        assert calls == []
        assert payload["enabled"] is False
        assert payload["config_valid"] is False
        assert payload["errors"] == [
            {"stage": "config", "error": "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED must be 'true' or 'false'"}
        ]

    def test_entrypoint_enabled_requires_explicit_uid_and_stable_worker_id(self):
        calls = []
        printer = TestEntrypoint._Printer()

        exit_code = entrypoint.run_vector_repair_outbox_worker_entrypoint(
            env={"MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true", "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u1"},
            db_client=object(),
            authoritative_item_loader=lambda record: calls.append("load"),
            vector_deleter=lambda record: calls.append("delete"),
            vector_repairer=lambda record, item: calls.append("repair"),
            tick_runner=lambda **kwargs: calls.append("tick"),
            print_json=printer,
        )

        payload = printer.payload()
        assert exit_code == 2
        assert calls == []
        assert payload["config_valid"] is False
        assert payload["errors"] == [
            {"stage": "config", "error": "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID is required when enabled"}
        ]

    def test_entrypoint_enabled_invokes_injected_tick_and_prints_deterministic_summary(self):
        printer = TestEntrypoint._Printer()
        captured = {}

        def fake_tick_runner(**kwargs):
            captured.update(kwargs)
            return {
                "enabled": True,
                "worker_id": "worker-a",
                "uid": "u1",
                "leased_count": 1,
                "processed_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "ack_failed_count": 0,
                "actions": [{"record_id": "rec-1", "idempotency_key": "idem-1", "action": "delete"}],
                "errors": [],
            }

        db = object()
        loader = object()
        deleter = object()
        repairer = object()
        exit_code = entrypoint.run_vector_repair_outbox_worker_entrypoint(
            env={
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
                "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u1",
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
                "MEMORY_VECTOR_REPAIR_OUTBOX_LIMIT": "7",
                "MEMORY_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS": "90",
                "MEMORY_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS": "4",
            },
            db_client=db,
            authoritative_item_loader=loader,
            vector_deleter=deleter,
            vector_repairer=repairer,
            tick_runner=fake_tick_runner,
            print_json=printer,
        )

        assert exit_code == 0
        assert captured["db_client"] is db
        assert captured["uid"] == "u1"
        assert captured["config"].enabled is True
        assert captured["config"].worker_id == "worker-a"
        assert captured["config"].limit == 7
        assert captured["config"].lease_seconds == 90
        assert captured["config"].max_attempts == 4
        assert captured["authoritative_item_loader"] is loader
        assert captured["vector_deleter"] is deleter
        assert captured["vector_repairer"] is repairer
        assert printer.payload()["actions"] == [{"record_id": "rec-1", "idempotency_key": "idem-1", "action": "delete"}]

    def test_entrypoint_dependency_or_action_failure_is_summarized_and_nonzero(self):
        printer = TestEntrypoint._Printer()

        def fake_tick_runner(**kwargs):
            return {
                "enabled": True,
                "worker_id": "worker-a",
                "uid": "u1",
                "leased_count": 1,
                "processed_count": 0,
                "skipped_count": 0,
                "failed_count": 1,
                "ack_failed_count": 0,
                "actions": [],
                "errors": [{"stage": "process", "record_id": "rec-1", "error": "pinecone unavailable"}],
            }

        exit_code = entrypoint.run_vector_repair_outbox_worker_entrypoint(
            env={
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
                "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u1",
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
            },
            db_client=object(),
            authoritative_item_loader=lambda record: None,
            vector_deleter=lambda record: None,
            vector_repairer=lambda record, item: None,
            tick_runner=fake_tick_runner,
            print_json=printer,
        )

        payload = printer.payload()
        assert exit_code == 1
        assert payload["failed_count"] == 1
        assert payload["errors"] == [{"stage": "process", "record_id": "rec-1", "error": "pinecone unavailable"}]

    def test_entrypoint_contract_has_no_scheduler_enqueue_side_effects(self):
        source = entrypoint.__loader__.get_source(entrypoint.__name__)

        assert "enqueue_" not in source
        assert "CloudTasksClient" not in source
        assert "firebase emulators" not in source

    def test_main_disabled_path_does_not_initialize_production_dependencies(self, monkeypatch):
        printer = TestEntrypoint._Printer()
        calls = []

        monkeypatch.setattr(
            entrypoint, "build_vector_repair_outbox_production_dependencies", lambda env: calls.append("deps")
        )

        exit_code = entrypoint.main(env={}, print_json=printer)

        assert exit_code == 0
        assert calls == []
        assert printer.payload()["enabled"] is False

    def test_main_enabled_calls_production_dependency_resolver_once(self, monkeypatch):
        printer = TestEntrypoint._Printer()
        calls = []
        deps = entrypoint.VectorRepairOutboxProductionDependencies(
            db_client=object(),
            authoritative_item_loader=object(),
            vector_deleter=object(),
            vector_repairer=object(),
        )

        def fake_resolver(env):
            calls.append(dict(env))
            return deps

        def fake_runner(**kwargs):
            return {
                "enabled": True,
                "worker_id": "worker-a",
                "uid": "u1",
                "leased_count": 0,
                "processed_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "ack_failed_count": 0,
                "actions": [],
                "errors": [],
            }

        monkeypatch.setattr(entrypoint, "build_vector_repair_outbox_production_dependencies", fake_resolver)

        exit_code = entrypoint.main(
            env={
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
                "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u1",
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
            },
            tick_runner=fake_runner,
            print_json=printer,
        )

        assert exit_code == 0
        assert len(calls) == 1
        assert calls[0]["MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED"] == "true"
        assert printer.payload()["config_valid"] is True

    def test_main_enabled_missing_production_dependency_config_fails_before_lease(self, monkeypatch):
        printer = TestEntrypoint._Printer()
        calls = []

        def fake_runner(**kwargs):
            calls.append("tick")
            return {}

        exit_code = entrypoint.main(
            env={
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
                "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u1",
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
            },
            tick_runner=fake_runner,
            print_json=printer,
        )

        payload = printer.payload()
        assert exit_code == 2
        assert calls == []
        assert payload["config_valid"] is False
        assert payload["errors"] == [
            {
                "stage": "dependencies",
                "error": "PINECONE_API_KEY is required when memory vector repair worker is enabled",
            }
        ]

    def test_http_shim_disabled_post_fails_closed_without_dependency_initialization(self):
        calls = []
        app = entrypoint.create_vector_repair_outbox_worker_app(
            env={},
            dependency_builder=lambda env: calls.append("deps"),
            tick_runner=lambda **kwargs: calls.append("tick"),
        )

        response = app.routes_by_path["/memory-vector-repair-outbox-worker/tick"]()

        assert calls == []
        assert response == {
            "enabled": False,
            "config_valid": True,
            "uid": None,
            "worker_id": None,
            "leased_count": 0,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "ack_failed_count": 0,
            "actions": [],
            "errors": [],
        }

    def test_http_shim_enabled_malformed_config_denies_before_dependencies(self):
        calls = []
        app = entrypoint.create_vector_repair_outbox_worker_app(
            env={"MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true"},
            dependency_builder=lambda env: calls.append("deps"),
            tick_runner=lambda **kwargs: calls.append("tick"),
        )

        response = app.routes_by_path["/memory-vector-repair-outbox-worker/tick"]()

        assert calls == []
        assert response["config_valid"] is False
        assert response["errors"] == [
            {"stage": "config", "error": "MEMORY_VECTOR_REPAIR_OUTBOX_UID is required when enabled"}
        ]

    def test_http_shim_enabled_uses_fake_dependencies_for_one_tick_summary(self):
        calls = []
        deps = entrypoint.VectorRepairOutboxProductionDependencies(
            db_client=object(),
            authoritative_item_loader=object(),
            vector_deleter=object(),
            vector_repairer=object(),
        )

        def fake_dependency_builder(env):
            calls.append(("deps", dict(env)))
            return deps

        def fake_tick_runner(**kwargs):
            calls.append(("tick", kwargs))
            return {
                "enabled": True,
                "worker_id": "worker-http",
                "uid": "u-http",
                "leased_count": 1,
                "processed_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "ack_failed_count": 0,
                "actions": [{"record_id": "rec-http", "idempotency_key": "idem-http", "action": "repair"}],
                "errors": [],
            }

        app = entrypoint.create_vector_repair_outbox_worker_app(
            env={
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
                "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u-http",
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-http",
            },
            dependency_builder=fake_dependency_builder,
            tick_runner=fake_tick_runner,
        )

        response = app.routes_by_path["/memory-vector-repair-outbox-worker/tick"]()

        assert calls[0][0] == "deps"
        assert calls[1][0] == "tick"
        assert calls[1][1]["db_client"] is deps.db_client
        assert response["config_valid"] is True
        assert response["actions"] == [{"record_id": "rec-http", "idempotency_key": "idem-http", "action": "repair"}]

    def test_http_shim_dependency_failure_is_deterministic_summary_before_tick(self):
        calls = []

        def failing_dependency_builder(env):
            calls.append(("deps", dict(env)))
            raise ValueError("PINECONE_API_KEY is required when memory vector repair worker is enabled")

        app = entrypoint.create_vector_repair_outbox_worker_app(
            env={
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
                "MEMORY_VECTOR_REPAIR_OUTBOX_UID": "u-http",
                "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-http",
            },
            dependency_builder=failing_dependency_builder,
            tick_runner=lambda **kwargs: calls.append(("tick", kwargs)),
        )

        response = app.routes_by_path["/memory-vector-repair-outbox-worker/tick"]()

        assert [call[0] for call in calls] == ["deps"]
        assert response["config_valid"] is False
        assert response["errors"] == [
            {
                "stage": "dependencies",
                "error": "PINECONE_API_KEY is required when memory vector repair worker is enabled",
            }
        ]

    def test_http_shim_documents_cloud_run_iam_oidc_enforcement_not_custom_auth(self):
        source = entrypoint.__loader__.get_source(entrypoint.__name__)

        assert "Cloud Run IAM (roles/run.invoker)" in source
        assert "OIDC" in source
        assert "custom shared secret" not in source
        assert "MEMORY_VECTOR_REPAIR_OUTBOX_UID" in source

    def test_production_dependency_resolver_builds_lazy_clients_and_loader_from_env(self):
        calls = []
        docs = {
            "users/u1/memory_items/mem1": {
                "memory_id": "mem1",
                "uid": "u1",
                "version": 1,
                "tier": "long_term",
                "status": "active",
                "processing_state": "processed",
                "content": "User prefers concise updates.",
                "evidence": [
                    {
                        "evidence_id": "ev1",
                        "source_id": "src1",
                        "source_version": "v1",
                        "source_type": "conversation",
                        "artifact_preservation": "preserved",
                        "source_state": "active",
                    }
                ],
                "source_state": "active",
                "sensitivity_labels": [],
                "visibility": "private",
                "user_asserted": False,
                "captured_at": "2026-06-19T00:00:00+00:00",
                "updated_at": "2026-06-19T00:00:00+00:00",
                "ledger_commit_id": "ledger-1",
                "ledger_sequence": 1,
                "item_revision": 2,
                "source_commit_id": "source-1",
                "content_hash": "hash-1",
                "account_generation": 7,
            }
        }

        class Snapshot:
            def __init__(self, data):
                self.exists = data is not None
                self._data = data

            def to_dict(self):
                return self._data

        class Document:
            def __init__(self, path):
                self.path = path

            def get(self):
                calls.append(("get", self.path))
                return Snapshot(docs.get(self.path))

        class DB:
            def document(self, path):
                return Document(path)

        class Index:
            def delete(self, **kwargs):
                calls.append(("delete", kwargs))
                return {"deleted": 1}

            def upsert(self, **kwargs):
                calls.append(("upsert", kwargs))
                return {"upserted": 1}

        class PineconeClient:
            def __init__(self, api_key):
                calls.append(("pinecone", api_key))

            def Index(self, name):
                calls.append(("index", name))
                return Index()

        class PineconeModule:
            Pinecone = PineconeClient

        class ClientModule:
            db = DB()

        class Embeddings:
            def embed_query(self, content):
                calls.append(("embed", content))
                return [0.1, 0.2]

        class LlmClientsModule:
            embeddings = Embeddings()

        def module_loader(name):
            calls.append(("import", name))
            if name == "pinecone":
                return PineconeModule
            if name == "database._client":
                return ClientModule
            if name == "utils.llm.clients":
                return LlmClientsModule
            raise AssertionError(name)

        deps = entrypoint.build_vector_repair_outbox_production_dependencies(
            {
                "PINECONE_API_KEY": "pc-key",
                "PINECONE_INDEX_NAME": "memory-index",
                "OPENAI_API_KEY": "openai-key",
            },
            module_loader=module_loader,
        )

        item = deps.authoritative_item_loader({"uid": "u1", "memory_id": "mem1"})
        deps.vector_deleter({"vector_id": "vec1"})
        deps.vector_repairer({"required_projection_commit_id": "projection-1"}, item)

        assert ("pinecone", "pc-key") in calls
        assert ("index", "memory-index") in calls
        assert ("get", "users/u1/memory_items/mem1") in calls
        assert ("delete", {"ids": ["vec1"], "namespace": "ns2"}) in calls
        assert ("embed", "User prefers concise updates.") in calls
        assert any(call[0] == "upsert" and call[1]["namespace"] == "ns2" for call in calls)
