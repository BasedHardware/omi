"""WS-I hardening: atomic source_generation bump + evidence redaction preservation."""

from __future__ import annotations

import hashlib
import inspect
import os
import sys
import types
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _document_id_from_seed(seed: str) -> str:
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()
_db_client_mod.document_id_from_seed = _document_id_from_seed
sys.modules.setdefault("database._client", _db_client_mod)

from database.v17_memory_apply_store import atomic_bump_source_generation  # noqa: E402
from models.memory_evidence import (  # noqa: E402
    ArtifactPreservationState,
    MemoryEvidence,
    ProvenanceVisibility,
    RedactionStatus,
    SourceState,
    SourceStateReason,
)
from models.v17_memory_apply import ApplyStatus, MemoryControlState  # noqa: E402
from models.v17_product_memory import MemoryItemStatus  # noqa: E402
from utils.memory.canonical_memory_adapter import (  # noqa: E402
    extraction_memory_id,
    read_canonical_memories,
    retract_conversation_sourced_memories,
    write_canonical_extraction_memory,
)

from tests.unit.test_ws_i_write_convergence import (  # noqa: E402
    _FakeDb,
    _fresh_short_term_item,
    _install_heavy_import_stubs,
    _sample_memory_payload,
    _stored_item,
    _trusted_account_generation,
)


def test_atomic_bump_uses_firestore_transaction_primitive():
    """Guarantees the bump goes through db.transaction(), not bare read-then-set."""
    source = inspect.getsource(atomic_bump_source_generation)
    assert "transaction()" in source
    assert "_atomic_bump_source_generation_transaction" in source
    apply_store_source = (Path(__file__).resolve().parents[2] / "database" / "v17_memory_apply_store.py").read_text(
        encoding="utf-8"
    )
    assert "def _atomic_bump_source_generation_transaction" in apply_store_source
    assert "control_ref.get(transaction=transaction)" in apply_store_source
    assert "transaction.set(control_ref" in apply_store_source


def test_sequential_source_generation_bumps_are_monotonic():
    uid = "uid-canonical"
    control_path = f"users/{uid}/memory_control/state"
    db = _FakeDb(
        {
            control_path: MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )

    first = atomic_bump_source_generation(uid, db_client=db)
    second = atomic_bump_source_generation(uid, db_client=db)

    assert first.source_generation == 2
    assert second.source_generation == 3
    assert db.docs[control_path]["source_generation"] == 3


def test_retract_path_bumps_source_generation_via_transaction(monkeypatch):
    """Two retracts on the same conversation advance generation without lost updates (sequential)."""
    uid = "uid-canonical"
    conversation_id = "conv-hardening"
    content = "User enjoys hiking"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]
    control_path = f"users/{uid}/memory_control/state"
    db = _FakeDb(
        {
            control_path: MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_v17_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    _install_heavy_import_stubs()

    committed_item = _fresh_short_term_item(
        uid=uid,
        memory_id=memory_id,
        conversation_id=conversation_id,
        content=content,
    )
    apply_result = SimpleNamespace(
        status=ApplyStatus.committed,
        memory_items=[committed_item],
        operation=SimpleNamespace(committed_memory_item_ids=[memory_id]),
        reason=None,
    )

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        return_value=apply_result,
    ):
        write_canonical_extraction_memory(uid, payload, db_client=db)

    first = retract_conversation_sourced_memories(uid, conversation_id, db_client=db)
    second = retract_conversation_sourced_memories(uid, conversation_id, db_client=db)

    assert first["source_generation"] == 2
    assert second["source_generation"] == 3
    assert db.docs[control_path]["source_generation"] == 3


def test_persist_evidence_preserves_redaction_status_on_reprocess_rewrite(monkeypatch):
    uid = "uid-canonical"
    conversation_id = "conv-redaction"
    content = "Sensitive fact"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    evidence_path = f"users/{uid}/memory_evidence/ev_ws_i_1"
    control_path = f"users/{uid}/memory_control/state"
    db = _FakeDb(
        {
            control_path: MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
            evidence_path: MemoryEvidence(
                evidence_id="ev_ws_i_1",
                source_type="conversation",
                source_id=conversation_id,
                source_version="v1",
                conversation_id=conversation_id,
                artifact_preservation=ArtifactPreservationState.preserved,
                redaction_status=RedactionStatus.redacted,
                provenance_visibility=ProvenanceVisibility.redacted,
                encryption_or_redaction_status=RedactionStatus.redacted,
                source_state=SourceState.tombstoned,
                source_state_reason=SourceStateReason.deleted_by_user,
            ).model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_v17_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    _install_heavy_import_stubs()

    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    committed_item = _fresh_short_term_item(
        uid=uid,
        memory_id=memory_id,
        conversation_id=conversation_id,
        content=content,
    )
    apply_result = SimpleNamespace(
        status=ApplyStatus.committed,
        memory_items=[committed_item],
        operation=SimpleNamespace(committed_memory_item_ids=[memory_id]),
        reason=None,
    )

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        return_value=apply_result,
    ):
        write_canonical_extraction_memory(uid, payload, db_client=db)

    stored = db.docs[evidence_path]
    assert stored["source_state"] == SourceState.active.value
    assert stored["redaction_status"] == RedactionStatus.redacted.value
    assert stored["provenance_visibility"] == ProvenanceVisibility.redacted.value
    assert stored["encryption_or_redaction_status"] == RedactionStatus.redacted.value


def test_persist_evidence_defaults_redaction_when_no_prior_value(monkeypatch):
    uid = "uid-canonical"
    conversation_id = "conv-default-redaction"
    content = "Plain fact"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    evidence_path = f"users/{uid}/memory_evidence/ev_ws_i_1"
    control_path = f"users/{uid}/memory_control/state"
    db = _FakeDb(
        {
            control_path: MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_v17_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    _install_heavy_import_stubs()

    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    committed_item = _fresh_short_term_item(
        uid=uid,
        memory_id=memory_id,
        conversation_id=conversation_id,
        content=content,
    )
    apply_result = SimpleNamespace(
        status=ApplyStatus.committed,
        memory_items=[committed_item],
        operation=SimpleNamespace(committed_memory_item_ids=[memory_id]),
        reason=None,
    )

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        return_value=apply_result,
    ):
        write_canonical_extraction_memory(uid, payload, db_client=db)

    stored = db.docs[evidence_path]
    assert stored["redaction_status"] == RedactionStatus.active.value
    assert stored["provenance_visibility"] == ProvenanceVisibility.visible.value
    assert stored["encryption_or_redaction_status"] == RedactionStatus.active.value
