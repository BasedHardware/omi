"""The L2 watermark writer must never rewind the transactional apply head."""

from datetime import datetime, timezone

from database import document_store
from models.memory_apply import MemoryControlState
from tests.store_fakes import FakeDocumentStore
from utils.memory.canonical_consolidation import _persist_control_state

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def test_watermark_merge_preserves_concurrent_apply_fields(monkeypatch):
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
    docs = {path: persisted}
    monkeypatch.setattr(document_store, "_store", lambda: FakeDocumentStore(backing=docs))

    stale_snapshot = MemoryControlState(
        uid="u1",
        head_commit_id="head-stale",
        account_generation=3,
        source_generation=7,
        commit_sequence=10,
        last_consolidation_run_at=NOW,
        updated_at=NOW,
    )

    _persist_control_state(stale_snapshot)

    stored = docs[path]
    assert stored["head_commit_id"] == "head-concurrent"
    assert stored["commit_sequence"] == 42
    assert stored["projection_watermark_commit_id"] == "projection-concurrent"
    assert stored["vector_watermark_commit_id"] == "vector-concurrent"
    assert stored["last_consolidation_run_at"] == NOW.isoformat()
