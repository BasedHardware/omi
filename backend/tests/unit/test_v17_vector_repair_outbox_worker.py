from datetime import datetime, timezone

from database.v17_vector_repair_outbox_worker import (
    ack_v17_vector_repair_purge_outbox_record,
    lease_v17_vector_repair_purge_outbox_records,
    process_v17_vector_repair_purge_outbox_records,
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
    data = {
        "memory_id": "mem-1",
        "uid": "u1",
        "status": "active",
        "source_state": "active",
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
            return data.get(field) <= value
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


def test_firestore_reader_leases_only_available_pending_vector_repair_records_and_ack_updates_path():
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

    leased = lease_v17_vector_repair_purge_outbox_records(
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

    ack_v17_vector_repair_purge_outbox_record(
        db_client=db,
        record=leased[0],
        patch={"status": "completed", "action": "repair"},
        now=now,
    )

    assert db.store["users/u1/memory_outbox/available"]["status"] == "completed"
    assert db.store["users/u1/memory_outbox/available"]["action"] == "repair"
    assert db.store["users/u1/memory_outbox/available"]["updated_at"] == now.isoformat()


def test_firestore_reader_claim_uses_transaction_when_client_supports_it():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    path = "users/u1/memory_outbox/transactional"
    db = _FakeTransactionalFirestore(
        {path: _record(record_id="transactional", outbox_path=path, available_at=now.isoformat())}
    )

    leased = lease_v17_vector_repair_purge_outbox_records(
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


def test_duplicate_lease_after_claim_does_not_duplicate_worker_action():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    path = "users/u1/memory_outbox/dup"
    db = _FakeFirestore({path: _record(record_id="dup", outbox_path=path, available_at=now.isoformat())})
    deleted = []

    first_lease = lease_v17_vector_repair_purge_outbox_records(
        db_client=db,
        uid="u1",
        worker_id="worker-a",
        limit=10,
        lease_seconds=30,
        now=now,
    )
    second_lease = lease_v17_vector_repair_purge_outbox_records(
        db_client=db,
        uid="u1",
        worker_id="worker-b",
        limit=10,
        lease_seconds=30,
        now=now,
    )

    result = process_v17_vector_repair_purge_outbox_records(
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


def test_ack_writer_failure_propagates_deterministically():
    class _FailingFirestore(_FakeFirestore):
        def document(self, path):
            raise RuntimeError(f"write failed for {path}")

    try:
        ack_v17_vector_repair_purge_outbox_record(
            db_client=_FailingFirestore(),
            record=_record(record_id="bad", outbox_path="users/u1/memory_outbox/bad"),
            patch={"status": "dead_letter"},
        )
    except RuntimeError as exc:
        assert "users/u1/memory_outbox/bad" in str(exc)
    else:
        raise AssertionError("expected ack writer failure to propagate")


def test_worker_deletes_stale_vector_when_authoritative_item_is_missing():
    deleted = []
    repaired = []
    updates = _Updates()

    result = process_v17_vector_repair_purge_outbox_records(
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


def test_worker_repairs_stale_live_authoritative_item():
    deleted = []
    repaired = []
    updates = _Updates()

    result = process_v17_vector_repair_purge_outbox_records(
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


def test_worker_tombstone_precedence_deletes_even_when_stale_record_could_repair():
    deleted = []
    repaired = []

    process_v17_vector_repair_purge_outbox_records(
        [_record(reason="stale_projection_commit")],
        authoritative_item_loader=lambda record: _live_item(status="tombstoned"),
        vector_deleter=lambda record: deleted.append(record["vector_id"]),
        vector_repairer=lambda record, item: repaired.append(record["vector_id"]),
        outbox_updater=lambda record, patch: None,
    )

    assert deleted == ["vec-1"]
    assert repaired == []


def test_worker_skips_terminal_in_progress_and_duplicate_pending_idempotency_keys():
    deleted = []
    updates = _Updates()
    records = [
        _record(record_id="completed", idempotency_key="completed-key", status="completed"),
        _record(record_id="dead", idempotency_key="dead-key", status="dead_letter"),
        _record(record_id="lease", idempotency_key="lease-key", status="in_progress"),
        _record(record_id="dup-a", idempotency_key="dup-key"),
        _record(record_id="dup-b", idempotency_key="dup-key"),
    ]

    result = process_v17_vector_repair_purge_outbox_records(
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


def test_worker_records_retry_and_dead_letter_failure_deterministically():
    retry_updates = _Updates()
    dead_updates = _Updates()

    def failing_delete(record):
        raise RuntimeError("pinecone unavailable")

    retry_result = process_v17_vector_repair_purge_outbox_records(
        [_record(record_id="retry", idempotency_key="retry-key", attempt_count=0)],
        authoritative_item_loader=lambda record: None,
        vector_deleter=failing_delete,
        vector_repairer=lambda record, item: None,
        outbox_updater=retry_updates,
        max_attempts=3,
    )
    dead_result = process_v17_vector_repair_purge_outbox_records(
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
