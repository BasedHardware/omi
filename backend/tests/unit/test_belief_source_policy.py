from datetime import datetime, timedelta, timezone

from models.memories import Memory, MemoryCaptureContext, MemoryCategory, MemoryDB
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.belief_source_policy import (
    AUTHORITY,
    eligible_record,
    evidence_families,
    independent_authoritative_evidence,
    source_authority,
)

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _evidence(
    evidence_id: str,
    *,
    source_type: str = "conversation",
    source_id: str = "conv-1",
    source_signal: str | None = "transcription",
    independence_group: str | None = None,
    lineage_id: str | None = None,
    attribution: str | None = None,
    source_state: SourceState = SourceState.active,
) -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=evidence_id,
        source_type=source_type,
        source_id=source_id,
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
        source_state=source_state,
        source_state_reason=("deleted_by_user" if source_state != SourceState.active else None),
        source_signal=source_signal,
        independence_group=independence_group,
        lineage_id=lineage_id,
        attribution=attribution,
    )


def _item(memory_id: str, evidence: MemoryEvidence, **updates: object) -> MemoryItem:
    data: dict[str, object] = {
        "memory_id": memory_id,
        "uid": "uid-1",
        "version": 1,
        "tier": MemoryLayer.short_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Lives in NYC",
        "evidence": [evidence],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": NOW,
        "updated_at": NOW,
        "expires_at": NOW + timedelta(days=2),
    }
    data.update(updates)
    return MemoryItem(**data)


def test_twenty_ocr_frames_with_no_lineage_cannot_corroborate_a_voice_claim():
    voice = _item("voice", _evidence("voice-1", source_id="conv-1"))

    frames = [
        _item(
            f"screen-{index}",
            _evidence(
                f"frame-{index}",
                source_type="screen",
                source_id=f"frame-{index}",
                source_signal="ocr",
                # A frame identifier is transport identity, not an
                # independence claim. Producers omit the group when the
                # original capture family is unknown.
                independence_group="unknown",
            ),
        )
        for index in range(20)
    ]

    assert all(not evidence_families(frame) for frame in frames)
    assert all(not independent_authoritative_evidence(frame, voice) for frame in frames)


def test_repeated_copies_from_one_capture_family_cannot_corrobate_twice():
    first = _item(
        "first",
        _evidence(
            "ev-first",
            source_id="frame-1",
            source_type="screen",
            source_signal="ocr",
            lineage_id="screen-capture-1",
        ),
    )
    copies = [
        _item(
            f"copy-{index}",
            _evidence(
                f"ev-copy-{index}",
                source_id=f"frame-{index + 2}",
                source_type="screen",
                source_signal="ocr",
                lineage_id="screen-capture-1",
            ),
        )
        for index in range(20)
    ]

    assert all(evidence_families(copy) == frozenset({"screen-capture-1"}) for copy in copies)
    assert all(not independent_authoritative_evidence(copy, first) for copy in copies)


def test_unknown_and_assistant_evidence_have_no_authority():
    unknown = _item(
        "unknown",
        _evidence("ev-unknown", source_signal="unknown", attribution="unknown"),
    )
    assistant = _item(
        "assistant",
        _evidence("ev-assistant", source_signal="typed", attribution="assistant"),
    )

    assert source_authority(unknown) == 0
    assert source_authority(assistant) == 0


def test_unasserted_capture_cannot_claim_direct_user_authority():
    item = _item(
        "spoofed-direct",
        _evidence(
            "ev-spoofed-direct",
            source_signal="typed",
            attribution="user_direct",
        ),
    )

    # A direct-user classification is a server-side mutation fact. An
    # extracted row may retain that the source was user-written, but cannot
    # promote itself to the direct-user authority tier.
    assert source_authority(item) < AUTHORITY["user_direct"]


def test_transport_and_primary_user_subject_do_not_establish_authorship():
    for signal in ("transcription", "push_to_talk", "typed", "manual", "ocr"):
        for attribution in (None, "unknown"):
            item = _item("unknown-author", _evidence("ev-unknown", source_signal=signal, attribution=attribution))
            assert source_authority(item) == 0


def test_explicit_positive_truth_review_has_owner_authority():
    item = _item("reviewed", _evidence("ev-screen", attribution="screen"))
    assert source_authority(item) == AUTHORITY["screen"]
    accepted = item.model_copy(update={"promotion": {"reviewed": True, "user_review": True}})
    assert source_authority(accepted) == AUTHORITY["user_direct"]
    pending = item.model_copy(update={"promotion": {"reviewed": False, "user_review": True}})
    assert source_authority(pending) == AUTHORITY["screen"]


def test_tombstoned_source_is_not_eligible_for_corroboration():
    item = _item(
        "deleted",
        _evidence("ev-deleted", source_state=SourceState.tombstoned),
        source_state=SourceState.tombstoned,
    )

    assert not eligible_record(item)


def test_pending_and_blocked_records_are_not_eligible_for_corroboration():
    """Rows that have not completed (or failed) provider processing must not
    drive belief admission writes, mirroring the canonical read fence."""
    assert not eligible_record(_item("pending", _evidence("ev-pending"), processing_state=ProcessingState.pending))
    assert not eligible_record(_item("blocked", _evidence("ev-blocked"), processing_state=ProcessingState.blocked))
    assert eligible_record(_item("processed", _evidence("ev-processed"), processing_state=ProcessingState.processed))


def test_memory_capture_context_preserves_original_voice_provenance():
    memory = Memory(
        content="I prefer tea",
        category=MemoryCategory.interesting,
        capture_context=MemoryCaptureContext(
            source_type="conversation",
            source_id="conv-voice-1",
            source_version="speech.v9",
            source_signal="transcription",
            independence_group="conversation-session-1",
            lineage_id="turn-12",
            attribution="user_spoken",
            quote_refs=[{"start_ms": 1200, "end_ms": 2400}],
        ),
    )

    stored = MemoryDB.from_memory(memory, "uid-1", None, False)
    evidence = stored.evidence[0]

    assert evidence.source_type == "conversation"
    assert evidence.source_id == "conv-voice-1"
    assert evidence.source_version == "speech.v9"
    assert evidence.source_signal == "transcription"
    assert evidence.independence_group == "conversation-session-1"
    assert evidence.lineage_id == "turn-12"
    assert evidence.attribution == "user_spoken"
    assert evidence.quote_refs == [{"start_ms": 1200, "end_ms": 2400}]

    projected = stored.model_dump(mode="json")
    assert source_authority(projected) == AUTHORITY["user_spoken"]
    redacted = {
        **projected,
        "evidence": [{**projected["evidence"][0], "redaction_status": "redacted"}],
    }
    assert source_authority(redacted) == AUTHORITY["unknown"]


def test_screen_capture_without_declared_family_stays_unknown_even_with_frame_id():
    memory = Memory(
        content="Browser shows a project name",
        category=MemoryCategory.interesting,
        capture_context=MemoryCaptureContext(
            source_type="screen",
            source_id="frame-123",
            source_signal="ocr",
        ),
    )

    stored = MemoryDB.from_memory(memory, "uid-1", None, False)
    evidence = stored.evidence[0]

    assert evidence.independence_group == "unknown"
    assert evidence.lineage_id is None


def test_delayed_capture_keeps_source_clock_separate_from_ingestion_time():
    from utils.memory.belief_source_policy import original_evidence_time

    original = NOW - timedelta(days=45)
    memory = Memory(
        content="I am staying in New York this month",
        category=MemoryCategory.system,
        capture_context=MemoryCaptureContext(
            source_type="screen", source_id="frame-1", source_signal="ocr", captured_at=original
        ),
    )
    captured = MemoryDB.from_memory(memory, "uid-1", None, False)
    assert captured.created_at > original
    assert captured.evidence[0].captured_at == original
    assert original_evidence_time(captured) == original
