"""WS-C legacy → canonical backfill + archive visibility tests."""

from __future__ import annotations

import copy
from typing import Callable
import hashlib
import os
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

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
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_c_backfill_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_c_import_isolation():
    saved = snapshot_sys_modules(
        [
            "database._client",
            "firebase_admin",
            "utils.subscription",
            "database.users",
            "stripe",
            "pinecone",
            "database.vector_db",
            "database.memories",
        ]
    )
    install_database_client_stub()
    install_ws_c_backfill_stubs()
    from utils.memory.legacy_backfill import (
        _fetch_active_legacy_memories,
        backfill_user,
        is_active_legacy_row,
        legacy_backfill_memory_id,
        reconcile_backfill_counts,
    )

    module_globals = globals()
    module_globals["_fetch_active_legacy_memories"] = _fetch_active_legacy_memories
    module_globals["backfill_user"] = backfill_user
    module_globals["is_active_legacy_row"] = is_active_legacy_row
    module_globals["legacy_backfill_memory_id"] = legacy_backfill_memory_id
    module_globals["reconcile_backfill_counts"] = reconcile_backfill_counts
    from utils.memory.memory_service import MemoryService

    module_globals["MemoryService"] = MemoryService
    yield
    restore_sys_modules(saved)


ensure_utils_memory_packages_importable()
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memories import MemoryCategory
from models.v17_memory_apply import MemoryControlState
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.canonical_memory_adapter import read_canonical_memories
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from tests.unit.test_ws_b_short_term_lifecycle import (
    NOW,
    _PromotionFakeDb,
    _canonical_db_with_control,
    _seed_canonical_short_term,
    _set_canonical_cohort,
)
from tests.unit.test_ws_i_write_convergence import _stored_item, _trusted_account_generation

LEGACY_UID = "uid-legacy-backfill"
NOW_TS = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _legacy_row(*, legacy_id: str, content: str, conversation_id: str | None = None) -> dict:
    return {
        "id": legacy_id,
        "uid": LEGACY_UID,
        "content": content,
        "category": MemoryCategory.work.value,
        "conversation_id": conversation_id,
        "created_at": NOW_TS,
        "updated_at": NOW_TS,
        "manually_added": False,
        "visibility": "private",
        "evidence": [
            {
                "evidence_id": f"ev_{legacy_id}",
                "source_id": conversation_id or legacy_id,
                "source_type": "conversation" if conversation_id else "legacy_memory",
                "source_signal": "transcription",
                "extractor_id": "legacy_extractor",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": conversation_id or legacy_id,
                "redaction_status": "active",
                "created_at": NOW_TS,
            }
        ],
    }


def _make_non_filtered_store(rows: list[dict]) -> tuple[Callable[..., list[dict]], list[dict]]:
    """Return (get_non_filtered_memories_fn, active_snapshot) for immutability checks."""
    store = copy.deepcopy(rows)
    active_snapshot = copy.deepcopy([row for row in store if is_active_legacy_row(row)])

    def _get_non_filtered(uid, limit=100, offset=0, **kwargs):
        assert uid == LEGACY_UID
        return store[offset : offset + limit]

    return _get_non_filtered, active_snapshot


def _make_paginated_non_filtered_store(*, page_size: int, pages: list[list[dict]]) -> Callable[..., list[dict]]:
    """Raw paginated reader: each page is a full Firestore slice (no in-Python post-filter)."""
    flat_store = [row for page in pages for row in page]

    def _get_non_filtered(uid, limit=100, offset=0, **kwargs):
        assert uid == LEGACY_UID
        return flat_store[offset : offset + limit]

    return _get_non_filtered


def _seed_legacy_evidence(db: _PromotionFakeDb, rows: list[dict]) -> None:
    for row in rows:
        for evidence in row.get("evidence") or []:
            if isinstance(evidence, dict) and evidence.get("evidence_id"):
                db.docs[f"users/{LEGACY_UID}/memory_evidence/{evidence['evidence_id']}"] = {
                    "evidence_id": evidence["evidence_id"],
                    "source_type": evidence.get("source_type") or "conversation",
                    "source_id": evidence.get("source_id"),
                    "source_version": "v1",
                    "artifact_preservation": "preserved",
                    "source_state": "active",
                }


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)


@pytest.fixture
def _trusted_account(monkeypatch):
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_v17_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )


def test_backfill_copies_legacy_without_mutating_source(_trusted_account):
    rows = [
        _legacy_row(legacy_id="leg-1", content="User works at Omi", conversation_id="conv-1"),
        _legacy_row(legacy_id="leg-2", content="User lives in Seattle", conversation_id="conv-2"),
        _legacy_row(legacy_id="leg-3", content="User enjoys hiking", conversation_id="conv-3"),
    ]
    get_non_filtered_fn, legacy_snapshot = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    report = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn, batch_size=2)

    assert report.completed is True
    assert report.source_count == 3
    assert report.written_count == 3
    assert report.verified is True
    for row in rows:
        canonical_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id=row["id"])
        stored = db.docs[f"users/{LEGACY_UID}/memory_items/{canonical_id}"]
        assert stored["tier"] == MemoryTier.long_term.value
        assert stored["status"] == MemoryItemStatus.active.value
        assert stored["processing_state"] == ProcessingState.processed.value
        assert stored["content"] == row["content"]

    assert get_non_filtered_fn(LEGACY_UID, limit=100, offset=0) == rows
    assert legacy_snapshot == [row for row in rows if is_active_legacy_row(row)]


def test_backfill_idempotent_second_run(_trusted_account):
    rows = [_legacy_row(legacy_id="leg-a", content="Fact A", conversation_id="conv-a")]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    first = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)
    second = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn, resume=True)

    assert first.written_count == 1
    assert second.written_count == 0
    assert second.resumed_from_index == 1
    assert second.intended_count == 0
    assert second.verified is True
    item_paths = [path for path in db.docs if path.startswith(f"users/{LEGACY_UID}/memory_items/")]
    assert len(item_paths) == 1


def test_dry_run_writes_nothing(_trusted_account):
    rows = [_legacy_row(legacy_id="leg-dry", content="Dry run fact", conversation_id="conv-dry")]
    get_non_filtered_fn, active_snapshot = _make_non_filtered_store(rows)
    db = _PromotionFakeDb({})
    control_path = f"users/{LEGACY_UID}/memory_control/state"

    report = backfill_user(LEGACY_UID, dry_run=True, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert report.dry_run is True
    assert report.intended_count == 1
    assert report.written_count == 0
    assert report.destination_count == 0
    assert report.verified is False
    assert control_path not in db.docs
    assert not any(path.startswith(f"users/{LEGACY_UID}/memory_items/") for path in db.docs)
    assert get_non_filtered_fn(LEGACY_UID, limit=10, offset=0) == rows
    assert active_snapshot == rows


def test_resume_after_interruption(_trusted_account):
    rows = [
        _legacy_row(legacy_id="leg-r1", content="Resume one", conversation_id="conv-r1"),
        _legacy_row(legacy_id="leg-r2", content="Resume two", conversation_id="conv-r2"),
        _legacy_row(legacy_id="leg-r3", content="Resume three", conversation_id="conv-r3"),
    ]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    call_count = {"n": 0}
    real_apply = backfill_user.__globals__["apply_long_term_patch_firestore"]

    def _interrupting_apply(**kwargs):
        call_count["n"] += 1
        if call_count["n"] > 2:
            raise RuntimeError("simulated crash")
        return real_apply(**kwargs)

    with patch("utils.memory.legacy_backfill.apply_long_term_patch_firestore", side_effect=_interrupting_apply):
        interrupted = backfill_user(
            LEGACY_UID,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
            batch_size=1,
            resume=False,
        )

    assert interrupted.completed is False
    assert interrupted.errors

    control = MemoryControlState(**db.docs[f"users/{LEGACY_UID}/memory_control/state"])
    assert control.legacy_backfill_processed_count == 2

    resumed = backfill_user(
        LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn, batch_size=1, resume=True
    )
    assert resumed.resumed_from_index == 2
    assert resumed.completed is True
    assert resumed.verified is True
    item_paths = [path for path in db.docs if path.startswith(f"users/{LEGACY_UID}/memory_items/")]
    assert len(item_paths) == 3


def test_count_reconciliation_flags_missing_destination(_trusted_account):
    rows = [
        _legacy_row(legacy_id="leg-v1", content="Verify one", conversation_id="conv-v1"),
        _legacy_row(legacy_id="leg-v2", content="Verify two", conversation_id="conv-v2"),
    ]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)
    backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    missing_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id="leg-v2")
    del db.docs[f"users/{LEGACY_UID}/memory_items/{missing_id}"]

    _, destination_count, verified, discrepancy = reconcile_backfill_counts(LEGACY_UID, rows, db_client=db)
    assert destination_count == 1
    assert verified is False
    assert discrepancy == "source=2 destination=1"


def test_archive_hidden_long_term_visible_in_canonical_read(monkeypatch, _trusted_account):
    uid = "uid-archive-read"
    _set_canonical_cohort(monkeypatch, uid)
    db = _canonical_db_with_control(uid)
    long_term_id = _seed_canonical_short_term(
        db,
        uid=uid,
        conversation_id="conv-lt",
        content="Visible long-term fact",
        monkeypatch=monkeypatch,
    )
    promoted = db.docs[f"users/{uid}/memory_items/{long_term_id}"]
    promoted["tier"] = MemoryTier.long_term.value
    db.docs[f"users/{uid}/memory_items/{long_term_id}"] = promoted

    archive_item = V17MemoryItem(
        memory_id="mem_archive_hidden",
        uid=uid,
        version=1,
        tier=MemoryTier.archive,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Archived coffee preference",
        evidence=[
            MemoryEvidence(
                evidence_id="ev_archive",
                source_type="conversation",
                source_id="conv-archive",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW,
        updated_at=NOW,
        expires_at=None,
        ledger_commit_id="commit_1",
        ledger_sequence=1,
        source_commit_id="commit_1",
        source_commit_sequence=1,
        content_hash="hash-archive",
        account_generation=1,
    )
    db.docs[f"users/{uid}/memory_items/{archive_item.memory_id}"] = _stored_item(archive_item)

    memories = read_canonical_memories(uid, db_client=db)
    ids = {memory.id for memory in memories}
    assert long_term_id in ids
    assert archive_item.memory_id not in ids


def test_pagination_fetches_active_rows_across_sparse_pages(_trusted_account, monkeypatch):
    """Regression: must not stop after page 1 when few active rows survive post-filter."""
    page_size = 10
    monkeypatch.setattr("utils.memory.legacy_backfill.LEGACY_SCAN_PAGE_SIZE", page_size)
    page1: list[dict] = []
    page1.append(_legacy_row(legacy_id="active-p1", content="Active page one", conversation_id="conv-p1"))
    for index in range(1, page_size):
        rejected = _legacy_row(
            legacy_id=f"inactive-p1-{index}",
            content=f"Rejected {index}",
            conversation_id=f"conv-x-{index}",
        )
        rejected["user_review"] = False
        page1.append(rejected)

    page2 = [
        _legacy_row(legacy_id="active-p2a", content="Active page two A", conversation_id="conv-p2a"),
        _legacy_row(legacy_id="active-p2b", content="Active page two B", conversation_id="conv-p2b"),
    ]
    all_active = [row for row in page1 + page2 if is_active_legacy_row(row)]

    get_non_filtered_fn = _make_paginated_non_filtered_store(page_size=page_size, pages=[page1, page2])
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, all_active)

    report = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert report.source_count == 3
    assert report.written_count == 3
    assert report.completed is True
    assert report.verified is True
    item_paths = [path for path in db.docs if path.startswith(f"users/{LEGACY_UID}/memory_items/")]
    assert len(item_paths) == 3


def test_pagination_regression_would_miss_page_two_with_old_post_filtered_paging():
    """Document the blocker: post-filtered paging stops early when page 1 is sparse."""
    page_size = 10
    page1: list[dict] = []
    page1.append(_legacy_row(legacy_id="active-p1", content="Active page one", conversation_id="conv-p1"))
    for index in range(1, page_size):
        rejected = _legacy_row(
            legacy_id=f"inactive-p1-{index}",
            content=f"Rejected {index}",
            conversation_id=f"conv-x-{index}",
        )
        rejected["user_review"] = False
        page1.append(rejected)
    page2 = [
        _legacy_row(legacy_id="active-p2a", content="Active page two A", conversation_id="conv-p2a"),
        _legacy_row(legacy_id="active-p2b", content="Active page two B", conversation_id="conv-p2b"),
    ]
    flat = page1 + page2

    def _old_broken_post_filtered_pagination() -> list[dict]:
        """Mirrors the bug: stop when filtered page is short, not when raw Firestore page is short."""
        collected: list[dict] = []
        offset = 0
        while True:
            raw_page = flat[offset : offset + page_size]
            if not raw_page:
                break
            filtered_page = [row for row in raw_page if is_active_legacy_row(row)]
            collected.extend(filtered_page)
            if len(filtered_page) < page_size:
                break
            offset += page_size
        return collected

    old_rows = _old_broken_post_filtered_pagination()
    new_rows = _fetch_active_legacy_memories(
        LEGACY_UID,
        get_non_filtered_memories_fn=_make_paginated_non_filtered_store(page_size=page_size, pages=[page1, page2]),
        scan_page_size=page_size,
    )

    assert len(old_rows) == 1
    assert len(new_rows) == 3


def test_legacy_read_path_unaffected_for_non_canonical_uid(_trusted_account):
    rows = [_legacy_row(legacy_id="leg-legacy-read", content="Legacy only", conversation_id="conv-lr")]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)
    backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert resolve_memory_system("uid-non-canonical", db_client=db) == MemorySystem.LEGACY
    service = MemoryService(db_client=db)

    with patch("utils.memory.memory_service.memories_db.get_memories", return_value=rows):
        legacy_memories = service.read("uid-non-canonical", limit=10)

    assert len(legacy_memories) == 1
    assert legacy_memories[0].content == "Legacy only"


def test_module_never_imports_legacy_mutators():
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "utils" / "memory" / "legacy_backfill.py"
    tree = ast.parse(source.read_text())
    forbidden_exact = {"save_memories", "delete_memory", "delete_all_memories", "invalidate_memory", "create_memory"}
    forbidden_prefixes = ("delete_", "update_", "invalidate_")

    def _is_forbidden_name(name: str) -> bool:
        if name in forbidden_exact:
            return True
        return any(name.startswith(prefix) for prefix in forbidden_prefixes)

    imported: set[str] = set()
    forbidden_attrs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "database.memories":
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.Attribute) and _is_forbidden_name(node.attr):
            forbidden_attrs.append(node.attr)
    assert imported == {"get_non_filtered_memories"}
    assert not forbidden_attrs
