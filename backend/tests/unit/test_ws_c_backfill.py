"""WS-C legacy → canonical backfill + archive visibility tests."""

from __future__ import annotations

import copy
from typing import Callable
import os
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    WS_C_STUB_MODULE_NAMES,
    ensure_utils_memory_packages_importable,
    install_ws_c_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_c_import_isolation():
    saved = snapshot_sys_modules(WS_C_STUB_MODULE_NAMES)
    touched = install_ws_c_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.memory.legacy_backfill import (
        _fetch_active_legacy_memories,
        backfill_user_bucketed,
        backfill_user,
        classify_legacy_backfill_bucket,
        is_active_legacy_row,
        legacy_backfill_memory_id,
        reconcile_backfill_counts,
    )

    module_globals = globals()
    module_globals["_fetch_active_legacy_memories"] = _fetch_active_legacy_memories
    module_globals["backfill_user"] = backfill_user
    module_globals["backfill_user_bucketed"] = backfill_user_bucketed
    module_globals["classify_legacy_backfill_bucket"] = classify_legacy_backfill_bucket
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
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_memory_adapter import extraction_memory_id, read_canonical_memories
from utils.memory.canonical_kg_promotion import CanonicalKgPromotionResult
from utils.memory.legacy_backfill import (
    BackfillCohortGateError,
    LegacyBackfillBucket,
    assert_canonical_cohort_for_backfill,
    both_store_canonical_duplicate_exists,
    live_extraction_memory_id_for_legacy_row,
)
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
    row = {
        "id": legacy_id,
        "uid": LEGACY_UID,
        "content": content,
        "category": MemoryCategory.work.value,
        "conversation_id": conversation_id,
        "created_at": NOW_TS,
        "updated_at": NOW_TS,
        "manually_added": False,
        "visibility": "private",
    }
    if conversation_id is not None:
        row["evidence"] = [
            {
                "evidence_id": f"ev_{legacy_id}",
                "source_id": conversation_id,
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "legacy_extractor",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": conversation_id,
                "redaction_status": "active",
                "created_at": NOW_TS,
            }
        ]
    else:
        row["evidence"] = [
            {
                "evidence_id": f"ev_{legacy_id}",
                "source_id": legacy_id,
                "source_type": "legacy_memory",
                "source_signal": "manual",
                "extractor_id": "legacy_extractor",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": legacy_id,
                "redaction_status": "active",
                "created_at": NOW_TS,
            }
        ]
    return row


def _seed_legacy_memories_in_db(db: _PromotionFakeDb, uid: str, rows: list[dict]) -> None:
    for row in rows:
        legacy_id = row["id"]
        db.docs[f"users/{uid}/memories/{legacy_id}"] = copy.deepcopy(row)


def _legacy_memory_docs_snapshot(db: _PromotionFakeDb, uid: str) -> dict[str, dict]:
    prefix = f"users/{uid}/memories/"
    return {path: copy.deepcopy(data) for path, data in db.docs.items() if path.startswith(prefix)}


def _get_memories_from_fake_db(db: _PromotionFakeDb, uid: str, limit: int = 100, offset: int = 0) -> list[dict]:
    prefix = f"users/{uid}/memories/"
    rows = [data for path, data in sorted(db.docs.items()) if path.startswith(prefix)]
    active_rows = [row for row in rows if is_active_legacy_row(row)]
    return active_rows[offset : offset + limit]


def _make_non_filtered_store(
    rows: list[dict], *, uid: str | None = None
) -> tuple[Callable[..., list[dict]], list[dict]]:
    """Return (get_non_filtered_memories_fn, active_snapshot) for immutability checks."""
    store = copy.deepcopy(rows)
    active_snapshot = copy.deepcopy([row for row in store if is_active_legacy_row(row)])
    expected_uid = uid or (rows[0].get("uid") if rows else LEGACY_UID)

    def _get_non_filtered(requested_uid, limit=100, offset=0, **kwargs):
        assert requested_uid == expected_uid
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
def _canonical_cohort_for_backfill(monkeypatch, request):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort, set_canonical_cohort

    if "test_gate_blocks_non_whitelisted_uid" in request.node.name:
        clear_canonical_cohort(monkeypatch)
        return
    set_canonical_cohort(monkeypatch, LEGACY_UID)


@pytest.fixture
def _trusted_account(monkeypatch):
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )


def test_gate_blocks_non_whitelisted_uid(_trusted_account):
    rows = [_legacy_row(legacy_id="leg-gate", content="Gated fact", conversation_id="conv-gate")]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)

    report = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert report.cohort_gated is True
    assert report.written_count == 0
    assert report.errors == ["cohort_gate: uid not in CANONICAL_MEMORY_USERS (use allow_admin_override=True to bypass)"]
    assert not any(path.startswith(f"users/{LEGACY_UID}/memory_items/") for path in db.docs)


def test_manual_note_id_fallback_enables_both_store_dedup(_trusted_account):
    content = "User keeps a daily journal"
    legacy_id = "leg-manual-note"
    rows = [_legacy_row(legacy_id=legacy_id, content=content, conversation_id=None)]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    live_id = live_extraction_memory_id_for_legacy_row(uid=LEGACY_UID, legacy_row=rows[0])
    assert live_id == extraction_memory_id(uid=LEGACY_UID, source_id=legacy_id, content=content)

    live_item = MemoryItem(
        memory_id=live_id,
        uid=LEGACY_UID,
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[
            MemoryEvidence(
                evidence_id="ev_manual_live",
                source_type="legacy_memory",
                source_id=legacy_id,
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW_TS,
        updated_at=NOW_TS,
        expires_at=None,
        ledger_commit_id="commit_manual",
        ledger_sequence=1,
        source_commit_id="commit_manual",
        source_commit_sequence=1,
        content_hash="hash-manual-live",
        account_generation=1,
    )
    db.docs[f"users/{LEGACY_UID}/memory_items/{live_id}"] = _stored_item(live_item)

    report = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert report.completed is True
    assert report.written_count == 0
    assert report.skipped_both_store_duplicate == 1
    backfill_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id=legacy_id)
    assert f"users/{LEGACY_UID}/memory_items/{backfill_id}" not in db.docs
    assert both_store_canonical_duplicate_exists(uid=LEGACY_UID, legacy_row=rows[0], db_client=db)


def test_semantic_duplicate_skipped_in_run(_trusted_account):
    conversation_id = "conv-semantic-dup"
    content = "User prefers tea over coffee"
    rows = [
        _legacy_row(legacy_id="leg-sem-1", content=content, conversation_id=conversation_id),
        _legacy_row(legacy_id="leg-sem-2", content=content, conversation_id=conversation_id),
    ]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    report = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert report.completed is True
    assert report.written_count == 1
    assert report.skipped_semantic_duplicate == 1
    item_paths = [path for path in db.docs if path.startswith(f"users/{LEGACY_UID}/memory_items/")]
    assert len(item_paths) == 1


def test_admin_override_without_ack_hard_fails(_trusted_account, monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)
    uid = "uid-orphan-override"
    rows = [_legacy_row(legacy_id="leg-orphan", content="Orphan fact", conversation_id="conv-orphan")]
    rows[0]["uid"] = uid
    get_non_filtered_fn, _ = _make_non_filtered_store(rows, uid=uid)
    db = _canonical_db_with_control(uid)

    report = backfill_user(
        uid,
        db_client=db,
        get_non_filtered_memories_fn=get_non_filtered_fn,
        allow_admin_override=True,
        acknowledge_non_canonical_uid=False,
    )

    assert report.cohort_gated is True
    assert report.written_count == 0
    assert "acknowledge_non_canonical_uid" in report.errors[0]
    assert not any(path.startswith(f"users/{uid}/memory_items/") for path in db.docs)

    with pytest.raises(BackfillCohortGateError, match="acknowledge_non_canonical_uid"):
        assert_canonical_cohort_for_backfill(uid, allow_admin_override=True, acknowledge_non_canonical_uid=False)


def test_admin_override_with_ack_writes_and_logs(_trusted_account, monkeypatch, caplog):
    import logging

    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)
    uid = "uid-orphan-override-ok"
    rows = [_legacy_row(legacy_id="leg-orphan-ok", content="Orphan ok fact", conversation_id="conv-orphan-ok")]
    rows[0]["uid"] = uid
    get_non_filtered_fn, _ = _make_non_filtered_store(rows, uid=uid)
    db = _canonical_db_with_control(uid)
    _seed_legacy_evidence(db, rows)

    with caplog.at_level(logging.WARNING, logger="utils.memory.legacy_backfill"):
        report = backfill_user(
            uid,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
            allow_admin_override=True,
            acknowledge_non_canonical_uid=True,
            operator_context="test-operator",
        )

    assert report.cohort_gated is False
    assert report.completed is True
    assert report.written_count == 1
    assert any("legacy backfill cohort override" in record.message for record in caplog.records)
    assert any(getattr(record, "uid", None) == uid for record in caplog.records)


def test_dedup_prevents_doubles_when_live_written(monkeypatch, _trusted_account):
    conversation_id = "conv-live-dup"
    content = "User prefers dark mode"
    rows = [_legacy_row(legacy_id="leg-live-dup", content=content, conversation_id=conversation_id)]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    live_id = extraction_memory_id(uid=LEGACY_UID, source_id=conversation_id, content=content)
    live_item = MemoryItem(
        memory_id=live_id,
        uid=LEGACY_UID,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[
            MemoryEvidence(
                evidence_id="ev_live_dup",
                source_type="conversation",
                source_id=conversation_id,
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW_TS,
        updated_at=NOW_TS,
        expires_at=NOW_TS + timedelta(days=30),
        ledger_commit_id="commit_live",
        ledger_sequence=1,
        source_commit_id="commit_live",
        source_commit_sequence=1,
        content_hash="hash-live-dup",
        account_generation=1,
    )
    db.docs[f"users/{LEGACY_UID}/memory_items/{live_id}"] = _stored_item(live_item)

    report = backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert report.completed is True
    assert report.written_count == 0
    assert report.skipped_both_store_duplicate == 1
    assert report.verified is True
    backfill_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id="leg-live-dup")
    assert f"users/{LEGACY_UID}/memory_items/{backfill_id}" not in db.docs
    item_paths = [path for path in db.docs if path.startswith(f"users/{LEGACY_UID}/memory_items/")]
    assert item_paths == [f"users/{LEGACY_UID}/memory_items/{live_id}"]


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
    control_path = f"users/{LEGACY_UID}/memory_state/apply_control"

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


def test_bucket_classifier_holds_noise_and_sensitive_rows():
    sensitive = _legacy_row(legacy_id="leg-sensitive", content="User API key token is stored elsewhere")
    downloads = _legacy_row(legacy_id="leg-downloads", content="Local downloads include report.pdf")
    focused = _legacy_row(legacy_id="leg-focused", content="Focused on Safari")
    manual = _legacy_row(legacy_id="leg-manual", content="User prefers fast code reviews")
    manual["manually_added"] = True
    reviewed = _legacy_row(legacy_id="leg-reviewed", content="David uses Omi Beta for daily dogfood")
    reviewed["user_review"] = True
    profile = _legacy_row(legacy_id="leg-profile", content="The user wants concise launch checklists")
    unmatched = _legacy_row(legacy_id="leg-unmatched", content="Coffee near the office was mentioned")

    assert classify_legacy_backfill_bucket(sensitive) == LegacyBackfillBucket.hold_sensitive
    assert classify_legacy_backfill_bucket(downloads) == LegacyBackfillBucket.hold_noise
    assert classify_legacy_backfill_bucket(focused) == LegacyBackfillBucket.hold_noise
    assert classify_legacy_backfill_bucket(manual) == LegacyBackfillBucket.manual_required_promotion
    assert classify_legacy_backfill_bucket(reviewed) == LegacyBackfillBucket.reviewed_long_term
    assert classify_legacy_backfill_bucket(profile) == LegacyBackfillBucket.profile_required_promotion
    assert classify_legacy_backfill_bucket(unmatched) == LegacyBackfillBucket.archive_review


def test_bucketed_inventory_dry_run_reports_counts_and_writes_nothing(_trusted_account):
    rows = [
        _legacy_row(legacy_id="leg-manual", content="User prefers concise docs", conversation_id="conv-manual"),
        _legacy_row(
            legacy_id="leg-sensitive",
            content="User password token should never migrate",
            conversation_id="conv-sensitive",
        ),
        _legacy_row(
            legacy_id="leg-noise", content="Local downloads include installer.dmg", conversation_id="conv-noise"
        ),
    ]
    rows[0]["manually_added"] = True
    get_non_filtered_fn, active_snapshot = _make_non_filtered_store(rows)
    db = _PromotionFakeDb({})

    report = backfill_user_bucketed(
        LEGACY_UID,
        dry_run=True,
        db_client=db,
        get_non_filtered_memories_fn=get_non_filtered_fn,
    )

    assert report.dry_run is True
    assert report.bucket_counts[LegacyBackfillBucket.manual_required_promotion.value] == 1
    assert report.bucket_counts[LegacyBackfillBucket.hold_sensitive.value] == 1
    assert report.bucket_counts[LegacyBackfillBucket.hold_noise.value] == 1
    assert report.intended_count == 1
    assert report.written_count == 0
    assert report.bucket_samples[LegacyBackfillBucket.manual_required_promotion.value][0]["id"] == "leg-manual"
    assert report.bucket_samples[LegacyBackfillBucket.hold_sensitive.value][0]["content"] == (
        "[redacted sensitive memory content]"
    )
    assert "password token" not in report.bucket_samples[LegacyBackfillBucket.hold_sensitive.value][0]["content"]
    assert not any(path.startswith(f"users/{LEGACY_UID}/memory_items/") for path in db.docs)
    assert get_non_filtered_fn(LEGACY_UID, limit=10, offset=0) == rows
    assert active_snapshot == rows


def test_bucketed_manual_apply_writes_required_promotion_with_legacy_timestamps(_trusted_account):
    created_at = datetime(2024, 3, 4, 5, 6, tzinfo=timezone.utc)
    updated_at = datetime(2024, 4, 5, 6, 7, tzinfo=timezone.utc)
    row = _legacy_row(
        legacy_id="leg-manual-apply", content="User prefers launch checklists", conversation_id="conv-manual"
    )
    row["manually_added"] = True
    row["created_at"] = created_at
    row["updated_at"] = updated_at
    rows = [row]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    report = backfill_user_bucketed(
        LEGACY_UID,
        bucket=LegacyBackfillBucket.manual_required_promotion,
        dry_run=False,
        db_client=db,
        get_non_filtered_memories_fn=get_non_filtered_fn,
    )

    assert report.completed is True
    assert report.verified is True
    assert report.written_count == 1
    canonical_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id=row["id"])
    stored = db.docs[f"users/{LEGACY_UID}/memory_items/{canonical_id}"]
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["user_asserted"] is True
    assert stored["captured_at"] == created_at
    assert stored["updated_at"] == updated_at
    assert stored["expires_at"] > datetime.now(timezone.utc)
    assert stored["promotion"]["required"] is True
    assert stored["promotion"]["status"] == "pending"
    assert stored["promotion"]["bucket"] == LegacyBackfillBucket.manual_required_promotion.value
    assert stored["promotion"]["legacy_memory_id"] == row["id"]


def test_bucketed_reviewed_apply_writes_long_term_with_legacy_timestamp(_trusted_account):
    created_at = datetime(2024, 5, 6, 7, 8, tzinfo=timezone.utc)
    row = _legacy_row(
        legacy_id="leg-reviewed-apply", content="David uses Omi Beta daily", conversation_id="conv-reviewed"
    )
    row["user_review"] = True
    row["created_at"] = created_at
    row["updated_at"] = created_at
    rows = [row]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    def _extract_kg(uid, item, *, db_client=None, preserve_item_updated_at=False, **_kwargs):
        assert preserve_item_updated_at is True
        db_client.document(f"users/{uid}/memory_items/{item.memory_id}").set({"kg_extracted": True}, merge=True)
        return CanonicalKgPromotionResult(attempted=True, success=True, node_count=1, edge_count=1)

    with patch("utils.memory.legacy_backfill.extract_kg_for_promoted_memory", side_effect=_extract_kg) as extract_kg:
        report = backfill_user_bucketed(
            LEGACY_UID,
            bucket=LegacyBackfillBucket.reviewed_long_term,
            dry_run=False,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
        )

    assert report.completed is True
    assert report.verified is True
    assert report.kg_extraction_failures == 0
    canonical_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id=row["id"])
    stored = db.docs[f"users/{LEGACY_UID}/memory_items/{canonical_id}"]
    assert stored["tier"] == MemoryTier.long_term.value
    assert stored["captured_at"] == created_at
    assert stored["updated_at"] == created_at
    assert stored["expires_at"] is None
    assert stored["kg_extracted"] is True
    assert stored["promotion"]["bucket"] == LegacyBackfillBucket.reviewed_long_term.value
    extract_kg.assert_called_once()


def test_bucketed_reviewed_rerun_repairs_missing_kg_on_existing_item(_trusted_account):
    row = _legacy_row(
        legacy_id="leg-reviewed-repair",
        content="User prefers memory bucket repairs",
        conversation_id="conv-reviewed",
    )
    row["user_review"] = True
    rows = [row]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    def _extract_kg(uid, item, *, db_client=None, preserve_item_updated_at=False, **_kwargs):
        assert preserve_item_updated_at is True
        db_client.document(f"users/{uid}/memory_items/{item.memory_id}").set({"kg_extracted": True}, merge=True)
        return CanonicalKgPromotionResult(attempted=True, success=True, node_count=1, edge_count=0)

    with patch("utils.memory.legacy_backfill.extract_kg_for_promoted_memory", side_effect=_extract_kg):
        first = backfill_user_bucketed(
            LEGACY_UID,
            bucket=LegacyBackfillBucket.reviewed_long_term,
            dry_run=False,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
        )

    canonical_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id=row["id"])
    item_path = f"users/{LEGACY_UID}/memory_items/{canonical_id}"
    assert first.written_count == 1
    assert db.docs[item_path]["kg_extracted"] is True

    db.docs[item_path]["kg_extracted"] = False

    with patch("utils.memory.legacy_backfill.extract_kg_for_promoted_memory", side_effect=_extract_kg) as extract_kg:
        repaired = backfill_user_bucketed(
            LEGACY_UID,
            bucket=LegacyBackfillBucket.reviewed_long_term,
            dry_run=False,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
        )

    assert repaired.written_count == 0
    assert repaired.skipped_already_present == 1
    assert repaired.kg_extraction_failures == 0
    assert db.docs[item_path]["kg_extracted"] is True
    extract_kg.assert_called_once()


def test_resume_completed_checkpoint_repairs_missing_kg_side_effect(_trusted_account):
    row = _legacy_row(legacy_id="leg-resume-kg", content="User prefers local rollout harnesses")
    rows = [row]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)

    def _extract_kg(uid, item, *, db_client=None, preserve_item_updated_at=False, **_kwargs):
        assert preserve_item_updated_at is True
        db_client.document(f"users/{uid}/memory_items/{item.memory_id}").set({"kg_extracted": True}, merge=True)
        return CanonicalKgPromotionResult(attempted=True, success=True, node_count=1, edge_count=0)

    with patch("utils.memory.legacy_backfill.extract_kg_for_promoted_memory", side_effect=_extract_kg):
        first = backfill_user(
            LEGACY_UID,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
            batch_size=1,
            resume=False,
        )

    canonical_id = legacy_backfill_memory_id(uid=LEGACY_UID, legacy_memory_id=row["id"])
    item_path = f"users/{LEGACY_UID}/memory_items/{canonical_id}"
    assert first.completed is True
    assert db.docs[item_path]["kg_extracted"] is True

    db.docs[item_path]["kg_extracted"] = False

    with patch("utils.memory.legacy_backfill.extract_kg_for_promoted_memory", side_effect=_extract_kg) as extract_kg:
        repaired = backfill_user(
            LEGACY_UID,
            db_client=db,
            get_non_filtered_memories_fn=get_non_filtered_fn,
            batch_size=1,
            resume=True,
        )

    assert repaired.resumed_from_index == 1
    assert repaired.written_count == 0
    assert repaired.kg_extraction_failures == 0
    assert db.docs[item_path]["kg_extracted"] is True
    extract_kg.assert_called_once()


def test_bucketed_hold_bucket_never_writes(_trusted_account):
    rows = [_legacy_row(legacy_id="leg-sensitive", content="User secret token should stay held")]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)

    report = backfill_user_bucketed(
        LEGACY_UID,
        bucket=LegacyBackfillBucket.hold_sensitive,
        dry_run=False,
        db_client=db,
        get_non_filtered_memories_fn=get_non_filtered_fn,
    )

    assert report.completed is True
    assert report.skipped_bucket_not_writable == 1
    assert report.written_count == 0
    assert not any(path.startswith(f"users/{LEGACY_UID}/memory_items/") for path in db.docs)


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

    control = MemoryControlState(**db.docs[f"users/{LEGACY_UID}/memory_state/apply_control"])
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

    archive_item = MemoryItem(
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
        db_client=MagicMock(),
        get_non_filtered_memories_fn=_make_paginated_non_filtered_store(page_size=page_size, pages=[page1, page2]),
        scan_page_size=page_size,
    )

    assert len(old_rows) == 1
    assert len(new_rows) == 3


def test_fetch_active_legacy_memories_passes_explicit_firestore_client():
    db_client = MagicMock(name="explicit-db-client")
    calls = []

    def _source(uid, *, limit, offset, firestore_client):
        calls.append((uid, limit, offset, firestore_client))
        return [_legacy_row(legacy_id="active-explicit", content="Active row")] if offset == 0 else []

    rows = _fetch_active_legacy_memories(
        LEGACY_UID,
        db_client=db_client,
        get_non_filtered_memories_fn=_source,
        scan_page_size=1,
    )

    assert [row["id"] for row in rows] == ["active-explicit"]
    assert calls[0][3] is db_client


def test_legacy_read_path_unaffected_for_non_canonical_uid(_trusted_account, monkeypatch):
    non_canonical_uid = "uid-non-canonical"
    rows = [_legacy_row(legacy_id="leg-legacy-read", content="Legacy only", conversation_id="conv-lr")]
    get_non_filtered_fn, _ = _make_non_filtered_store(rows)
    db = _canonical_db_with_control(LEGACY_UID)
    _seed_legacy_evidence(db, rows)
    _seed_legacy_memories_in_db(db, LEGACY_UID, rows)
    legacy_before = _legacy_memory_docs_snapshot(db, LEGACY_UID)

    backfill_user(LEGACY_UID, db_client=db, get_non_filtered_memories_fn=get_non_filtered_fn)

    assert _legacy_memory_docs_snapshot(db, LEGACY_UID) == legacy_before
    assert resolve_memory_system(non_canonical_uid, db_client=db) == MemorySystem.LEGACY

    non_canonical_rows = [
        {
            **_legacy_row(legacy_id="leg-nc-1", content="Non-canonical legacy", conversation_id="conv-nc"),
            "uid": non_canonical_uid,
        }
    ]
    _seed_legacy_memories_in_db(db, non_canonical_uid, non_canonical_rows)
    non_canonical_before = _legacy_memory_docs_snapshot(db, non_canonical_uid)

    monkeypatch.setattr(
        "utils.memory.memory_service.memories_db.get_memories",
        lambda uid, limit, offset=0, **kwargs: _get_memories_from_fake_db(db, uid, limit=limit, offset=offset),
    )
    service = MemoryService(db_client=db)
    legacy_memories = service.read(non_canonical_uid, limit=10)

    assert _legacy_memory_docs_snapshot(db, non_canonical_uid) == non_canonical_before
    assert len(legacy_memories) == 1
    assert legacy_memories[0].content == "Non-canonical legacy"


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
