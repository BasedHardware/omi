"""Shared Firestore + memory-item fakes for chat/developer/MCP adapter unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_search_gateway import SearchVectorHit
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryTier, ProcessingState
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS


class Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self):
        self._db_client.document_get_paths.append(self.path)
        if self.path not in self._db_client.docs:
            return Snapshot(None, exists=False)
        return Snapshot(self._db_client.docs[self.path], exists=True)


class CollectionRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def stream(self):
        prefix = f"{self.path}/"
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if path.startswith(prefix) and "/" not in path[len(prefix) :]:
                snapshots.append(Snapshot(data))
        return snapshots


class FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.collection_paths = []
        self.document_paths = []
        self.document_get_paths = []

    def collection(self, path):
        self.collection_paths.append(path)
        return CollectionRef(self, path)

    def document(self, path):
        self.document_paths.append(path)
        return DocumentRef(self, path)


class VectorCandidateResult:
    def __init__(self, hits, rejected_count=0):
        self.hits = hits
        self.rejected_count = rejected_count


def evidence(source_id: str = "conv1", *, quote_text: str) -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=f"ev-{source_id}",
        source_id=source_id,
        source_type="conversation",
        source_version="v1",
        quote_refs=[{"text": quote_text}],
        content_hash="hash1",
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def memory_item(
    memory_id: str,
    *,
    tier=MemoryTier.short_term,
    now=None,
    captured_at=None,
    content=None,
    quote_text: str,
    **overrides,
) -> MemoryItem:
    now = now or datetime.now(timezone.utc)
    captured_at = captured_at or (now - timedelta(days=1))
    data = {
        "memory_id": memory_id,
        "uid": "u1",
        "version": 1,
        "tier": tier,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": content or f"{memory_id} coffee preference",
        "evidence": [evidence(f"{memory_id}-source", quote_text=quote_text)],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": captured_at,
        "updated_at": captured_at,
        "expires_at": (
            captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS) if tier == MemoryTier.short_term else None
        ),
        "ledger_commit_id": "commit-1" if tier == MemoryTier.long_term else None,
        "ledger_sequence": 1 if tier == MemoryTier.long_term else None,
        "item_revision": 1,
        "source_commit_id": f"source-commit-{memory_id}",
        "content_hash": f"content-hash-{memory_id}",
        "account_generation": 3,
    }
    data.update(overrides)
    return MemoryItem(**data)


def stored_item(item: MemoryItem) -> dict:
    return item.model_dump(mode="json")


def vector_hit(item: MemoryItem, *, score, projection_commit_id="projection-1") -> SearchVectorHit:
    return SearchVectorHit(
        memory_id=item.memory_id,
        score=score,
        projection_commit_id=projection_commit_id,
        vector_updated_at=item.updated_at + timedelta(minutes=1),
        uid=item.uid,
        account_generation=item.account_generation,
        item_revision=item.item_revision,
        source_commit_id=item.source_commit_id,
        content_hash=item.content_hash,
    )


def enabled_rollout_doc(uid: str = "u1", *, grant_consumer: str) -> dict:
    return {
        "schema_version": 1,
        "uid": uid,
        "mode": MemoryRolloutMode.read.value,
        "mode_epoch": 7,
        "cutover_epoch": 7,
        "account_generation": 3,
        "vector_projection_commit_id": "projection-1",
        "fallback_projection_ready": True,
        "persistent_memory_writes_started": True,
        "writes_blocked": False,
        "stage_gates": {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        },
        "grants": {
            grant_consumer: {
                "default_memory": True,
                "archive": True,
            }
        },
    }
