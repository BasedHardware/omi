from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_selector():
    path = BACKEND_DIR / "scripts" / "select_backend_unit_tests.py"
    spec = importlib.util.spec_from_file_location("select_backend_unit_tests", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def selector_and_all_tests():
    selector = _load_selector()
    return selector, selector.discover_all_tests()


def test_firestore_index_guard_runs_for_all_serving_backend_python_changes(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    guard = set(selector.FIRESTORE_INDEX_GUARD_TESTS)
    assert guard <= set(all_tests)

    serving_changes = (
        "backend/routers/conversations.py",
        "backend/utils/conversations/filters.py",
        "backend/utils/retrieval/agentic.py",
        "backend/routers/example.py",
        "backend/utils/example.py",
        "backend/new_service_package/handlers.py",
    )
    for path in serving_changes:
        selected, _reason = selector.tests_for_changed_paths([path], all_tests)
        assert guard <= set(selected), path

    # The runner distributes sorted tests round-robin across four shards.
    selected, _reason = selector.tests_for_changed_paths([serving_changes[0]], all_tests)
    positions = [index for index, path in enumerate(selected) if path in guard]
    assert len({position % 4 for position in positions}) == 4


def test_firestore_guard_runs_for_manifest_registry_and_support_changes(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    guard = set(selector.FIRESTORE_INDEX_GUARD_TESTS)
    for path in (
        "firestore.indexes.json",
        "backend/database/firestore_index_registry.py",
        "backend/tests/support/firestore_serving_query_inventory.py",
    ):
        selected, _reason = selector.tests_for_changed_paths([path], all_tests)
        assert guard <= set(selected), path


def test_web_admin_and_manifest_changes_run_the_admin_query_contract():
    repo = BACKEND_DIR.parent
    action = (repo / ".github/actions/detect-changes/action.yml").read_text(encoding="utf-8")
    workflow = (repo / ".github/workflows/web-checks.yml").read_text(encoding="utf-8")
    assert "^web/admin/" in action
    assert r"^firestore\.indexes\.json$" in action
    assert "if: needs.changes.outputs.has_admin == 'true'" in workflow
    admin_job = workflow[workflow.index("Build Admin Dashboard") :]
    assert "working-directory: ./web/admin" in admin_job
    assert "npm test" in admin_job
