"""Regression test for the memory-promotion control-state persist path.

`_persist_control_state` used a full-document `.set(control.model_dump())`, which
overwrote the entire `memory_apply_control_state` doc from a non-transactional read
snapshot. A concurrent `apply_long_term_patch_firestore` transaction landing between
promotion's read and this write had its `head_commit_id` / `commit_sequence` /
watermarks silently reverted (lost update). The fix writes only the two fields
promotion owns (`last_promotion_run_at`, `updated_at`) with `merge=True`, mirroring
the consolidation writer.
"""

from datetime import datetime, timezone

from models.memory_apply import MemoryControlState
from utils.memory.short_term_promotion import _persist_control_state


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            merged = dict(self._db.docs[self.path])
            merged.update(data)
            self._db.docs[self.path] = merged
        else:
            self._db.docs[self.path] = data


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def document(self, path):
        return _DocRef(self, path)


def test_persist_control_state_preserves_concurrently_advanced_head():
    uid = "user-promo"
    control_path = f"memory_apply/{uid}/state/control"

    # Seed the control doc as if a concurrent apply advanced the head/watermarks
    # AFTER promotion read its (now stale) snapshot.
    db = _FakeDb(
        {
            control_path: {
                "uid": uid,
                "head_commit_id": "head-ADVANCED",
                "account_generation": 1,
                "source_generation": 1,
                "commit_sequence": 42,
                "projection_watermark_commit_id": "proj-ADVANCED",
                "projection_watermark_sequence": 42,
                "vector_watermark_commit_id": "vec-ADVANCED",
            }
        }
    )

    # Promotion stamps only its two owned fields, carrying a STALE head snapshot.
    now = datetime(2026, 7, 12, 3, 0, 0, tzinfo=timezone.utc)
    stale_control = MemoryControlState(
        uid=uid,
        head_commit_id="head-STALE",
        account_generation=1,
        source_generation=1,
        commit_sequence=0,
        last_promotion_run_at=now,
        updated_at=now,
    )

    # Point the collection-path builder at our seeded doc path.
    import utils.memory.short_term_promotion as promo

    original = promo.MemoryCollections

    class _StubCollections:
        def __init__(self, uid):
            self.memory_apply_control_state = control_path

    promo.MemoryCollections = _StubCollections
    try:
        _persist_control_state(stale_control, db_client=db)
    finally:
        promo.MemoryCollections = original

    persisted = db.docs[control_path]
    # The concurrently-advanced fields must survive (merge, not overwrite).
    assert persisted["head_commit_id"] == "head-ADVANCED"
    assert persisted["commit_sequence"] == 42
    assert persisted["projection_watermark_commit_id"] == "proj-ADVANCED"
    assert persisted["vector_watermark_commit_id"] == "vec-ADVANCED"
    # Promotion's owned fields are updated.
    assert persisted["last_promotion_run_at"] == now.isoformat()
    assert persisted["updated_at"] == now.isoformat()
