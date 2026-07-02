from datetime import datetime, timezone

from models.memories import MemoryDB
from models.product_memory import MemoryTier
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload, memory_write_payload


def _memory(memory_tier=MemoryTier.short_term):
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    return MemoryDB(
        id="m1",
        uid="uid1",
        content="User is testing memory rollout",
        category="system",
        created_at=now,
        updated_at=now,
        memory_tier=memory_tier,
    )


def test_legacy_api_payload_strips_canonical_lifecycle_fields():
    payload = memory_api_payload(_memory(), MemoryApiExposure.LEGACY)

    assert "memory_tier" not in payload
    assert "layer" not in payload
    assert "tier" not in payload
    assert payload["content"] == "User is testing memory rollout"


def test_legacy_write_payload_strips_canonical_lifecycle_fields():
    payload = memory_write_payload(_memory(MemoryTier.long_term), MemoryApiExposure.LEGACY)

    assert "memory_tier" not in payload
    assert "layer" not in payload
    assert "tier" not in payload


def test_canonical_api_payload_keeps_lifecycle_fields():
    payload = memory_api_payload(_memory(MemoryTier.long_term), MemoryApiExposure.CANONICAL)

    assert payload["memory_tier"] == MemoryTier.long_term
    assert payload["layer"] == "long_term"
