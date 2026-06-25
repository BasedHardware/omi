"""WS-I.2: canonical external writes preserve visibility + manual metadata."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memories import MemoryCategory
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem, MemoryTier
from utils.memory.canonical_memory_adapter import (
    memory_item_to_memorydb,
    read_canonical_memories,
    write_canonical_external_memory,
)
from tests.unit.memory_import_isolation import install_canonical_write_runtime_stubs
from tests.unit.test_ws_i_write_convergence import _FakeDb, _trusted_account_generation

install_canonical_write_runtime_stubs()
from database.memory_apply_store import apply_long_term_patch_firestore  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
    from utils.memory.memory_system_pin import clear_memory_system_pin

    clear_memory_system_pin()
    yield
    clear_memory_system_pin()


def test_canonical_external_write_preserves_public_visibility_and_manual_flag(monkeypatch):
    uid = "uid-canonical-meta"
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    payload = {
        "id": "mem_public_manual",
        "uid": uid,
        "content": "I prefer tea over coffee",
        "category": MemoryCategory.manual.value,
        "visibility": "public",
        "manually_added": True,
        "tags": ["user-note"],
        "created_at": now,
        "updated_at": now,
    }
    db = _FakeDb(
        {
            f"users/{uid}/memory_control/state": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
        }
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        wraps=apply_long_term_patch_firestore,
    ) as apply_mock:
        memory_id = write_canonical_external_memory(uid, payload, db_client=db)

    assert memory_id == "mem_public_manual"
    apply_mock.assert_called_once()
    patch_payload = apply_mock.call_args.kwargs["patch_payload"]
    assert patch_payload["visibility"] == "public"
    assert patch_payload["user_asserted"] is True

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert stored["visibility"] == "public"
    assert stored["user_asserted"] is True
    assert stored["promotion"]["category"] == MemoryCategory.manual.value
    assert stored["promotion"]["tags"] == ["user-note"]

    item = MemoryItem(**stored)
    mapped = memory_item_to_memorydb(item)
    assert mapped.visibility == "public"
    assert mapped.manually_added is True
    assert mapped.category == MemoryCategory.manual
    assert mapped.tags == ["user-note"]
    assert mapped.memory_tier == MemoryTier.long_term

    memories = read_canonical_memories(uid, db_client=db)
    assert len(memories) == 1
    assert memories[0].visibility == "public"
    assert memories[0].manually_added is True


def test_mcp_validate_memory_uses_canonical_store_for_canonical_cohort():
    source = (Path(__file__).resolve().parents[2] / "routers" / "mcp.py").read_text(encoding="utf-8")
    section = source.split("def _validate_mcp_memory", 1)[1].split("@router.delete", 1)[0]
    assert "MemorySystem.CANONICAL" in section
    assert "_read_canonical_memory_item" in section
    assert section.index("MemorySystem.CANONICAL") < section.index("memories_db.get_memory")
