from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.device_scope_filter import (
    device_scope_validation_error,
    filter_items_by_device_scope,
    memory_matches_device,
)
from utils.client_device import DeviceScopeRequest
from utils.memory.memory_service import DeviceScopeNotSupportedError, LegacyMemoryBackend


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


def test_filter_scoped_without_device_id_returns_empty():
    items = [_item(primary="macos_abc12345"), _item(primary="ios_deadbeef")]
    assert filter_items_by_device_scope(items, device_scope="current", client_device_id=None) == []
    assert filter_items_by_device_scope(items, device_scope="explicit", client_device_id="") == []


def test_device_scope_validation_error_messages():
    assert device_scope_validation_error("all", None) is None
    assert device_scope_validation_error("current", "macos_abc") is None
    assert "X-App-Platform" in device_scope_validation_error("current", None)
    assert "client_device_id" in device_scope_validation_error("explicit", None)


def test_legacy_backend_rejects_non_all_device_scope():
    backend = LegacyMemoryBackend()
    with pytest.raises(DeviceScopeNotSupportedError):
        backend.read(
            "uid-test",
            device_scope_request=DeviceScopeRequest(device_scope="current", client_device_id="macos_abc"),
        )
    with pytest.raises(DeviceScopeNotSupportedError):
        backend.search(
            "uid-test",
            "query",
            device_scope_request=DeviceScopeRequest(device_scope="explicit", client_device_id="ios_abcd"),
        )
