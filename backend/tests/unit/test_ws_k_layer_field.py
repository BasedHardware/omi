"""WS-K: additive ``layer`` on MemoryDB API responses, derived from ``memory_tier``."""

import hashlib
import os
import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()


def _document_id_from_seed(seed: str) -> str:
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod.document_id_from_seed = _document_id_from_seed

from tests.unit.memory_import_isolation import (
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_k_import_isolation():
    saved = snapshot_sys_modules(["database._client", "firebase_admin", "utils.subscription", "database.users"])
    install_database_client_stub()
    install_canonical_write_runtime_stubs()
    yield
    restore_sys_modules(saved)


from models.memory_domain import tier_to_layer
from models.memories import MemoryDB
from models.product_memory import MemoryTier


def _minimal_memorydb_payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "id": "mem-test-1",
        "uid": "uid-test",
        "content": "User lives in Seattle",
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "tier",
    [MemoryTier.short_term, MemoryTier.long_term, MemoryTier.archive],
)
def test_memorydb_serializes_layer_from_memory_tier(tier):
    memory = MemoryDB(**_minimal_memorydb_payload(memory_tier=tier))
    serialized = memory.model_dump(mode="json")

    assert serialized["layer"] == tier_to_layer(tier).value
    assert serialized["memory_tier"] == tier.value


def test_layer_absent_for_default_legacy_row():
    memory = MemoryDB(**_minimal_memorydb_payload())
    serialized = memory.model_dump(mode="json")

    assert serialized["layer"] is None
    assert serialized["memory_tier"] is None


def test_legacy_firestore_dict_without_memory_tier_stays_untiered():
    memory = MemoryDB.model_validate(_minimal_memorydb_payload())
    serialized = memory.model_dump(mode="json")

    assert serialized["memory_tier"] is None
    assert serialized["layer"] is None


def test_layer_uses_real_tier_to_layer_not_hardcoded_mapping():
    for tier in MemoryTier:
        memory = MemoryDB(**_minimal_memorydb_payload(memory_tier=tier))
        assert memory.layer == tier_to_layer(tier).value
