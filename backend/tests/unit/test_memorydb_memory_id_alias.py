"""MemoryDB ``memory_id`` alias: always mirrors ``id``, never a stored legacy value."""

from datetime import datetime, timezone

from models.memories import MemoryDB


def _minimal_payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "id": "mem_abc123",
        "uid": "uid-test",
        "content": "User lives in Seattle",
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return payload


def test_memory_id_mirrors_id_not_conversation_id():
    memory = MemoryDB(
        **_minimal_payload(
            id="mem_abc123",
            conversation_id="conv_xyz789",
        )
    )

    assert memory.memory_id == "mem_abc123"
    assert memory.conversation_id == "conv_xyz789"

    serialized = memory.model_dump(mode="json")
    assert serialized["memory_id"] == "mem_abc123"
    assert serialized["id"] == "mem_abc123"
    assert serialized["conversation_id"] == "conv_xyz789"


def test_legacy_id_only_row_sets_memory_id_from_id():
    memory = MemoryDB(**_minimal_payload(id="legacy-mem-only"))

    assert memory.memory_id == "legacy-mem-only"

    serialized = memory.model_dump(mode="json")
    assert serialized["memory_id"] == "legacy-mem-only"


def test_stored_legacy_memory_id_is_normalized_to_id():
    # Docs written while `memory_id = conversation_id` was live carry a stored
    # mismatched alias; serving it verbatim makes desktop reject the whole
    # memories list (ServerMemory throws on id != memory_id).
    memory = MemoryDB(
        **_minimal_payload(
            id="mem_primary",
            memory_id="conv_legacy_ref",
            conversation_id="conv_legacy_ref",
        )
    )

    assert memory.memory_id == "mem_primary"

    serialized = memory.model_dump(mode="json")
    assert serialized["memory_id"] == "mem_primary"
    assert serialized["conversation_id"] == "conv_legacy_ref"
