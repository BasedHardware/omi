import importlib.util
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = BACKEND_DIR / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_workflow_contract_sources_select_adjacent_tests():
    selector = _load_script("select_backend_unit_tests")
    all_tests = selector.discover_all_tests()

    full_run_cases = {
        "backend/database/memory_vector_repair_outbox_worker.py": "tests/unit/test_vector_repair_outbox_worker.py",
        "backend/database/projection_repair.py": "tests/unit/test_memory_ledger.py",
        "backend/utils/webhooks.py": "tests/unit/test_async_webhooks.py",
    }
    selected_cases = {
        "backend/utils/memory/legacy_backfill.py": "tests/unit/test_ws_c_backfill.py",
        "backend/services/users/account_deletion.py": "tests/services/users/test_account_deletion.py",
        "backend/routers/sync.py": "tests/unit/test_sync_v2.py",
        "backend/routers/transcribe.py": "tests/unit/test_listen_pipeline.py",
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
