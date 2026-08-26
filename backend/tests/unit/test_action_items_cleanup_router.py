"""
Tests for preview + execute endpoints in routers/action_items_cleanup.py.

Verifies: session staging, breakdown shape, sample capping, deletion delegation,
410 on expired session, and empty-list short-circuit.

Strategy functions and Redis are replaced by in-memory fakes; the route
handlers are called directly (bypassing FastAPI DI) so auth is passed as a kwarg.
"""

import os
import re
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.rate_limit_config import RATE_POLICIES

_BACKEND = Path(__file__).resolve().parents[2]
_ROUTER_PATH = _BACKEND / "routers" / "action_items_cleanup.py"


def _grep_router(pattern: str) -> list[str]:
    with open(_ROUTER_PATH, encoding="utf-8") as f:
        return [line.strip() for line in f if re.search(pattern, line)]


@pytest.fixture(scope="module")
def router():
    """Load routers/action_items_cleanup.py fresh against faked heavy deps."""
    langchain_pkg = AutoMockModule("langchain_core")
    langchain_pkg.__path__ = []

    utils_other_pkg = AutoMockModule("utils.other")
    utils_other_pkg.__path__ = []

    action_items_db_mock = AutoMockModule("database.action_items")
    # Sane defaults so every test that doesn't care about scan-truncation
    # (i.e. all of them except TestCleanupPreviewScanTruncation) doesn't have
    # to monkeypatch these two calls just to avoid comparing MagicMocks.
    action_items_db_mock.get_open_action_items_count = lambda uid: 0
    action_items_db_mock.get_action_items_list_scan_cap = lambda: 2000

    fakes = {
        "langchain_core": langchain_pkg,
        "langchain_core.prompts": AutoMockModule("langchain_core.prompts"),
        "utils.action_item_cleanup": AutoMockModule("utils.action_item_cleanup"),
        "utils.notifications": AutoMockModule("utils.notifications"),
        "utils.other": utils_other_pkg,
        "utils.other.endpoints": AutoMockModule("utils.other.endpoints"),
        "database.action_items": action_items_db_mock,
        "database.redis_db": AutoMockModule("database.redis_db"),
        "database.vector_db": AutoMockModule("database.vector_db"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "routers.action_items_cleanup",
            os.path.join(str(_BACKEND), "routers", "action_items_cleanup.py"),
        )
        yield module


def _three_candidates(strategy: str = "stale_age"):
    return [{"id": f"t{i}", "description": f"task {i}", "strategy": strategy} for i in range(3)]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestCleanupRateLimitPolicies:
    def test_cleanup_preview_policy_exists(self):
        assert "action_items:cleanup_preview" in RATE_POLICIES
        max_req, window = RATE_POLICIES["action_items:cleanup_preview"]
        assert max_req == 15
        assert window == 3600

    def test_cleanup_execute_policy_exists(self):
        assert "action_items:cleanup_execute" in RATE_POLICIES
        max_req, window = RATE_POLICIES["action_items:cleanup_execute"]
        assert max_req == 10
        assert window == 3600


class TestCleanupRateLimitWiring:
    # Source-level check (not a live-router test): the strategy/Redis fakes in
    # the `router` fixture stub out utils.other.endpoints entirely, so this
    # verifies the actual on-disk wiring instead of the mocked module.
    def test_preview_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*action_items:cleanup_preview")
        assert len(matches) == 1, f"POST cleanup/preview must have action_items:cleanup_preview, found: {matches}"

    def test_execute_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*action_items:cleanup_execute")
        assert len(matches) == 1, f"POST cleanup/execute must have action_items:cleanup_execute, found: {matches}"


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------


class TestCleanupPreview:
    def test_returns_session_id_breakdown_and_total(self, router, monkeypatch):
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: _three_candidates())
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])

        store = {}
        monkeypatch.setattr(router, "_save_session", lambda uid, sid, data: store.update({sid: data}))

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert result.total_candidates == 3
        assert result.breakdown == {"stale_age": 3}
        assert result.session_id
        assert result.session_id in store
        assert result.expires_in_seconds == router._SESSION_TTL

    def test_session_stores_candidate_ids(self, router, monkeypatch):
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: _three_candidates())
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])

        store = {}
        monkeypatch.setattr(router, "_save_session", lambda uid, sid, data: store.update({sid: data}))

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        session_data = store[result.session_id]
        assert set(session_data["ids"]) == {"t0", "t1", "t2"}

    def test_sample_capped_per_strategy(self, router, monkeypatch):
        # 10 candidates for one strategy → sample must be ≤ _SAMPLE_PER_STRATEGY
        many = [{"id": f"t{i}", "description": f"task {i}", "strategy": "stale_age"} for i in range(10)]
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: many)
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert len(result.sample) <= router._SAMPLE_PER_STRATEGY

    def test_breakdown_only_shows_requested_strategies(self, router, monkeypatch):
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: _three_candidates())
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert set(result.breakdown.keys()) == {"stale_age"}

    def test_failed_strategy_contributes_zero_to_breakdown(self, router, monkeypatch):
        def _raise(*a, **kw):
            raise RuntimeError("simulated strategy error")

        monkeypatch.setattr(router, "candidates_stale_age", _raise)
        monkeypatch.setattr(router, "merge_candidates", lambda lists: [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert result.total_candidates == 0
        assert result.breakdown == {"stale_age": 0}

    def test_two_strategies_each_appear_in_breakdown(self, router, monkeypatch):
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: _three_candidates("stale_age"))
        monkeypatch.setattr(router, "candidates_vague", lambda *a, **kw: _three_candidates("vague"))
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] + lists[1] if lists else [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)

        req = router.CleanupPreviewRequest(strategies=["stale_age", "vague"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert set(result.breakdown.keys()) == {"stale_age", "vague"}
        assert result.breakdown["stale_age"] == 3
        assert result.breakdown["vague"] == 3

    def test_candidate_meta_includes_description_for_every_candidate(self, router, monkeypatch):
        # candidate_meta backs per-item review/exclusion in the UI, so it must carry
        # the full description for every candidate, not just the capped sample.
        many = [{"id": f"t{i}", "description": f"task {i}", "strategy": "stale_age"} for i in range(10)]
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: many)
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert len(result.candidate_meta) == 10
        assert {(m.id, m.description) for m in result.candidate_meta} == {(f"t{i}", f"task {i}") for i in range(10)}


# ---------------------------------------------------------------------------
# Scan-truncation reporting (get_action_items' 2000-item hard cap means
# strategies can silently skip tasks on large accounts — surface that instead
# of staying quiet about it)
# ---------------------------------------------------------------------------


class TestCleanupPreviewScanTruncation:
    def test_not_truncated_when_open_count_within_cap(self, router, monkeypatch):
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: _three_candidates())
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)
        monkeypatch.setattr(router.action_items_db, "get_open_action_items_count", lambda uid: 1500)
        monkeypatch.setattr(router.action_items_db, "get_action_items_list_scan_cap", lambda: 2000)

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert result.total_open_action_items == 1500
        assert result.scan_cap == 2000
        assert result.scan_truncated is False

    def test_truncated_when_open_count_exceeds_cap(self, router, monkeypatch):
        monkeypatch.setattr(router, "candidates_stale_age", lambda *a, **kw: _three_candidates())
        monkeypatch.setattr(router, "merge_candidates", lambda lists: lists[0] if lists else [])
        monkeypatch.setattr(router, "_save_session", lambda *a, **kw: None)
        monkeypatch.setattr(router.action_items_db, "get_open_action_items_count", lambda uid: 45000)
        monkeypatch.setattr(router.action_items_db, "get_action_items_list_scan_cap", lambda: 2000)

        req = router.CleanupPreviewRequest(strategies=["stale_age"])
        result = router.cleanup_preview(req, uid="uid-1")

        assert result.total_open_action_items == 45000
        assert result.scan_cap == 2000
        assert result.scan_truncated is True

    def test_truncation_fields_present_on_empty_strategies_short_circuit(self, router, monkeypatch):
        monkeypatch.setattr(router.action_items_db, "get_open_action_items_count", lambda uid: 5000)
        monkeypatch.setattr(router.action_items_db, "get_action_items_list_scan_cap", lambda: 2000)

        req = router.CleanupPreviewRequest(strategies=[])
        result = router.cleanup_preview(req, uid="uid-1")

        assert result.total_open_action_items == 5000
        assert result.scan_truncated is True


# ---------------------------------------------------------------------------
# Execute endpoint
# ---------------------------------------------------------------------------


class TestCleanupExecute:
    def test_deletes_staged_ids_and_returns_count(self, router, monkeypatch):
        ids = ["t1", "t2", "t3"]
        monkeypatch.setattr(
            router,
            "_load_session",
            lambda uid, sid: {"ids": ids, "strategies": ["stale_age"], "age_days": 90},
        )
        monkeypatch.setattr(router, "_delete_session", lambda *a, **kw: None)
        monkeypatch.setattr(
            router.action_items_db,
            "delete_action_items_batch",
            lambda uid, id_list: id_list,
        )
        monkeypatch.setattr(router, "delete_action_item_vectors_batch", lambda *a, **kw: None)
        monkeypatch.setattr(router, "send_action_items_batch_deletion_message", lambda **kw: None)

        req = router.CleanupExecuteRequest(session_id="sess-1")
        result = router.cleanup_execute(req, uid="uid-1")

        assert result.deleted_count == 3

    def test_raises_410_when_session_expired(self, router, monkeypatch):
        monkeypatch.setattr(router, "_load_session", lambda *a, **kw: None)

        req = router.CleanupExecuteRequest(session_id="expired-sess")
        with pytest.raises(HTTPException) as exc_info:
            router.cleanup_execute(req, uid="uid-1")

        assert exc_info.value.status_code == 410

    def test_empty_candidate_list_returns_zero_without_calling_delete(self, router, monkeypatch):
        monkeypatch.setattr(
            router,
            "_load_session",
            lambda uid, sid: {"ids": [], "strategies": ["stale_age"], "age_days": 90},
        )
        monkeypatch.setattr(router, "_delete_session", lambda *a, **kw: None)
        delete_called = []
        monkeypatch.setattr(
            router.action_items_db,
            "delete_action_items_batch",
            lambda *a, **kw: delete_called.append(True) or [],
        )

        req = router.CleanupExecuteRequest(session_id="sess-empty")
        result = router.cleanup_execute(req, uid="uid-1")

        assert result.deleted_count == 0
        assert delete_called == [], "delete must not be called when candidate list is empty"

    def test_vectors_and_notifications_only_on_non_empty_deleted(self, router, monkeypatch):
        ids = ["t1"]
        monkeypatch.setattr(
            router,
            "_load_session",
            lambda uid, sid: {"ids": ids, "strategies": ["stale_age"], "age_days": 90},
        )
        monkeypatch.setattr(router, "_delete_session", lambda *a, **kw: None)
        monkeypatch.setattr(
            router.action_items_db,
            "delete_action_items_batch",
            lambda uid, id_list: id_list,
        )
        vector_calls, notify_calls = [], []
        monkeypatch.setattr(
            router,
            "delete_action_item_vectors_batch",
            lambda uid, deleted_ids: vector_calls.append(deleted_ids),
        )
        monkeypatch.setattr(
            router,
            "send_action_items_batch_deletion_message",
            lambda **kw: notify_calls.append(kw),
        )

        req = router.CleanupExecuteRequest(session_id="sess-1")
        router.cleanup_execute(req, uid="uid-1")

        assert len(vector_calls) == 1
        assert len(notify_calls) == 1
        assert notify_calls[0]["user_id"] == "uid-1"

    def test_excluded_ids_are_kept_out_of_deletion(self, router, monkeypatch):
        ids = ["t1", "t2", "t3"]
        monkeypatch.setattr(
            router,
            "_load_session",
            lambda uid, sid: {"ids": ids, "strategies": ["stale_age"], "age_days": 90},
        )
        monkeypatch.setattr(router, "_delete_session", lambda *a, **kw: None)
        deleted_arg = []
        monkeypatch.setattr(
            router.action_items_db,
            "delete_action_items_batch",
            lambda uid, id_list: deleted_arg.append(id_list) or id_list,
        )
        monkeypatch.setattr(router, "delete_action_item_vectors_batch", lambda *a, **kw: None)
        monkeypatch.setattr(router, "send_action_items_batch_deletion_message", lambda **kw: None)

        req = router.CleanupExecuteRequest(session_id="sess-1", excluded_ids=["t2"])
        result = router.cleanup_execute(req, uid="uid-1")

        assert deleted_arg == [["t1", "t3"]]
        assert result.deleted_count == 2

    def test_excluding_every_candidate_deletes_nothing(self, router, monkeypatch):
        ids = ["t1", "t2"]
        monkeypatch.setattr(
            router,
            "_load_session",
            lambda uid, sid: {"ids": ids, "strategies": ["stale_age"], "age_days": 90},
        )
        monkeypatch.setattr(router, "_delete_session", lambda *a, **kw: None)
        delete_called = []
        monkeypatch.setattr(
            router.action_items_db,
            "delete_action_items_batch",
            lambda *a, **kw: delete_called.append(True) or [],
        )

        req = router.CleanupExecuteRequest(session_id="sess-1", excluded_ids=["t1", "t2"])
        result = router.cleanup_execute(req, uid="uid-1")

        assert result.deleted_count == 0
        assert delete_called == [], "delete must not be called when every candidate is excluded"
