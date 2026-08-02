"""Safety guarantees for code-defined canonical memory cohort (WS-E)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort, set_canonical_cohort
from utils.memory.memory_system import (
    CANONICAL_MEMORY_USERS,
    MemorySystem,
    list_canonical_cohort_uids,
    resolve_memory_system,
)


@pytest.fixture(autouse=True)
def _empty_cohort(monkeypatch):
    clear_canonical_cohort(monkeypatch)
    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)


class TestCanonicalCohortFailClosed:
    def test_unknown_uid_resolves_legacy(self):
        assert resolve_memory_system("uid-not-in-cohort") == MemorySystem.LEGACY

    @pytest.mark.parametrize("uid", ["", None])
    def test_empty_uid_resolves_legacy(self, uid):
        assert resolve_memory_system(uid) == MemorySystem.LEGACY

    def test_cohort_member_resolves_canonical(self, monkeypatch):
        set_canonical_cohort(monkeypatch, "uid-test-canonical")
        assert resolve_memory_system("uid-test-canonical") == MemorySystem.CANONICAL

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

        assert resolve_memory_system("uid-memory-dogfood") == MemorySystem.LEGACY


class TestLocalFixtureCanonicalCohort:
    def test_local_harness_canonical_users_keep_seeded_fixture_on_canonical_path(self, monkeypatch):
        monkeypatch.setenv("OMI_ENV_STAGE", "local")
        monkeypatch.setenv("MEMORY_CANONICAL_USERS", "alice-auth-uid, bob-auth-uid")

        assert resolve_memory_system("alice-auth-uid") == MemorySystem.CANONICAL
        assert resolve_memory_system("bob-auth-uid") == MemorySystem.CANONICAL

    def test_fixture_environment_cannot_enroll_a_production_account(self, monkeypatch):
        monkeypatch.setenv("OMI_ENV_STAGE", "prod")
        monkeypatch.setenv("MEMORY_CANONICAL_USERS", "fixture-auth-uid")

        assert resolve_memory_system("fixture-auth-uid") == MemorySystem.LEGACY


_EXPECTED_CANONICAL_COHORT_UIDS = frozenset(
    {
        "vi7SA9ckQCe4ccobWNxlbdcNdC23",  # david.d.zhang@gmail.com
        "omi-local-emulator-chat-first-enabled-v1",  # local emulator fixture user
        "omi-dev-what-matters-now-smoke-v1",  # dev deploy-gate smoke identity (no human account)
        # Next dogfood (re-enable with CANONICAL_MEMORY_USERS):
        # "viUv7GtdoHXbK1UBCDlPuTDuPgJ2",  # kodjima33@gmail.com
    }
)


def test_production_cohort_constant_matches_approved_dogfood_uids():
    """Guardrail: canonical rollout stays intentionally limited to approved dogfood UIDs."""
    assert CANONICAL_MEMORY_USERS == _EXPECTED_CANONICAL_COHORT_UIDS
