"""Tests for scheduled canonical short-term maintenance cron."""

from __future__ import annotations

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
    restore_sys_modules(saved)


ensure_utils_memory_packages_importable()

from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_for_cohort,
    should_run_canonical_short_term_maintenance_cron,
)
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.short_term_promotion import CanonicalShortTermMaintenanceReport, ShortTermPromotionReport
from tests.unit.test_ws_b_short_term_lifecycle import _canonical_db_with_control

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
CANONICAL_A = "uid-canonical-a"
CANONICAL_B = "uid-canonical-b"
LEGACY_UID = "uid-legacy-only"


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
    monkeypatch.delenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", raising=False)
    monkeypatch.delenv("MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS", raising=False)


def test_list_canonical_cohort_uids_reads_whitelist_only(monkeypatch):
    monkeypatch.setenv("MEMORY_CANONICAL_USERS", f" {CANONICAL_B}, {CANONICAL_A} ")

    assert list_canonical_cohort_uids() == [CANONICAL_A, CANONICAL_B]


def test_should_run_is_false_when_disabled_or_cohort_empty(monkeypatch):
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "true")
    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is False

    monkeypatch.setenv("MEMORY_CANONICAL_USERS", CANONICAL_A)
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "false")
    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is False


def test_should_run_is_true_when_enabled_with_cohort_on_interval_tick(monkeypatch):
    monkeypatch.setenv("MEMORY_CANONICAL_USERS", CANONICAL_A)
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_ENABLED", "true")
    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS", "1")

    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is True

    monkeypatch.setenv("MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS", "2")
    assert should_run_canonical_short_term_maintenance_cron(now=NOW) is True
    assert (
        should_run_canonical_short_term_maintenance_cron(now=datetime(2026, 6, 24, 13, 0, tzinfo=timezone.utc)) is False
    )


def test_cohort_runner_invokes_maintenance_for_each_canonical_uid_only(monkeypatch):
    monkeypatch.setenv("MEMORY_CANONICAL_USERS", f"{CANONICAL_A},{CANONICAL_B}")
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
    monkeypatch.setenv("MEMORY_CANONICAL_USERS", CANONICAL_A)
    db = _canonical_db_with_control(CANONICAL_A)

    summary = run_canonical_short_term_maintenance_for_cohort(db_client=db, now=NOW, run_id="cron-test-2")

    assert summary.user_count == 1
    assert summary.promoted_total == 0
    assert summary.skipped_users == 1
    assert summary.errors == []
