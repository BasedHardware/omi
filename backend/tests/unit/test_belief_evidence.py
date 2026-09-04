from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.belief_evidence import (
    EvidenceEventJudgment,
    EvidenceEventKind,
    admit_claim_against_neighbors,
    patch_for_evidence_event,
)

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _item(**updates) -> MemoryItem:
    data = {
        "memory_id": "mem-old",
        "uid": "uid-1",
        "version": 1,
        "tier": MemoryLayer.short_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Lives in NYC",
        "evidence": [
            MemoryEvidence(
                evidence_id="ev-1",
                source_type="conversation",
                source_id="conv-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
                source_state=SourceState.active,
            )
        ],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": NOW,
        "updated_at": NOW,
        "expires_at": NOW + timedelta(days=2),
        "corroboration_count": 0,
    }
    data.update(updates)
    return MemoryItem(**data)


def test_restated_increments_corroboration_and_resets_clock():
    existing = _item()
    patch = patch_for_evidence_event(
        existing,
        EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id="mem-old"),
        pointer="mem-new",
        now=NOW,
    )
    assert patch is not None
    logical, extra = patch
    assert extra["corroboration_count"] == 1
    assert extra["last_corroborated_at"] == NOW
    assert logical["metadata"]["evidence_event"] == "restated"
    assert logical["metadata"]["pointer"] == "mem-new"


def test_contradicted_supersedes_when_authorized():
    existing = _item()
    patch = patch_for_evidence_event(
        existing,
        EvidenceEventJudgment(event=EvidenceEventKind.contradicted, target_memory_id="mem-old"),
        pointer="mem-new",
        now=NOW,
        new_is_as_authoritative=True,
    )
    assert patch is not None
    logical, extra = patch
    assert extra["confidence"] == 0.0
    assert extra["superseded_by"] == "mem-new"
    assert logical["result_status"] == "superseded"


def test_contradicted_lowers_truth_without_supersede_when_less_authoritative():
    existing = _item(user_asserted=True)
    patch = patch_for_evidence_event(
        existing,
        EvidenceEventJudgment(event=EvidenceEventKind.contradicted, target_memory_id="mem-old"),
        pointer="mem-new",
        now=NOW,
        new_is_as_authoritative=False,
    )
    assert patch is not None
    logical, extra = patch
    assert extra["confidence"] == 0.0
    assert "superseded_by" not in extra
    assert "result_status" not in logical


def test_resolved_sets_valid_to():
    existing = _item()
    patch = patch_for_evidence_event(
        existing,
        EvidenceEventJudgment(event=EvidenceEventKind.resolved, target_memory_id="mem-old"),
        pointer="mem-new",
        now=NOW,
    )
    assert patch is not None
    logical, extra = patch
    assert logical["valid_to"] == NOW
    assert "result_status" not in logical
    assert extra == {}


def test_unrelated_and_similarity_alone_write_nothing():
    existing = _item()
    assert (
        patch_for_evidence_event(
            existing,
            EvidenceEventJudgment(event=EvidenceEventKind.unrelated),
            pointer="mem-new",
            now=NOW,
        )
        is None
    )


def test_admit_is_noop_when_flag_off(monkeypatch):
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    applied = []
    judgment = admit_claim_against_neighbors(
        "uid-1",
        "mem-new",
        "Lives in NYC",
        db_client=SimpleNamespace(),
        neighbor_fetcher=lambda *_: [{"memory_id": "mem-old", "content": "Lives in NYC", "score": 0.99}],
        judge=lambda *_: EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id="mem-old"),
        applier=lambda *args: applied.append(args),
    )
    assert judgment is None
    assert applied == []


def test_admit_unrelated_does_not_apply(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    applied = []
    judgment = admit_claim_against_neighbors(
        "uid-1",
        "mem-new",
        "Likes tea",
        db_client=SimpleNamespace(),
        neighbor_fetcher=lambda *_: [{"memory_id": "mem-old", "content": "Lives in NYC", "score": 0.4}],
        judge=lambda *_: (_ for _ in ()).throw(AssertionError("judge must not run below the similarity gate")),
        applier=lambda *args: applied.append(args),
    )
    assert judgment is not None
    assert judgment.event is EvidenceEventKind.unrelated
    assert judgment.rationale == "below similarity gate"
    assert applied == []


def test_admit_below_score_gate_skips_judge(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    monkeypatch.setenv("MEMORY_BELIEF_ADMISSION_MIN_SCORE", "0.75")
    judged = []

    def _judge(*_):
        judged.append(True)
        raise AssertionError("judge must not run below the similarity gate")

    judgment = admit_claim_against_neighbors(
        "uid-1",
        "mem-new",
        "Likes tea",
        db_client=SimpleNamespace(),
        neighbor_fetcher=lambda *_: [
            {"memory_id": "mem-old", "content": "Lives in NYC", "score": 0.74},
            {"memory_id": "mem-far", "content": "Owns a cat", "score": 0.2},
        ],
        judge=_judge,
        applier=lambda *args: None,
    )
    assert judged == []
    assert judgment is not None
    assert judgment.event is EvidenceEventKind.unrelated
    assert judgment.rationale == "below similarity gate"


def test_admit_at_score_gate_calls_judge(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    judged = []

    def _judge(_content, neighbors):
        judged.append([row.get("memory_id") for row in neighbors])
        return EvidenceEventJudgment(event=EvidenceEventKind.unrelated, rationale="asked")

    judgment = admit_claim_against_neighbors(
        "uid-1",
        "mem-new",
        "Likes tea",
        db_client=SimpleNamespace(),
        neighbor_fetcher=lambda *_: [
            {"memory_id": "mem-old", "content": "Prefers tea", "score": 0.75},
            {"memory_id": "mem-far", "content": "Owns a cat", "score": 0.1},
        ],
        judge=_judge,
        applier=lambda *args: None,
    )
    assert judged == [["mem-old"]]
    assert judgment is not None
    assert judgment.rationale == "asked"


def test_schedule_belief_admission_does_not_wait(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    waited = []
    submitted = []

    class _Future:
        def result(self, *_a, **_k):
            waited.append(True)
            return None

        def add_done_callback(self, _cb):
            return None

    def _submit(_executor, fn, *args, **kwargs):
        submitted.append((fn, args, kwargs))
        return _Future()

    monkeypatch.setattr("utils.executors.submit_with_context", _submit)
    from utils.memory.belief_evidence import schedule_belief_admission

    schedule_belief_admission("uid-1", "mem-new", "Likes tea", db_client=SimpleNamespace(), new_user_asserted=False)
    assert submitted
    assert waited == []
    fn, args, kwargs = submitted[0]
    assert fn is admit_claim_against_neighbors
    assert args[:3] == ("uid-1", "mem-new", "Likes tea")
    assert kwargs["new_user_asserted"] is False


def test_admit_restated_applies_to_existing_row(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    existing = _item()
    applied = []
    judgment = admit_claim_against_neighbors(
        "uid-1",
        "mem-new",
        "Lives in NYC",
        db_client=SimpleNamespace(),
        now=NOW,
        neighbor_fetcher=lambda *_: [{"memory_id": "mem-old", "content": "Lives in NYC", "score": 0.95}],
        judge=lambda *_: EvidenceEventJudgment(event=EvidenceEventKind.restated, target_memory_id="mem-old"),
        applier=lambda *args: applied.append(args),
        reader=lambda _uid, memory_id, _db: existing if memory_id == "mem-old" else None,
    )
    assert judgment.event is EvidenceEventKind.restated
    assert len(applied) == 1
    uid, memory_id, logical, extra, _db = applied[0]
    assert uid == "uid-1"
    assert memory_id == "mem-old"
    assert extra["corroboration_count"] == 1
    assert logical["metadata"]["pointer"] == "mem-new"
