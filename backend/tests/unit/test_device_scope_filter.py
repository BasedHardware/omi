from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.device_scope_filter import filter_items_by_device_scope, memory_matches_device


def _item(*, primary: str | None = None, devices: list[str] | None = None, evidence_device: str | None = None):
    evidence = []
    if evidence_device:
        evidence.append(
            MemoryEvidence(
                evidence_id="ev1",
                source_type="conversation",
                source_id="conv-1",
                source_version="v1",
                conversation_id="conv-1",
                artifact_preservation=ArtifactPreservationState.preserved,
                client_device_id=evidence_device,
            )
        )
    now = datetime.now(timezone.utc)
    return MemoryItem(
        memory_id="m1",
        uid="u1",
        version=1,
        tier=MemoryLayer.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="hello",
        evidence=evidence,
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=7),
        capture_device_ids=devices or [],
        primary_capture_device=primary,
    )


def test_filter_current_device_matches_primary():
    items = [_item(primary="macos_abc12345"), _item(primary="ios_deadbeef")]
    filtered = filter_items_by_device_scope(items, device_scope="current", client_device_id="macos_abc12345")
    assert len(filtered) == 1
    assert filtered[0].primary_capture_device == "macos_abc12345"


def test_memory_matches_device_via_evidence():
    item = _item(evidence_device="ios_abcd1234")
    assert memory_matches_device(item, "ios_abcd1234")
