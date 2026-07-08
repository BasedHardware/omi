"""Tests for scheduled canonical short-term maintenance cron."""

from __future__ import annotations

import os
import sys
import types
import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    restore_sys_modules,
    snapshot_sys_modules,
)

_STUB_MODULE_NAMES = (
    "database._client",
    "firebase_admin",
    "utils.subscription",
    "database.users",
    "pinecone",
    "typesense",
    "database.vector_db",
)


@pytest.fixture(scope="module", autouse=True)
def _cron_import_isolation():
    saved = snapshot_sys_modules(_STUB_MODULE_NAMES)
    for name in ("database.vector_db",):
        sys.modules.pop(name, None)
    install_database_client_stub()
    install_canonical_write_runtime_stubs()
    yield
    _clear_ws_b_runtime_modules()
    restore_sys_modules(saved)


ensure_utils_memory_packages_importable()

from models.product_memory import MemoryTier
from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_for_cohort,
    should_run_canonical_short_term_maintenance_cron,
)
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport,
    ShortTermPromotionReport,
    promotion_batch_threshold,
)
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort
from tests.unit.test_ws_b_short_term_lifecycle import (
    _clear_ws_b_runtime_modules,
    _canonical_db_with_control,
    _seed_canonical_short_term,
    _set_canonical_cohort,
)

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
CANONICAL_A = "uid-canonical-a"
CANONICAL_B = "uid-canonical-b"
LEGACY_UID = "uid-legacy-only"


def _refresh_cron_runtime() -> None:
    cron = importlib.import_module("utils.memory.canonical_short_term_maintenance_cron")
    memory_system = importlib.import_module("utils.memory.memory_system")
    short_term_promotion = importlib.import_module("utils.memory.short_term_promotion")
    cron.list_canonical_cohort_uids = memory_system.list_canonical_cohort_uids
    cron.run_canonical_short_term_maintenance = short_term_promotion.run_canonical_short_term_maintenance
    globals().update(
        {
            "run_canonical_short_term_maintenance_for_cohort": cron.run_canonical_short_term_maintenance_for_cohort,
            "should_run_canonical_short_term_maintenance_cron": cron.should_run_canonical_short_term_maintenance_cron,
            "list_canonical_cohort_uids": memory_system.list_canonical_cohort_uids,
            "CanonicalShortTermMaintenanceReport": short_term_promotion.CanonicalShortTermMaintenanceReport,
            "ShortTermPromotionReport": short_term_promotion.ShortTermPromotionReport,
            "promotion_batch_threshold": short_term_promotion.promotion_batch_threshold,
        }
    )


@pytest.fixture(autouse=True)
def _clear_canonical_cohort(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    _refresh_cron_runtime()
    clear_canonical_cohort(monkeypatch)
    monkeypatch.delenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", raising=False)
    monkeypatch.delenv("MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS", raising=False)


def test_list_canonical_cohort_uids_reads_code_cohort_only(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

    set_canonical_cohort(monkeypatch, CANONICAL_B, CANONICAL_A)

    assert list_canonical_cohort_uids() == [CANONICAL_A, CANONICAL_B]


def test_should_run_is_false_when_disabled_or_cohort_empty(monkeypatch):
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "true")
    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is False

    set_canonical_cohort(monkeypatch, CANONICAL_A)
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "false")
    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is False


def test_should_run_is_true_when_enabled_with_cohort_on_interval_tick(monkeypatch):
    set_canonical_cohort(monkeypatch, CANONICAL_A)
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "true")
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS", "1")

    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is True

    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS", "2")
    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is True
    assert (
        should_run_canonical_short_term_maintenance_cron(now=datetime(2026, 6, 24, 13, 0, tzinfo=timezone.utc)) is False
    )


def test_cohort_runner_invokes_maintenance_for_each_canonical_uid_only(monkeypatch):
    set_canonical_cohort(monkeypatch, CANONICAL_A, CANONICAL_B)
    db = _canonical_db_with_control(CANONICAL_A)

    invoked: list[str] = []

    def _recording_maintenance(uid, **kwargs):
        invoked.append(uid)
        return CanonicalShortTermMaintenanceReport(
            uid=uid,
            promotion=ShortTermPromotionReport(uid=uid, skipped_reason="promotion_not_due"),
        )

    monkeypatch.setattr(
        "utils.memory.canonical_short_term_maintenance_cron.run_canonical_short_term_maintenance",
        _recording_maintenance,
    )

    summary = run_canonical_short_term_maintenance_for_cohort(db_client=db, now=NOW, run_id="cron-test-1")

    assert invoked == [CANONICAL_A, CANONICAL_B]
    assert LEGACY_UID not in invoked
    assert summary.user_count == 2
    assert summary.run_id == "cron-test-1"
    assert summary.promoted_total == 0
    assert summary.skipped_users == 2
    assert summary.errors == []


def test_cohort_runner_uses_real_maintenance_with_fake_firestore(monkeypatch):
    set_canonical_cohort(monkeypatch, CANONICAL_A)
    db = _canonical_db_with_control(CANONICAL_A)

    summary = run_canonical_short_term_maintenance_for_cohort(db_client=db, now=NOW, run_id="cron-test-2")

    assert summary.user_count == 1
    assert summary.promoted_total == 0
    assert summary.skipped_users == 1
    assert summary.errors == []


def test_first_cron_tick_does_not_mass_promote_below_batch_threshold(monkeypatch):
    set_canonical_cohort(monkeypatch, CANONICAL_A)
    db = _canonical_db_with_control(CANONICAL_A)
    _set_canonical_cohort(monkeypatch, CANONICAL_A)
    memory_id = _seed_canonical_short_term(
        db,
        uid=CANONICAL_A,
        conversation_id="conv-cron-first-tick",
        content="Single short-term fact",
        monkeypatch=monkeypatch,
    )

    summary = run_canonical_short_term_maintenance_for_cohort(db_client=db, now=NOW, run_id="cron-first-tick")

    assert summary.promoted_total == 0
    assert summary.skipped_users == 1
    assert db.docs[f"users/{CANONICAL_A}/memory_items/{memory_id}"]["tier"] == MemoryTier.short_term.value


@pytest.fixture
def _consolidation_disabled_for_promotion_cron(monkeypatch):
    """Promotion cron tests target batch-or-daily promotion, not the consolidation LLM path."""
    monkeypatch.setenv("MEMORY_CANONICAL_CONSOLIDATION_ENABLED", "false")
    monkeypatch.setattr(
        "utils.memory.canonical_kg_promotion.extract_knowledge_from_memory",
        lambda *args, **kwargs: {"nodes": [], "edges": []},
    )


def test_first_cron_tick_promotes_at_batch_threshold(monkeypatch, _consolidation_disabled_for_promotion_cron):
    set_canonical_cohort(monkeypatch, CANONICAL_A)
    db = _canonical_db_with_control(CANONICAL_A)
    _set_canonical_cohort(monkeypatch, CANONICAL_A)
    threshold = promotion_batch_threshold()
    for index in range(threshold):
        _seed_canonical_short_term(
            db,
            uid=CANONICAL_A,
            conversation_id=f"conv-cron-batch-{index}",
            content=f"Batch fact {index}",
            monkeypatch=monkeypatch,
        )

    summary = run_canonical_short_term_maintenance_for_cohort(db_client=db, now=NOW, run_id="cron-batch")

    assert summary.promoted_total == threshold
    assert summary.skipped_users == 0


def test_daily_cadence_after_first_promotion_run(monkeypatch, _consolidation_disabled_for_promotion_cron):
    set_canonical_cohort(monkeypatch, CANONICAL_A)
    db = _canonical_db_with_control(CANONICAL_A)
    _set_canonical_cohort(monkeypatch, CANONICAL_A)
    threshold = promotion_batch_threshold()
    for index in range(threshold):
        _seed_canonical_short_term(
            db,
            uid=CANONICAL_A,
            conversation_id=f"conv-cron-daily-seed-{index}",
            content=f"Seed fact {index}",
            monkeypatch=monkeypatch,
        )

    first = run_canonical_short_term_maintenance_for_cohort(db_client=db, now=NOW, run_id="cron-daily-seed")
    assert first.promoted_total == threshold

    daily_memory_id = _seed_canonical_short_term(
        db,
        uid=CANONICAL_A,
        conversation_id="conv-cron-daily",
        content="Fact for daily promotion",
        monkeypatch=monkeypatch,
    )

    hold = run_canonical_short_term_maintenance_for_cohort(
        db_client=db,
        now=NOW + timedelta(hours=1),
        run_id="cron-daily-hold",
    )
    assert hold.promoted_total == 0
    assert db.docs[f"users/{CANONICAL_A}/memory_items/{daily_memory_id}"]["tier"] == MemoryTier.short_term.value

    daily = run_canonical_short_term_maintenance_for_cohort(
        db_client=db,
        now=NOW + timedelta(hours=25),
        run_id="cron-daily-fire",
    )
    assert daily.promoted_total == 1
    assert db.docs[f"users/{CANONICAL_A}/memory_items/{daily_memory_id}"]["tier"] == MemoryTier.long_term.value
