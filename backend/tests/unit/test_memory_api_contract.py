from datetime import datetime, timezone

from models.memories import MemoryDB
from models.product_memory import MemoryTier
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload, memory_write_payload
from utils.memory.memory_api_response import memory_batch_response, memory_item_response, memory_list_response


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
    memory = _memory()
    payload = memory_api_payload(
        {**memory.model_dump(), "expires_at": "2026-07-03T00:00:00Z"}, MemoryApiExposure.LEGACY
    )

    assert "memory_tier" not in payload
    assert "layer" not in payload
    assert "tier" not in payload
    assert "expires_at" not in payload
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


def test_api_payload_strips_internal_memory_fields_for_all_exposures():
    for exposure in (MemoryApiExposure.LEGACY, MemoryApiExposure.CANONICAL):
        payload = memory_api_payload(
            {
                "id": "m1",
                "content": "User is testing memory rollout",
                "memory_only": "strip-me",
                "memory_default_memory": True,
                "memory_source": "compatibility_projection",
                "archive_default_visible": True,
                "read_decision": "internal",
            },
            exposure,
        )

        assert "memory_only" not in payload
        assert "memory_default_memory" not in payload
        assert "memory_source" not in payload
        assert "archive_default_visible" not in payload
        assert "read_decision" not in payload
        assert payload["content"] == "User is testing memory rollout"


def test_memory_response_builders_apply_public_projection():
    value = {
        "id": "m1",
        "content": "User is testing memory rollout",
        "memory_tier": "short_term",
        "memory_only": "strip-me",
    }

    item = memory_item_response(value, MemoryApiExposure.LEGACY)
    listed = memory_list_response([value], MemoryApiExposure.LEGACY, headers={"X-Test": "yes"})
    batch = memory_batch_response([value], MemoryApiExposure.LEGACY, created_count=1)

    assert b"memory_tier" not in item.body
    assert b"memory_only" not in item.body
    assert listed.headers["x-test"] == "yes"
    assert b"memory_tier" not in listed.body
    assert b"memory_only" not in batch.body
    assert b"created_count" in batch.body
