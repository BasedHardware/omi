from database.v17_vector_repair_outbox_worker import process_v17_vector_repair_purge_outbox_records


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
