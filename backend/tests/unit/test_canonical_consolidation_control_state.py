"""The L2 watermark writer must never rewind the transactional apply head."""

from datetime import datetime, timezone

from models.memory_apply import MemoryControlState
from utils.memory.canonical_consolidation import _persist_control_state

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    exists = True

    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


class _Document:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self):
        return _Snapshot(self.db.docs[self.path])

    def set(self, payload, merge=False):
        if merge:
            self.db.docs[self.path] = {**self.db.docs[self.path], **payload}
        else:
            self.db.docs[self.path] = payload


class _Db:
    def __init__(self, path, payload):
        self.docs = {path: payload}

    def document(self, path):
        return _Document(self, path)


def test_watermark_merge_preserves_concurrent_apply_fields():
    path = "users/u1/memory_state/apply_control"
    persisted = MemoryControlState(
        uid="u1",
        head_commit_id="head-concurrent",
        account_generation=3,
        source_generation=7,
        commit_sequence=42,
        projection_watermark_commit_id="projection-concurrent",
        projection_watermark_sequence=42,
        vector_watermark_commit_id="vector-concurrent",
    ).model_dump(mode="json")
    db = _Db(path, persisted)
    stale_snapshot = MemoryControlState(
        uid="u1",
        head_commit_id="head-stale",
        account_generation=3,
        source_generation=7,
        commit_sequence=10,
        last_consolidation_run_at=NOW,
        updated_at=NOW,
    )

    _persist_control_state(stale_snapshot, db_client=db)

    stored = db.docs[path]
    assert stored["head_commit_id"] == "head-concurrent"
    assert stored["commit_sequence"] == 42
    assert stored["projection_watermark_commit_id"] == "projection-concurrent"
    assert stored["vector_watermark_commit_id"] == "vector-concurrent"
    assert stored["last_consolidation_run_at"] == NOW.isoformat()
