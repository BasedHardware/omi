"""MemoryDB ``memory_id`` alias: mirrors ``id`` only, not ``conversation_id``."""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()
sys.modules.setdefault("database._client", _db_client_mod)

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


def test_explicit_memory_id_is_not_overwritten():
    memory = MemoryDB(
        **_minimal_payload(
            id="mem_primary",
            memory_id="mem_explicit",
            conversation_id="conv_other",
        )
    )

    assert memory.memory_id == "mem_explicit"
