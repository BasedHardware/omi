import importlib.util
import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = BACKEND_DIR / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_memory_policy_core_change_selects_inv_mem_guard():
    """Narrow memory policy PRs always pull INV-MEM guard tests."""
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    selected, reason = selector.tests_for_changed_paths(
        ["backend/utils/memory/chat_memory_adapter.py"],
        all_tests,
    )
    assert "tests/unit/test_inv_mem_1_guard.py" in selected
    assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_workflow_contract_sources_select_adjacent_tests():
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    full_run_cases = {
        "backend/database/memory_vector_repair_outbox_worker.py": "tests/unit/test_vector_repair_outbox_worker.py",
        "backend/database/projection_repair.py": "tests/unit/test_memory_ledger.py",
        "backend/main.py": "tests/unit/test_vector_repair_outbox_worker.py",
        "backend/utils/executors.py": "tests/unit/test_vector_repair_outbox_worker.py",
    }
    selected_cases = {
        "backend/utils/memory/legacy_backfill.py": "tests/unit/test_ws_c_backfill.py",
        "backend/utils/memory/canonical_memory_adapter.py": "testing/e2e/test_canonical_memory_pipeline.py",
        "backend/services/users/account_deletion.py": "tests/services/users/test_account_deletion.py",
        "backend/routers/sync.py": "tests/unit/test_sync_v2.py",
        "backend/utils/sync/pipeline.py": "tests/unit/test_sync_v2.py",
        "backend/routers/transcribe.py": "tests/unit/test_listen_pipeline.py",
        "backend/config/prerecorded_stt.py": "tests/unit/test_parakeet_prerecorded.py",
        "backend/scripts/validate-backend-runtime-env.py": "tests/unit/test_backend_runtime_env_validator.py",
        "backend/jobs/short_term_lifecycle_worker.py": "tests/unit/test_ws_b_short_term_lifecycle.py",
        "backend/utils/memory_ingestion/export_runner.py": "tests/unit/test_memory_ingestion_pipeline.py",
    }

    for source_path, expected_test in selected_cases.items():
        selected, reason = selector.tests_for_changed_paths([source_path], all_tests)
        assert expected_test in selected, source_path
        assert reason == "selected backend unit tests from changed paths and workflow contracts"

    for source_path, expected_test in full_run_cases.items():
        selected, reason = selector.tests_for_changed_paths([source_path], all_tests)
        assert expected_test in selected, source_path
        assert reason == f"{source_path} requires the full backend unit suite"
        assert selected == all_tests


def test_selector_docs_and_flat_utils_do_not_force_full_suite_via_globs():
    """Docs/AGENTS skip selection; metrics is not a FULL_RUN_GLOBS hit."""
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    for path in (
        "backend/AGENTS.md",
        "backend/docs/runbooks/resilience-dashboards.md",
        "backend/charts/monitoring/alerts/resilience.json",
    ):
        selected, reason = selector.tests_for_changed_paths([path], all_tests)
        assert selected == [], path
        assert reason == "no backend files changed", (path, reason)

    selected, reason = selector.tests_for_changed_paths(["backend/utils/metrics.py"], all_tests)
    # Not a FULL_RUN_GLOBS path; unmapped flat utils still use the fallback.
    assert reason == "backend/utils/metrics.py did not match a backend test-selection contract", reason
    assert selected == all_tests

    selected, reason = selector.tests_for_changed_paths(["backend/routers/sync.py"], all_tests)
    assert "tests/unit/test_sync_v2.py" in selected
    assert selected != all_tests
    assert reason == "selected backend unit tests from changed paths and workflow contracts"

    for path in ("backend/main.py", "backend/dependencies.py", "backend/utils/executors.py"):
        selected, reason = selector.tests_for_changed_paths([path], all_tests)
        assert selected == all_tests, path
        assert reason == f"{path} requires the full backend unit suite"


def test_unmapped_source_forces_full_suite_even_when_direct_test_changed():
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    selected, reason = selector.tests_for_changed_paths(
        [
            "backend/new_unmapped_runtime.py",
            "backend/tests/unit/test_workflow_contracts.py",
        ],
        all_tests,
    )

    assert selected == all_tests
    assert reason == "backend/new_unmapped_runtime.py did not match a backend test-selection contract"


def test_mapped_source_with_direct_test_remains_narrow():
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    selected, reason = selector.tests_for_changed_paths(
        [
            "backend/routers/sync.py",
            "backend/tests/unit/test_sync_v2.py",
        ],
        all_tests,
    )

    assert "tests/unit/test_sync_v2.py" in selected
    assert selected != all_tests
    assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_removed_test_forces_full_discovered_suite():
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    selected, reason = selector.tests_for_changed_paths(
        ["backend/tests/unit/test_removed_contract.py"],
        all_tests,
    )

    assert selected == all_tests
    assert reason == "backend/tests/unit/test_removed_contract.py was removed or is outside backend test discovery"


def test_every_external_workflow_contract_source_triggers_backend_unit_workflow():
    contracts = json.loads((BACKEND_DIR / "testing/workflow_contracts.json").read_text())
    workflow_text = (BACKEND_DIR.parent / ".github/workflows/backend-unit-tests.yml").read_text()

    external_sources = {
        source
        for workflow in contracts["workflows"]
        for source in workflow.get("sources", [])
        if not source.startswith("backend/")
    }
    missing = {
        source
        for source in external_sources
        if f"- '{source}'" not in workflow_text and f'- "{source}"' not in workflow_text
    }

    assert missing == set()


def test_pre_push_requires_backend_python_lazily():
    pre_push = (BACKEND_DIR.parent / "scripts/pre-push").read_text()
    setup_prefix = pre_push[: pre_push.index("run_step()")]

    assert "require_backend_python()" in setup_prefix
    assert 'if [[ ! -x "$BACKEND_PYTHON" ]]' not in setup_prefix
    for function_name in (
        "check_backend_runtime_env_if_needed",
        "check_backend_async_blockers_if_needed",
        "check_module_stub_pollution_if_needed",
        "check_import_time_side_effects_if_needed",
        "check_workflow_contracts_if_needed",
        "check_backend_typecheck_if_needed",
        "check_backend_unit_tests_if_needed",
        "check_openapi_contract_if_needed",
    ):
        function_start = pre_push.index(f"{function_name}()")
        function_end = pre_push.find("\n}\n", function_start)
        assert "require_backend_python" in pre_push[function_start:function_end], function_name


def test_pre_push_runs_each_named_check_phase_once():
    pre_push = (BACKEND_DIR.parent / "scripts/pre-push").read_text()
    check_calls = re.findall(r"^run_step (check_[A-Za-z0-9_]+)$", pre_push, flags=re.MULTILINE)
    duplicates = sorted({name for name in check_calls if check_calls.count(name) > 1})

    assert duplicates == []


def test_shared_change_detection_and_backend_isolation_are_ci_wired():
    repo = BACKEND_DIR.parent
    detect_changes = (repo / ".github/actions/detect-changes/action.yml").read_text()
    backend_checks = (repo / ".github/workflows/backend-checks.yml").read_text()
    desktop_checks = (repo / ".github/workflows/desktop-checks.yml").read_text()
    swift_test_suites = (repo / "desktop/macos/scripts/swift-test-suites.sh").read_text()
    pre_push = (repo / "scripts/pre-push").read_text()

    assert 'FILES=$(scripts/changed-files "$DIFF_BASE"...HEAD)' in detect_changes
    assert "has_backend_isolation_gate" in detect_changes
    assert 'scripts/changed-files "${{ needs.changes.outputs.diff_base }}"...HEAD' in desktop_checks
    assert "scan_import_time_side_effects.py" in backend_checks
    assert "check_module_stub_pollution.py" in backend_checks
    assert 'BASE_REMOTE="${PRE_PUSH_BASE_REMOTE:-origin}"' in pre_push
    assert 'scripts/changed-files "$DIFF_BASE" "$local_oid"' in pre_push
    assert "run_step check_desktop_quality_if_needed" in pre_push
    assert 'python3 "$SCRIPT_DIR/check_desktop_test_quality.py"' in swift_test_suites


def test_installed_pre_push_hook_falls_back_for_older_worktrees():
    installer = (BACKEND_DIR.parent / "scripts/install-git-hooks.sh").read_text()

    assert 'if [ -x "$ROOT/scripts/pre-push-singleflight" ]' in installer
    assert 'exec "$ROOT/scripts/pre-push" "$@"' in installer


def test_workflow_contracts_static_check_accepts_current_allowlist():
    checker = _load_script("check_workflow_contracts")
    contracts = checker.load_contracts()

    assert checker.check_no_large_tuple_results(contracts) == []


def test_workflow_contracts_static_check_rejects_unlisted_large_tuple_result(tmp_path, monkeypatch):
    checker = _load_script("check_workflow_contracts")
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    fake_source = fake_repo / "backend" / "utils" / "memory" / "new_workflow.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text("def bad_contract() -> tuple[int, int, int]:\n    return 1, 2, 3\n")

    monkeypatch.setattr(checker, "REPO_DIR", fake_repo)
    contracts = {
        "checks": {"no_large_tuple_results": {"allowlist": []}},
        "workflows": [
            {
                "risk": "high",
                "sources": ["backend/utils/memory/new_workflow.py"],
                "tests": ["tests/unit/test_new_workflow.py"],
                "checks": ["no_large_tuple_results"],
            }
        ],
    }

    errors = checker.check_no_large_tuple_results(contracts)

    assert len(errors) == 1
    assert "bad_contract returns a positional tuple with 3 fields" in errors[0]


def test_workflow_contracts_static_check_skips_workflows_without_tuple_check(tmp_path, monkeypatch):
    checker = _load_script("check_workflow_contracts")
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    fake_source = fake_repo / "backend" / "routers" / "sync.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text("def bad_contract() -> tuple[int, int, int]:\n    return 1, 2, 3\n")

    monkeypatch.setattr(checker, "REPO_DIR", fake_repo)
    contracts = {
        "checks": {"no_large_tuple_results": {"allowlist": []}},
        "workflows": [
            {
                "risk": "high",
                "sources": ["backend/routers/sync.py"],
                "tests": ["tests/unit/test_sync_v2.py"],
                "checks": [],
            }
        ],
    }

    assert checker.check_no_large_tuple_results(contracts) == []


def test_workflow_contracts_static_check_validates_all_sources_when_manifest_changes(tmp_path, monkeypatch):
    checker = _load_script("check_workflow_contracts")
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    fake_source = fake_repo / "backend" / "utils" / "memory" / "new_workflow.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text("def bad_contract() -> tuple[int, int, int]:\n    return 1, 2, 3\n")

    monkeypatch.setattr(checker, "REPO_DIR", fake_repo)
    contracts = {
        "checks": {"no_large_tuple_results": {"allowlist": []}},
        "workflows": [
            {
                "risk": "high",
                "sources": ["backend/utils/memory/new_workflow.py"],
                "tests": ["tests/unit/test_new_workflow.py"],
                "checks": ["no_large_tuple_results"],
            }
        ],
    }

    errors = checker.check_no_large_tuple_results(contracts, [checker.CONTRACTS_REL_PATH])

    assert len(errors) == 1
    assert "bad_contract returns a positional tuple with 3 fields" in errors[0]
