"""Safety guarantees for code-defined canonical memory cohort (WS-E)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort, set_canonical_cohort
from tests.unit.memory_import_isolation import ensure_utils_memory_packages_importable

ensure_utils_memory_packages_importable()

from utils.memory.memory_system import (
    CANONICAL_MEMORY_USERS,
    MemorySystem,
    list_canonical_cohort_uids,
    resolve_memory_system,
)


class _FirestoreFake:
    def document(self, path):
        raise AssertionError(f"unexpected Firestore access: {path}")


@pytest.fixture(autouse=True)
def _empty_cohort(monkeypatch):
    clear_canonical_cohort(monkeypatch)
    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)


class TestCanonicalCohortFailClosed:
    def test_unknown_uid_resolves_legacy(self):
        assert resolve_memory_system("uid-not-in-cohort", db_client=_FirestoreFake()) == MemorySystem.LEGACY

    @pytest.mark.parametrize("uid", ["", None])
    def test_empty_uid_resolves_legacy(self, uid):
        assert resolve_memory_system(uid, db_client=_FirestoreFake()) == MemorySystem.LEGACY

    def test_cohort_member_resolves_canonical(self, monkeypatch):
        set_canonical_cohort(monkeypatch, "uid-test-canonical")
        assert resolve_memory_system("uid-test-canonical", db_client=_FirestoreFake()) == MemorySystem.CANONICAL

    def test_list_canonical_cohort_uids_reflects_code_set_only(self, monkeypatch):
        set_canonical_cohort(monkeypatch, "uid-b", "uid-a")
        assert list_canonical_cohort_uids() == ["uid-a", "uid-b"]

    def test_empty_code_cohort_is_global_legacy_kill_switch(self, monkeypatch):
        set_canonical_cohort(monkeypatch, "uid-was-canonical")
        assert resolve_memory_system("uid-was-canonical") == MemorySystem.CANONICAL
        clear_canonical_cohort(monkeypatch)
        assert resolve_memory_system("uid-was-canonical") == MemorySystem.LEGACY
        assert list_canonical_cohort_uids() == []


class TestResolveMemorySystemIgnoresMemoryFlags:
    def test_memory_rollout_flags_do_not_imply_canonical(self, monkeypatch):
        monkeypatch.setenv("MEMORY_MODE", "read")
        monkeypatch.setenv("MEMORY_ENABLED_USERS", "uid-memory-dogfood")
        db_docs = {
            "users/uid-memory-dogfood/memory_control/state": {
                "mode": "read",
                "memory_system": "canonical",
                "fallback_projection_ready": True,
            }
        }

        class _Db:
            def __init__(self, docs):
                self.docs = docs

            def document(self, path):
                from tests.unit.test_ws_l_surface_routing import _DocumentRef

                return _DocumentRef(self, path)

        assert resolve_memory_system("uid-memory-dogfood", db_client=_Db(db_docs)) == MemorySystem.LEGACY


_EXPECTED_CANONICAL_OWNER_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"  # david.d.zhang@gmail.com


def test_production_cohort_constant_contains_single_owner():
    """Guardrail: canonical rollout stays intentionally limited to one production owner."""
    assert CANONICAL_MEMORY_USERS == frozenset({_EXPECTED_CANONICAL_OWNER_UID})
