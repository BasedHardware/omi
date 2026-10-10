import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest
import yaml

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = BACKEND_DIR / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_repo_script(name: str):
    path = BACKEND_DIR.parent / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


@pytest.fixture(scope="module")
def selector_and_all_tests():
    selector = _load_script("select_backend_unit_tests")
    return selector, selector.discover_all_tests()


def test_memory_policy_core_change_selects_inv_mem_guard(selector_and_all_tests):
    """Narrow memory policy PRs always pull INV-MEM guard tests."""
    selector, all_tests = selector_and_all_tests

    selected, reason = selector.tests_for_changed_paths(
        ["backend/utils/memory/chat_memory_adapter.py"],
        all_tests,
    )
    assert "tests/unit/test_inv_mem_1_guard.py" in selected
    assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_workflow_contract_sources_select_adjacent_tests(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    full_run_cases = {
        "backend/database/memory_vector_repair_outbox_worker.py": "tests/unit/test_vector_repair_outbox_worker.py",
        "backend/database/projection_repair.py": "tests/unit/test_memory_ledger.py",
        "backend/main.py": "tests/unit/test_vector_repair_outbox_worker.py",
        "backend/utils/executors.py": "tests/unit/test_vector_repair_outbox_worker.py",
    }
    selected_cases = {
        "backend/utils/memory/legacy_backfill.py": "tests/unit/test_ws_c_backfill.py",
        "backend/utils/memory/canonical_memory_adapter.py": "testing/e2e/test_canonical_memory_pipeline.py",
        "backend/routers/conversations.py": "tests/unit/test_conversation_lifecycle_contract.py",
        "backend/services/users/account_deletion.py": "tests/services/users/test_account_deletion.py",
        "backend/routers/sync.py": "tests/unit/test_sync_v2.py",
        "backend/utils/sync/pipeline.py": "tests/unit/test_sync_v2.py",
        "backend/routers/transcribe.py": "tests/unit/test_listen_pipeline.py",
        "backend/config/prerecorded_stt.py": "tests/unit/test_parakeet_prerecorded.py",
        "backend/config/plan_catalog.json": "tests/unit/test_plan_catalog_contract.py",
        "backend/scripts/generate_plan_catalog.py": "tests/unit/test_plan_catalog_contract.py",
        "backend/scripts/validate-backend-runtime-env.py": "tests/unit/test_backend_runtime_env_validator.py",
        "backend/scripts/runtime_env_capability_contracts.py": "tests/unit/test_pusher_static_capability_admission.py",
        "backend/scripts/firebase_release_probe_token.py": "tests/unit/test_firebase_release_probe_token.py",
        "scripts/voice-provider-probe.sh": "tests/unit/test_voice_provider_probe.py",
        ".github/workflows/desktop_backend_auto_dev.yml": "tests/unit/test_voice_provider_probe.py",
        "backend/charts/pusher/templates/deployment.yaml": "tests/unit/test_rendered_deployment_contract.py",
        ".github/workflows/gcp_backend_pusher.yml": "tests/unit/test_verify_pusher_rollout_budget.py",
        "backend/scripts/pusher_prod_canary.py": "tests/unit/test_pusher_deployment_control_workflow.py",
        "backend/scripts/verify_pusher_rollout_budget.py": "tests/unit/test_verify_pusher_rollout_budget.py",
        "backend/scripts/verify_pusher_live_alert_route.py": "tests/unit/test_verify_pusher_live_alert_route.py",
        "backend/charts/monitoring/live-alert-gate.json": "tests/unit/test_verify_pusher_live_alert_route.py",
        "backend/scripts/validate_rendered_deployment_contract.py": "tests/unit/test_rendered_deployment_contract.py",
        ".github/workflows/gcp_backend_auto_dev.yml": "tests/unit/test_llm_gateway_deploy_contract.py",
        ".github/workflows/gcp_llm_gateway.yml": "tests/unit/test_preflight_cloud_run_deploy.py",
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


def test_workflow_contract_directory_glob_selects_nested_chart_test(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    selected, reason = selector.tests_for_changed_paths(
        ["backend/charts/pusher/templates/deployment.yaml"],
        all_tests,
    )

    assert "tests/unit/test_rendered_deployment_contract.py" in selected
    assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_selector_docs_and_flat_utils_do_not_force_full_suite_via_globs(selector_and_all_tests):
    """Docs/AGENTS skip selection; metrics is not a FULL_RUN_GLOBS hit."""
    selector, all_tests = selector_and_all_tests

    for path in (
        "backend/AGENTS.md",
        "backend/docs/runbooks/resilience-dashboards.md",
    ):
        selected, reason = selector.tests_for_changed_paths([path], all_tests)
        assert selected == [], path
        assert reason == "no backend files changed", (path, reason)

    # Monitoring telemetry contract sources (#9587) select monitoring unit tests.
    selected, reason = selector.tests_for_changed_paths(
        ["backend/charts/monitoring/alerts/resilience.json"],
        all_tests,
    )
    assert "tests/unit/test_monitoring_telemetry_contract.py" in selected
    assert "tests/unit/test_monitoring_alert_rule_contract.py" in selected
    assert "tests/unit/test_journey_observability.py" in selected
    assert "tests/unit/test_verify_pusher_live_alert_route.py" in selected
    assert reason == "selected backend unit tests from changed paths and workflow contracts"

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


def test_unmapped_source_forces_full_suite_even_when_direct_test_changed(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    selected, reason = selector.tests_for_changed_paths(
        [
            "backend/new_unmapped_runtime.py",
            "backend/tests/unit/test_workflow_contracts.py",
        ],
        all_tests,
    )

    assert selected == all_tests
    assert reason == "backend/new_unmapped_runtime.py did not match a backend test-selection contract"


def test_mapped_source_with_direct_test_remains_narrow(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

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


def test_location_context_paths_select_their_focused_privacy_regressions(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    for source_path in (
        "backend/models/geolocation.py",
        "backend/models/users.py",
        "backend/database/users.py",
        "backend/routers/developer.py",
        "backend/utils/retrieval/agentic.py",
        "backend/routers/users.py",
    ):
        selected, reason = selector.tests_for_changed_paths([source_path], all_tests)
        assert "tests/unit/test_location_context_consent.py" in selected, source_path
        assert "tests/unit/test_chat_async_offload.py" in selected, source_path
        assert selected != all_tests, source_path
        assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_csat_surface_paths_select_their_focused_contracts(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    for source_path in ("backend/database/csat.py", "backend/routers/csat.py"):
        selected, reason = selector.tests_for_changed_paths([source_path], all_tests)
        assert "tests/unit/test_csat.py" in selected, source_path
        assert "tests/unit/test_desktop_rest_inventory.py" in selected, source_path
        assert selected != all_tests, source_path
        assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_query_guard_paths_select_firestore_shape_guard_tests(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    guard_tests = {
        "tests/unit/test_firestore_query_shapes.py",
        "tests/unit/test_firestore_index_rules.py",
        "tests/unit/test_firestore_shape_recorder.py",
    }
    for source_path in ("backend/database/users.py", "backend/database/csat.py"):
        selected, reason = selector.tests_for_changed_paths([source_path], all_tests)
        assert guard_tests <= set(selected), source_path
        assert selected != all_tests, source_path
        assert reason == "selected backend unit tests from changed paths and workflow contracts"
    # A manifest-only change must also run the shape guard: an index added to
    # serve a ledgered gap has to prune the now-stale ledger row before merge,
    # not fail on main after the change lands (Codex review r4144046082).
    selected, reason = selector.tests_for_changed_paths(["firestore.indexes.json"], all_tests)
    assert "tests/unit/test_firestore_query_shapes.py" in selected
    assert selected != all_tests
    assert reason == "selected backend unit tests from changed paths and workflow contracts"


def test_regular_conversations_path_remains_full_run(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    selected, reason = selector.tests_for_changed_paths(["backend/database/conversations.py"], all_tests)
    assert selected == all_tests
    assert reason == "backend/database/conversations.py requires the full backend unit suite"


def test_removed_test_forces_full_discovered_suite(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests

    selected, reason = selector.tests_for_changed_paths(
        ["backend/tests/unit/test_removed_contract.py"],
        all_tests,
    )

    assert selected == all_tests
    assert reason == "backend/tests/unit/test_removed_contract.py was removed or is outside backend test discovery"


def test_every_external_workflow_contract_source_triggers_backend_unit_workflow():
    contracts = json.loads((BACKEND_DIR / "testing/workflow_contracts.json").read_text(encoding="utf-8"))
    workflow_text = (BACKEND_DIR.parent / ".github/workflows/backend-unit-tests.yml").read_text(encoding="utf-8")

    external_sources = {
        source
        for workflow in contracts["workflows"]
        for source in workflow.get("sources", [])
        if not source.startswith("backend/")
    }
    triggers = re.findall(r"^\s*-\s+['\"]([^'\"]+)['\"]\s*$", workflow_text, flags=re.MULTILINE)
    missing = {
        source
        for source in external_sources
        if not any(
            source == trigger or ("*" not in source and PurePosixPath(source).match(trigger)) for trigger in triggers
        )
    }

    assert missing == set()


def test_backend_unit_ci_runner_stays_in_ci_while_pre_push_keeps_its_budget():
    """#9440: CI is full-suite authority; push latency must remain bounded."""
    repo = BACKEND_DIR.parent
    workflow_text = (repo / ".github/workflows/backend-unit-tests.yml").read_text(encoding="utf-8")
    pre_push = (repo / "scripts/pre-push").read_text(encoding="utf-8")
    runner = (BACKEND_DIR / "scripts/run-unit-ci.sh").read_text(encoding="utf-8")

    assert "scripts/run-unit-ci.sh --changed-files" in workflow_text
    assert "scripts/run-unit-ci.sh --all" in workflow_text
    assert "backend/scripts/run-unit-ci.sh" not in pre_push
    assert "backend/scripts/needs-typecheck.sh" in pre_push
    # The runner parses its argv into named variables before this call; the
    # pin is that the changed-files diff still feeds the typecheck boundary.
    assert '"$SCRIPT_DIR/needs-typecheck.sh" "$changed_files_arg"' in runner
    assert 'PRE_PUSH_MAX_BACKEND_UNIT_TEST_FILES:-40' in pre_push
    assert "pre-push is intentionally a bounded local-feedback gate" in pre_push
    assert 'BACKEND_FAST_UNIT_WARN_SECONDS="0.1"' in runner
    assert 'BACKEND_FAST_UNIT_FAIL_SECONDS="1.0"' in runner


def test_expensive_pr_contracts_cancel_only_superseded_pull_request_runs():
    repo = BACKEND_DIR.parent
    workflows = {
        "backend-unit-tests.yml": "backend-unit-tests-",
        "openapi-contract.yml": "openapi-contract-",
    }

    for filename, group_prefix in workflows.items():
        workflow = (repo / ".github/workflows" / filename).read_text(encoding="utf-8")
        assert "concurrency:" in workflow
        assert f"group: {group_prefix}${{{{ github.event_name == 'pull_request'" in workflow
        assert "format('pr-{0}', github.event.pull_request.number)" in workflow
        assert "format('run-{0}', github.run_id)" in workflow
        assert "cancel-in-progress: true" in workflow


def test_backend_unit_suite_is_sharded_with_a_literal_gate_and_budget():
    """The suite is per-file pytest process bound; CI fans it out, guarded.

    Measured 2026-09-10 (run 34430370667): 1126 files each in its own pytest
    session cost 19m18s of a 21m53s run while only two files exceeded 4.5s of
    test time, and sharing processes across files is blocked by dense
    sys.modules contamination (see the BACKEND_PYTEST_PARALLEL_SESSION
    measurement in backend/test.sh). The workflow therefore runs the SAME
    selection as four parallel shard jobs whose interleaved slices partition
    the sorted file list exactly (union = full selection), plus a concurrent
    guardrails job, and publishes the verdict through a literal-named gate so
    the required check surface never changes. Each shard carries a wall-clock
    regression budget; duration drift fails the run instead of publishing
    green.
    """
    repo = BACKEND_DIR.parent
    workflow = (repo / ".github/workflows/backend-unit-tests.yml").read_text(encoding="utf-8")
    runner = (BACKEND_DIR / "scripts/run-unit-ci.sh").read_text(encoding="utf-8")

    assert "shard: [1, 2, 3, 4]" in workflow
    assert "--shard 4/${{ matrix.shard }}" in workflow
    assert 'BACKEND_UNIT_STEP_BUDGET_SECONDS: "720"' in workflow
    assert "backend unit shard wall: ${elapsed}s" in workflow
    # The gate keeps the exact check name and fails closed on any shard or
    # guardrail result that is not a plain success.
    assert "name: Backend unit suite" in workflow
    assert "needs: [ci-tier, backend-unit-shard, backend-unit-guardrails]" in workflow
    assert 'if [ "$SHARD_RESULT" != "success" ]' in workflow
    # Guardrails are required on internal PRs, main, and ci:full forks; an
    # unlabeled fork must report them skipped, never silently green.
    assert 'guardrails_required=success' in workflow
    assert 'if [ "$GUARDRAILS_RESULT" != "$guardrails_required" ]' in workflow
    assert '::notice title=Heavy CI deferred::' in workflow
    assert 'echo "Heavy CI deferred: $notice" >> "$GITHUB_STEP_SUMMARY"' in workflow
    assert 'guardrails_required=skipped' in workflow
    # The runner slices the deterministic selection round-robin with the
    # one-based mapping (line i runs in shard ((i - 1) % total) + 1, so
    # shard labels match the files they carry); `index` is an awk builtin,
    # so the shard variable must be named anything else.
    assert "(NR - 1) % total == shard - 1" in runner
    assert "awk -v index=" not in runner


def test_backend_test_runner_defaults_python_to_utf8():
    runner = (BACKEND_DIR / "test.sh").read_text(encoding="utf-8")
    utf8_export = 'export PYTHONUTF8="${PYTHONUTF8:-1}"'

    assert utf8_export in runner
    assert runner.index(utf8_export) < runner.index('PYTHON_BIN="${PYTHON:-}"')


def test_pre_push_requires_backend_python_lazily():
    pre_push = (BACKEND_DIR.parent / "scripts/pre-push").read_text(encoding="utf-8")
    setup_prefix = pre_push[: pre_push.index("run_step()")]

    assert "require_backend_python()" in setup_prefix
    assert 'if [[ ! -x "$BACKEND_PYTHON" ]]' not in setup_prefix
    for function_name in (
        "check_backend_runtime_env_if_needed",
        "check_backend_typecheck_if_needed",
        "check_backend_unit_tests_if_needed",
        "check_openapi_contract_if_needed",
    ):
        function_start = pre_push.index(f"{function_name}()")
        function_end = pre_push.find("\n}\n", function_start)
        assert "require_backend_python" in pre_push[function_start:function_end], function_name


def test_pre_push_selects_release_guard_and_focused_test_for_release_contract_changes():
    """The fast lane catches qualification guard drift without cloning the backend suite."""
    pre_push = (BACKEND_DIR.parent / "scripts/pre-push").read_text(encoding="utf-8")
    function_start = pre_push.index("check_release_process_guards_if_needed()")
    function_end = pre_push.index("\n}\n", function_start)
    guard = pre_push[function_start:function_end]

    assert ".github/scripts/check-release-process-guards.py" in guard
    assert "scripts/run-release-process-guards.sh" in guard
    assert "tests/unit/test_desktop_release_scripts.py" in guard
    assert "bash scripts/run-release-process-guards.sh" in guard
    assert "BACKEND_UNIT_TEST_FILE_LIST" in guard


def test_pre_push_runs_each_named_check_phase_once():
    pre_push = (BACKEND_DIR.parent / "scripts/pre-push").read_text(encoding="utf-8")
    check_calls = re.findall(r"^run_step (check_[A-Za-z0-9_]+)$", pre_push, flags=re.MULTILINE)
    duplicates = sorted({name for name in check_calls if check_calls.count(name) > 1})

    assert duplicates == []


def test_shared_change_detection_and_backend_isolation_are_ci_wired():
    repo = BACKEND_DIR.parent
    detect_changes = (repo / ".github/actions/detect-changes/action.yml").read_text(encoding="utf-8")
    manifest = (repo / ".github/checks-manifest.yaml").read_text(encoding="utf-8")
    backend_checks = (repo / ".github/workflows/backend-checks.yml").read_text(encoding="utf-8")
    repo_checks = (repo / ".github/workflows/repo-checks.yml").read_text(encoding="utf-8")
    desktop_checks = (repo / ".github/workflows/desktop-checks.yml").read_text(encoding="utf-8")

    swift_test_suites = (repo / "desktop/macos/scripts/swift-test-suites.sh").read_text(encoding="utf-8")
    pre_push = (repo / "scripts/pre-push").read_text(encoding="utf-8")

    assert 'FILES=$(scripts/changed-files "$DIFF_BASE"...HEAD)' in detect_changes
    assert "has_backend_isolation_gate" in detect_changes
    assert "has_desktop_rust" not in desktop_checks
    assert "scan_import_time_side_effects.py" in manifest
    assert "check_module_stub_pollution.py" in manifest
    assert '"--check-allowlist-monotonic", "{base}"' in manifest
    assert "backend/dependencies.py" in manifest
    assert "unmanaged_thread_offload" in manifest
    assert "scan_import_time_side_effects.py" not in backend_checks
    assert "check_module_stub_pollution.py" not in backend_checks
    assert "run_checks.py --lane ci" in repo_checks
    assert 'BASE_REMOTE="${PRE_PUSH_BASE_REMOTE:-origin}"' in pre_push
    assert 'scripts/changed-files "$DIFF_BASE" "$local_oid"' in pre_push
    assert "scripts/pr-preflight --lane local" in pre_push
    assert "backend/scripts/run-unit-ci.sh" not in pre_push
    assert 'PRE_PUSH_MAX_BACKEND_UNIT_TEST_FILES:-40' in pre_push
    assert "scan_import_time_side_effects.py" not in pre_push
    assert "check_module_stub_pollution.py" not in pre_push
    assert "check_desktop_test_quality.py" in manifest
    assert 'python3 "$SCRIPT_DIR/check_desktop_test_quality.py"' in swift_test_suites
    assert 'if [ -z "${OMI_SWIFT_TEST_DISCOVERY_ROOT:-}" ]; then' in swift_test_suites


def test_backend_static_contract_job_uses_the_pinned_backend_environment():
    repo = BACKEND_DIR.parent
    workflow = (repo / '.github/workflows/backend-checks.yml').read_text(encoding='utf-8')
    pre_deploy = (BACKEND_DIR / 'scripts/pre-deploy-check.sh').read_text(encoding='utf-8')

    assert 'uses: actions/setup-python@v6' in workflow
    assert 'uses: astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84' in workflow
    assert 'uv pip sync pylock.toml --system' in workflow
    assert 'backend/scripts/pre-deploy-check.sh' in workflow
    assert 'python3 -m pip install' not in pre_deploy
    assert "python3 -c 'import pytest, yaml'" in pre_deploy


def _github_jobs(workflow_text: str) -> dict[str, str]:
    """Map top-level GitHub Actions job ids to their YAML bodies."""
    match = re.search(r"^jobs:\n", workflow_text, re.MULTILINE)
    assert match is not None
    body = workflow_text[match.end() :]
    tokens = re.split(r"^(  [A-Za-z0-9_-]+:)\n", body, flags=re.MULTILINE)
    jobs: dict[str, str] = {}
    index = 1
    while index < len(tokens):
        job_id = tokens[index].strip()[:-1]
        job_body = tokens[index + 1] if index + 1 < len(tokens) else ""
        jobs[job_id] = job_body
        index += 2
    return jobs


def test_mobile_generated_files_only_run_for_codegen_or_localization_changes():
    repo = BACKEND_DIR.parent
    mobile_checks = (repo / '.github/workflows/mobile-app-checks.yml').read_text(encoding='utf-8')
    jobs = _github_jobs(mobile_checks)
    generated = jobs["generated-files"]
    android = jobs["android-compile-smoke"]
    changes = jobs["changes"]
    resolver = _load_repo_script("pre_push_ci_prediction")

    regular_dart = "app/lib/utils/date_formats.dart"
    regular_plan = resolver.resolve_impact(
        [regular_dart],
        read_text=lambda path: {regular_dart: "class DateFormats {}"}.get(path),
    )
    regular_outputs = resolver.github_outputs(regular_plan)
    assert regular_outputs["has_app_codegen"] == "false"
    assert regular_outputs["has_app_l10n"] == "false"
    assert regular_outputs["has_flutter_generated"] == "false"

    asset_plan = resolver.resolve_impact(["app/assets/icons/omi.png"])
    asset_outputs = resolver.github_outputs(asset_plan)
    assert asset_outputs["has_app_codegen"] == "true"
    assert asset_outputs["has_flutter_generated"] == "true"

    assert "needs.changes.outputs.has_flutter_generated == 'true'" in generated
    assert "if: needs.changes.outputs.has_app_codegen == 'true'" in generated
    assert "if: needs.changes.outputs.has_app_l10n == 'true'" in generated
    assert 'fetch-depth: 1' in generated
    assert 'fetch-depth: 1' in android
    assert 'fetch-depth: 0' in changes


def test_mobile_jobs_share_the_repository_flutter_toolchain_pin():
    repo = BACKEND_DIR.parent
    mobile_checks = (repo / ".github/workflows/mobile-app-checks.yml").read_text(encoding="utf-8")
    repo_checks = (repo / ".github/workflows/repo-checks.yml").read_text(encoding="utf-8")

    pinned_version = re.search(r"flutter-version:\s*([^\s#]+)", repo_checks)
    assert pinned_version is not None
    pinned = f"flutter-version: {pinned_version.group(1)}"
    # Every Flutter-installing job must use the repo pin. A new job that
    # installs Flutter without this pin (or a mismatched version) fails
    # because the two counts diverge. The floor is the historical four
    # (generated-files, analyze-and-test, journeys-hermetic,
    # android-compile-smoke); android-unit-tests, dart-tests-kiritimati, and
    # ios-compile-check add three more.
    action_count = mobile_checks.count("uses: subosito/flutter-action")
    assert action_count == mobile_checks.count(pinned)
    assert action_count >= 6


def test_backend_hermetic_fork_deferral_stays_neutral_and_requires_skipped_jobs():
    repo = BACKEND_DIR.parent
    workflow = (repo / ".github/workflows/backend-hermetic-e2e.yml").read_text(encoding="utf-8")
    gate = workflow.split("  merge-gate:\n", 1)[1].split("  post-merge-failure-issues:\n", 1)[0]

    assert "::notice title=Heavy CI deferred::$notice" in gate
    assert 'echo "Heavy CI deferred: $notice" >> "$GITHUB_STEP_SUMMARY"' in gate
    assert "required_result=skipped" in gate
    assert '[[ "$HERMETIC_E2E_RESULT" == "$required_result" ]]' in gate
    assert '[[ "$LISTEN_PUSHER_RESULT" == "$listen_required" ]]' in gate
    assert '[[ "$SYNC_CLOUD_TASKS_RESULT" == "$sync_required" ]]' in gate


def test_python_cli_fork_deferral_uses_the_standard_notice():
    # #19729 standardized the heavy-CI deferral surface across the ci-tier workflows;
    # python-cli-ci kept the pre-refactor summary line with no annotation.
    repo = BACKEND_DIR.parent
    workflow = (repo / ".github/workflows/python-cli-ci.yml").read_text(encoding="utf-8")

    assert "::notice title=Heavy CI deferred::$notice" in workflow
    assert 'echo "Heavy CI deferred: $notice" >> "$GITHUB_STEP_SUMMARY"' in workflow
    assert "deferred: fork PR — a maintainer adds label ci:full, then Re-run all jobs" not in workflow


def test_mobile_android_compile_smoke_uploads_debug_apk_and_runs_jvm_tests_in_parallel():
    repo = BACKEND_DIR.parent
    mobile_checks = (repo / ".github/workflows/mobile-app-checks.yml").read_text(encoding="utf-8")
    jobs = _github_jobs(mobile_checks)

    android = jobs["android-compile-smoke"]
    unit_tests = jobs["android-unit-tests"]

    assert "name: Android Compile Smoke" in mobile_checks
    assert "name: Android JVM Unit Tests" in mobile_checks
    assert "needs: changes" in android
    assert "needs: changes" in unit_tests
    assert "needs: android-compile-smoke" not in unit_tests
    assert "needs: android-unit-tests" not in android
    assert "has_app_compile_smoke" in android
    assert "has_app_compile_smoke" in unit_tests

    # PRs and main both stay arm64-only (disk; extra ABIs OOM'd ubuntu-latest).
    assert "flutter build apk --debug --flavor dev --target-platform android-arm64" in android
    android_run_lines = {line.strip() for line in android.splitlines()}
    assert "flutter build apk --debug --flavor dev" not in android_run_lines
    assert "GITHUB_EVENT_NAME" not in android
    assert "testDevDebugUnitTest" not in android
    assert "actions/upload-artifact@v7" in android
    assert "app-dev-debug-${{ github.event.pull_request.head.sha || github.sha }}" in android
    assert "app/build/app/outputs/flutter-apk/app-dev-debug.apk" in android
    assert "retention-days: 5" in android
    assert "${{ secrets." not in android
    # Compile-smoke is the wall: restore-only so main does not pay Gradle
    # save+cleanup after the APK, and so it does not race the JVM writer
    # for the same content keys (runs 35256814704 / 35268313733).
    assert "cache-read-only: true" in android
    assert "cache-read-only: ${{ github.ref != 'refs/heads/main' }}" not in android

    # Size report is a zip breakdown of the debug APK this job already built.
    # --analyze-size would need a second release compile; this is never a gate.
    assert "report_debug_apk_size.py" in android
    assert "GITHUB_STEP_SUMMARY" in android
    assert "apk-size-${{ github.event.pull_request.head.sha || github.sha }}" in android
    assert not any("--analyze-size" in line and not line.lstrip().startswith("#") for line in android.splitlines())
    assert "github-script" not in android
    assert "create-or-update-comment" not in android
    assert "${{ secrets." not in android
    assert "THRESHOLD" not in (repo / ".github/scripts/report_debug_apk_size.py").read_text(encoding="utf-8")

    assert "./gradlew :app:testDevDebugUnitTest -Ptarget-platform=android-arm64" in unit_tests
    unit_run_lines = {line.strip() for line in unit_tests.splitlines()}
    assert "flutter build apk --debug --flavor dev --target-platform android-arm64" not in unit_run_lines
    assert "uses: gradle/actions/setup-gradle@v6" in android
    assert "uses: gradle/actions/setup-gradle@v6" in unit_tests
    # Configuration cache broke AGP 8.11.1 + Kotlin 2.2.20 in CI
    # (run 35207698338): warn mode does not downgrade a cache-state
    # serialization failure. Savings stay in the Gradle User Home cache
    # and the parallel JVM job.
    assert "org.gradle.configuration-cache" not in android
    assert "org.gradle.configuration-cache" not in unit_tests
    assert "--config-only" not in android
    assert "flutter build apk --debug --flavor dev --target-platform android-arm64 --config-only" in unit_tests
    assert "${{ secrets." not in unit_tests
    assert "cache-read-only: ${{ github.ref != 'refs/heads/main' }}" in unit_tests
    # Fork PRs must keep working: debug keystore is the in-repo prebuilt file.
    assert "app/setup/prebuilt/debug.keystore" in android
    assert "app/setup/prebuilt/debug.keystore" in unit_tests


def test_mobile_kiritimati_dart_suite_is_a_parallel_second_pass():
    repo = BACKEND_DIR.parent
    mobile_checks = (repo / ".github/workflows/mobile-app-checks.yml").read_text(encoding="utf-8")
    jobs = _github_jobs(mobile_checks)

    tz_job = jobs["dart-tests-kiritimati"]
    journeys = jobs["journeys-hermetic"]
    analyze = jobs["analyze-and-test"]

    assert "name: Dart Tests (Pacific/Kiritimati)" in mobile_checks
    assert "needs: changes" in tz_job
    assert "needs: analyze-and-test" not in tz_job
    assert "needs: android-compile-smoke" not in tz_job
    assert "needs: journeys-hermetic" not in tz_job
    assert "has_app_dart" in tz_job
    assert "TZ=Pacific/Kiritimati bash app/test.sh" in tz_job
    assert "TZ=Pacific/Pago_Pago bash app/test.sh" in tz_job
    assert "${{ secrets." not in tz_job
    # The UTC Dart job and the journeys lane must not grow this TZ serial
    # dependency — a needs: edge here would lengthen the critical path.
    assert "dart-tests-kiritimati" not in analyze
    assert "TZ=" not in journeys
    assert "Pacific/Kiritimati" not in journeys
    assert "Pacific/Pago_Pago" not in journeys


def test_mobile_ios_compile_check_is_path_gated_simulator_unsigned_and_secret_free():
    repo = BACKEND_DIR.parent
    mobile_checks = (repo / ".github/workflows/mobile-app-checks.yml").read_text(encoding="utf-8")
    detect_changes = (repo / ".github/actions/detect-changes/action.yml").read_text(encoding="utf-8")
    jobs = _github_jobs(mobile_checks)
    ios = jobs["ios-compile-check"]
    changes = jobs["changes"]
    resolver = _load_repo_script("pre_push_ci_prediction")

    assert "name: iOS Compile Check" in mobile_checks
    assert "runs-on: macos-26" in ios
    assert "needs: changes" in ios
    assert "has_app_ios_compile" in ios
    assert "has_app_ios_compile" in changes
    assert "has_app_ios_compile:" in detect_changes
    assert "timeout-minutes: 40" in ios
    assert "fetch-depth: 0" in ios
    assert "run-swift-ci.sh --select-toolchain" in ios
    assert "Prove stable iOS compiler emits no Siri metadata" in ios
    assert "hashFiles('app/ios/Podfile.lock')" in ios
    assert "GoogleService-Info-Local.plist" in ios
    assert "flutter build ios --simulator --debug --flavor dev --no-codesign -d \"$IOS_SIMULATOR_UDID\"" in ios
    assert "simctl" in ios
    assert "IOS_SIMULATOR_UDID" in ios
    assert "${{ secrets." not in ios
    assert "ios-compile-check.yml" not in mobile_checks

    dart = "app/lib/pages/chat/page.dart"
    dart_outputs = resolver.github_outputs(
        resolver.resolve_impact([dart], read_text=lambda path: {dart: "class ChatPage {}"}.get(path))
    )
    assert dart_outputs["has_app_ios_compile"] == "false"
    assert dart_outputs["has_app_compile_smoke"] == "true"

    swift = "app/ios/Runner/AppDelegate.swift"
    swift_outputs = resolver.github_outputs(resolver.resolve_impact([swift]))
    assert swift_outputs["has_app_ios_compile"] == "true"

    workflow = ".github/workflows/mobile-app-checks.yml"
    workflow_outputs = resolver.github_outputs(resolver.resolve_impact([workflow]))
    assert workflow_outputs["has_app_ios_compile"] == "true"

    # Stacked PRs whose base is not main must still start this workflow.
    # `pull_request: branches: main` skipped the entire run for #14358.
    header = mobile_checks.split("jobs:", 1)[0]
    assert "pull_request:" in header
    assert "push:\n    branches: main" in header
    assert "pull_request:\n    branches:" not in header


def test_installed_pre_push_hook_falls_back_for_older_worktrees():
    installer = (BACKEND_DIR.parent / "scripts/install-git-hooks.sh").read_text(encoding="utf-8")

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


def test_workflow_contracts_static_check_ignores_non_python_glob_matches(tmp_path, monkeypatch):
    checker = _load_script("check_workflow_contracts")
    fake_repo = tmp_path / "repo"
    source_dir = fake_repo / "backend" / "utils" / "memory"
    source_dir.mkdir(parents=True)
    (source_dir / "contract.py").write_text("def safe_contract() -> tuple[int, int, int]:\n    return 1, 2, 3\n")
    (source_dir / "ARCHITECTURE.md").write_text("# architecture\n")
    pycache = source_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "contract.cpython-311.pyc").write_bytes(b"\xa7\r\r\n")

    monkeypatch.setattr(checker, "REPO_DIR", fake_repo)
    contracts = {
        "checks": {
            "no_large_tuple_results": {
                "allowlist": [
                    {
                        "path": "backend/utils/memory/contract.py",
                        "function": "safe_contract",
                    }
                ]
            }
        },
        "workflows": [
            {
                "risk": "high",
                "sources": ["backend/utils/memory/**"],
                "tests": ["tests/unit/test_contract.py"],
                "checks": ["no_large_tuple_results"],
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


def test_codemagic_mobile_app_builds_inject_build_provenance_defines():
    repo = BACKEND_DIR.parent
    cm = (repo / "codemagic.yaml").read_text(encoding="utf-8")
    script = repo / "app/scripts/build_provenance_dart_defines.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "OMI_GIT_SHA" in text
    assert "OMI_BUILD_NUMBER" in text
    assert "OMI_GIT_DIRTY" in text
    assert "diff --quiet HEAD --" in text
    assert "git status --porcelain" not in text
    assert "CM_BUILD_ID" in text
    assert "diff --name-only HEAD --" in text
    assert "invalid OMI_GIT_SHA" in text
    assert "invalid OMI_BUILD_NUMBER" in text

    for workflow_id in (
        "ios-internal-auto",
        "android-internal-auto",
        "ios-prod-testflight",
        "android-prod-internal",
        "ios-prod-patch",
        "android-prod-patch",
    ):
        assert f"  {workflow_id}:" in cm

    assert cm.count("scripts/build_provenance_dart_defines.sh") == 6
    assert "shorebird patch ios" in cm
    assert "shorebird patch android" in cm


def _workflow_policy():
    path = BACKEND_DIR / "scripts" / "firestore_workflow_policy.py"
    spec = importlib.util.spec_from_file_location("firestore_workflow_policy", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get("firestore_workflow_policy")
    sys.modules["firestore_workflow_policy"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop("firestore_workflow_policy", None)
        else:
            sys.modules["firestore_workflow_policy"] = previous
    return module


def test_firestore_readiness_gate_covers_every_backend_image_shipment():
    """Every backend-source image push/deploy needs the shared immutable gate."""
    policy = _workflow_policy()
    assert policy.repository_gate_violations(BACKEND_DIR.parent) == []


def test_firestore_gate_policy_rejects_ungated_deploy_mutations():
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    workflow = (repo / '.github/workflows/gcp_memory_maintenance_job.yml').read_text(encoding='utf-8')

    gate_block = re.search(r'      - name: Verify serving Firestore indexes\n(?:        .*\n)+', workflow).group(0)
    removed = workflow.replace(gate_block, '')
    assert policy.workflow_gate_violations(removed, name='removed.yml', dockerfiles=dockerfiles)

    disabled = workflow.replace(
        '        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
        "        if: 'false'\n        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness",
    )
    assert policy.workflow_gate_violations(disabled, name='disabled.yml', dockerfiles=dockerfiles)

    tolerated = workflow.replace(
        '        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
        '        continue-on-error: true\n        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
    )
    assert policy.workflow_gate_violations(tolerated, name='tolerated.yml', dockerfiles=dockerfiles)

    tolerated_expr = workflow.replace(
        '        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
        '        continue-on-error: ${{ true }}\n'
        '        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
        1,
    )
    assert policy.workflow_gate_violations(tolerated_expr, name='tolerated-expr.yml', dockerfiles=dockerfiles)

    tolerated_job = workflow.replace('  deploy:\n', '  deploy:\n    continue-on-error: ${{ true }}\n', 1)
    assert policy.workflow_gate_violations(tolerated_job, name='tolerated-job.yml', dockerfiles=dockerfiles)

    tolerated_control = workflow.replace(
        '          persist-credentials: false\n',
        '          persist-credentials: false\n        continue-on-error: ${{ true }}\n',
        1,
    )
    assert policy.workflow_gate_violations(tolerated_control, name='tolerated-control.yml', dockerfiles=dockerfiles)

    push_step = re.search(r'      - name: Push verified runtime image\n(?:        .*\n)+', workflow).group(0)
    reordered = workflow.replace(gate_block, '')
    reordered = reordered.replace(push_step, push_step + gate_block)
    assert policy.workflow_gate_violations(reordered, name='reordered.yml', dockerfiles=dockerfiles)


def _synthetic_deploy(steps: str, *, extra_jobs: str = '', job_prefix: str = '') -> str:
    return f"""name: synthetic-deploy
on: workflow_dispatch
jobs:
  deploy:
{job_prefix}    environment: development
    runs-on: ubuntu-latest
    steps:
{steps}
{extra_jobs}"""


_SYNTHETIC_GATE = """      - uses: actions/checkout@v7
      - name: Checkout immutable Firestore gate controls
        uses: actions/checkout@v7
        with:
          ref: ${{ github.workflow_sha }}
          path: .github/firestore-workflow
          persist-credentials: false
      - name: Verify serving Firestore indexes
        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness
        with:
          source_sha: ${{ github.sha }}
          project_id: ${{ vars.RUNTIME_GCP_PROJECT_ID }}
          credentials_json: ${{ secrets.GCP_FIRESTORE_READONLY_CREDENTIALS }}
"""


def test_firestore_gate_policy_rejects_new_ungated_backend_deploy_workflow():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    synthetic = _synthetic_deploy("""      - uses: actions/checkout@v7
      - name: Build backend image
        uses: docker/build-push-action@v7
        with:
          context: .
          file: backend/Dockerfile
          push: true
          tags: gcr.io/example/brand-new-worker:abc1234
""")
    violations = policy.workflow_gate_violations(synthetic, name='synthetic-new-worker.yml', dockerfiles=dockerfiles)
    assert any('Firestore readiness gate' in violation for violation in violations)

    gated = _synthetic_deploy(_SYNTHETIC_GATE + """      - name: Build backend image
        uses: docker/build-push-action@v7
        with:
          context: .
          file: backend/Dockerfile
          push: true
          tags: gcr.io/example/brand-new-worker:abc1234
""")
    assert policy.workflow_gate_violations(gated, name='synthetic-gated.yml', dockerfiles=dockerfiles) == []


@pytest.mark.parametrize(
    'ship_steps',
    [
        """      - run: |
          docker build -f backend/Dockerfile -t "$IMAGE" .
      - run: docker push "$IMAGE"
""",
        """      - run: |
          docker build -t "$IMAGE" backend
      - run: docker push "$IMAGE"
""",
        """      - run: |
          docker build -t "$IMAGE" .
        working-directory: backend
      - run: docker push "$IMAGE"
""",
        """      - run: |
          docker buildx build -f backend/Dockerfile -t "$IMAGE" --push .
""",
    ],
    ids=['split-build-push', 'default-backend-context', 'backend-working-directory', 'buildx-push'],
)
def test_firestore_gate_policy_tracks_split_build_and_push_provenance(ship_steps):
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    job_prefix = '    env:\n      IMAGE: gcr.io/example/backend:abc1234\n'
    ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n' + ship_steps, job_prefix=job_prefix)
    assert policy.workflow_gate_violations(ungated, name='ungated.yml', dockerfiles=dockerfiles)
    gated = _synthetic_deploy(_SYNTHETIC_GATE + ship_steps, job_prefix=job_prefix)
    assert policy.workflow_gate_violations(gated, name='gated.yml', dockerfiles=dockerfiles) == []


@pytest.mark.parametrize(
    'ship_steps,job_prefix',
    [
        (
            """      - run: |
          docker build -f backend/Dockerfile -t gcr.io/example/brand-new-worker:abc1234 .
      - run: docker push gcr.io/example/brand-new-worker:abc1234
""",
            '',
        ),
        (
            """      - run: |
          docker build -f backend/Dockerfile -t "$IMAGE" .
      - run: docker push "$IMAGE"
""",
            '    env:\n      IMAGE: gcr.io/example/brand-new-worker:abc1234\n',
        ),
    ],
    ids=['literal-tag', 'variable-tag'],
)
def test_firestore_gate_policy_tracks_brand_new_worker_provenance(ship_steps, job_prefix):
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n' + ship_steps, job_prefix=job_prefix)
    assert policy.workflow_gate_violations(ungated, name='ungated.yml', dockerfiles=dockerfiles)
    gated = _synthetic_deploy(_SYNTHETIC_GATE + ship_steps, job_prefix=job_prefix)
    assert policy.workflow_gate_violations(gated, name='gated.yml', dockerfiles=dockerfiles) == []


@pytest.mark.parametrize(
    'ship_steps',
    [
        """      - uses: google-github-actions/deploy-cloudrun@v3
        with:
          service: backend
          image: gcr.io/example/backend@sha256:%s
""" % ('a' * 64),
        '      - run: gcloud run services update backend --image gcr.io/example/backend:abc1234 --region us-central1\n',
    ],
    ids=['deploy-cloudrun-action', 'services-update-image'],
)
def test_firestore_gate_policy_covers_cloud_run_shipments(ship_steps):
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n' + ship_steps)
    assert policy.workflow_gate_violations(ungated, name='ungated.yml', dockerfiles=dockerfiles)
    gated = _synthetic_deploy(_SYNTHETIC_GATE + ship_steps)
    assert policy.workflow_gate_violations(gated, name='gated.yml', dockerfiles=dockerfiles) == []


def test_firestore_gate_policy_ignores_traffic_only_updates():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    traffic_only = _synthetic_deploy(
        '      - run: gcloud run services update-traffic backend --to-revisions backend-abc=100 --region us-central1\n'
    )
    assert policy.workflow_gate_violations(traffic_only, name='traffic.yml', dockerfiles=dockerfiles) == []


def test_firestore_gate_policy_rejects_or_dependency_bypass():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    gate_job = """  gate:
    environment: development
    runs-on: ubuntu-latest
    steps:
"""
    gate_job += _SYNTHETIC_GATE
    for deploy_if in (
        "    if: always() && needs.gate.result == 'success' || true\n",
        "    if: always() || needs.gate.result == 'failure'\n",
        '    if: always()\n',
        "    if: always() && (needs.gate.result == 'success' || true)\n",
        "    if: (always() && needs.gate.result == 'success') || true\n",
        "    if: failure() && needs.gate.result == 'success' || needs.gate.result == 'failure'\n",
        "    if: needs.gate.result != 'failure'\n",
        "    if: always() && !(needs.gate.result == 'success')\n",
    ):
        deploy_job = (
            '  deploy:\n    needs: [gate]\n'
            + deploy_if
            + '    environment: development\n    runs-on: ubuntu-latest\n    steps:\n'
            + '      - run: docker push gcr.io/example/backend:abc1234\n'
        )
        synthetic = _synthetic_deploy('      - uses: actions/checkout@v7\n', extra_jobs=gate_job + deploy_job)
        assert policy.workflow_gate_violations(synthetic, name='orbypass.yml', dockerfiles=dockerfiles), deploy_if

    gated_job = (
        '  deploy:\n    needs: [gate]\n'
        "    if: always() && needs.gate.result == 'success'\n"
        '    environment: development\n    runs-on: ubuntu-latest\n    steps:\n'
        '      - run: docker push gcr.io/example/backend:abc1234\n'
    )
    synthetic = _synthetic_deploy('      - uses: actions/checkout@v7\n', extra_jobs=gate_job + gated_job)
    assert policy.workflow_gate_violations(synthetic, name='orbypass.yml', dockerfiles=dockerfiles) == []

    false_gate_job = gate_job.replace('  gate:', "  gate:\n    if: 'false'", 1)
    false_deploy = (
        '  deploy:\n    needs: [gate]\n    if: always()\n'
        '    environment: development\n    runs-on: ubuntu-latest\n    steps:\n'
        '      - run: docker push gcr.io/example/backend:abc1234\n'
    )
    synthetic = _synthetic_deploy('      - uses: actions/checkout@v7\n', extra_jobs=false_gate_job + false_deploy)
    assert policy.workflow_gate_violations(synthetic, name='falsegate.yml', dockerfiles=dockerfiles)


def test_firestore_gate_policy_step_working_directory_overrides_job_defaults():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    job_prefix = '    env:\n      IMAGE: gcr.io/example/backend:abc1234\n    defaults:\n      run:\n        working-directory: frontend\n'
    ship = (
        '      - run: docker build -t "$IMAGE" .\n        working-directory: backend\n'
        '      - run: docker push "$IMAGE"\n'
    )
    ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n' + ship, job_prefix=job_prefix)
    assert policy.workflow_gate_violations(ungated, name='wd.yml', dockerfiles=dockerfiles)
    gated = _synthetic_deploy(_SYNTHETIC_GATE + ship, job_prefix=job_prefix)
    assert policy.workflow_gate_violations(gated, name='wd.yml', dockerfiles=dockerfiles) == []


def test_firestore_gate_policy_action_file_is_workspace_relative():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    ship = """      - uses: docker/build-push-action@v7
        with:
          context: backend
          file: backend/Dockerfile
          push: true
          tags: gcr.io/example/backend:abc1234
"""
    ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n' + ship)
    violations = policy.workflow_gate_violations(ungated, name='ctx.yml', dockerfiles=dockerfiles)
    assert violations and not any('unregistered' in v for v in violations)
    gated = _synthetic_deploy(_SYNTHETIC_GATE + ship)
    assert policy.workflow_gate_violations(gated, name='ctx.yml', dockerfiles=dockerfiles) == []


def test_firestore_gate_policy_expands_local_action_inputs():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    helper = {'.github/actions/ship-image/action.yml': """name: ship
runs:
  using: composite
  steps:
    - uses: docker/build-push-action@v7
      with:
        context: .
        file: ${{ inputs.dockerfile }}
        push: true
        tags: gcr.io/example/brand-new-worker:abc1234
"""}
    ship = """      - uses: ./.github/actions/ship-image
        with:
          dockerfile: backend/Dockerfile
"""
    ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n' + ship)
    assert policy.workflow_gate_violations(ungated, name='nested.yml', local_actions=helper, dockerfiles=dockerfiles)
    gated = _synthetic_deploy(_SYNTHETIC_GATE + ship)
    assert (
        policy.workflow_gate_violations(gated, name='nested.yml', local_actions=helper, dockerfiles=dockerfiles) == []
    )


def test_firestore_gate_policy_rejects_unregistered_backend_dockerfile_context():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    synthetic = _synthetic_deploy(
        _SYNTHETIC_GATE + """      - run: docker build -t gcr.io/example/backend:f00d backend/future-service
"""
    )
    violations = policy.workflow_gate_violations(synthetic, name='unregistered.yml', dockerfiles=dockerfiles)
    assert any('unregistered backend Dockerfile' in violation for violation in violations)


@pytest.mark.parametrize(
    'gate_mutation',
    [
        "        if: ${{ false }}\n",
        '        if: always()\n',
        '        if: ${{ success() || true }}\n',
        '        continue-on-error: true\n',
    ],
    ids=['if-false', 'if-always', 'if-or-true', 'continue-on-error'],
)
def test_firestore_gate_policy_rejects_disabled_or_soft_gates(gate_mutation):
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    uses_line = '        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness\n'
    mutated = _synthetic_deploy(
        _SYNTHETIC_GATE.replace(uses_line, gate_mutation + uses_line)
        + '      - run: docker push gcr.io/example/backend:abc1234\n'
    )
    assert policy.workflow_gate_violations(mutated, name='soft-gate.yml', dockerfiles=dockerfiles)


def test_firestore_gate_policy_rejects_commented_and_reordered_and_orphan_gates():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    push = '      - run: docker push gcr.io/example/backend:abc1234\n'

    commented = _synthetic_deploy(
        '      - uses: actions/checkout@v7\n'
        + ''.join(f'      # {line.lstrip()}' for line in _SYNTHETIC_GATE.splitlines(keepends=True))
        + push
    )
    assert policy.workflow_gate_violations(commented, name='commented.yml', dockerfiles=dockerfiles)

    gate_after_checkout = _SYNTHETIC_GATE.split('      - name: Checkout', 1)
    reordered = _synthetic_deploy(
        '      - uses: actions/checkout@v7\n' + push + '      - name: Checkout' + gate_after_checkout[1]
    )
    assert policy.workflow_gate_violations(reordered, name='reordered.yml', dockerfiles=dockerfiles)

    unrelated_gate_job = """  gate:
    environment: development
    runs-on: ubuntu-latest
    steps:
"""
    sibling = _synthetic_deploy(
        '      - uses: actions/checkout@v7\n' + push,
        extra_jobs=unrelated_gate_job + _SYNTHETIC_GATE,
    )
    assert policy.workflow_gate_violations(sibling, name='unrelated.yml', dockerfiles=dockerfiles)


def test_firestore_gate_policy_rejects_always_failure_dependency_bypass():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    push = '      - run: docker push gcr.io/example/backend:abc1234\n'
    gate_job = """  firestore_readiness:
    environment: development
    runs-on: ubuntu-latest
    steps:
"""
    bypassing = _synthetic_deploy(
        '      - uses: actions/checkout@v7\n' + push,
        extra_jobs=gate_job + _SYNTHETIC_GATE,
        job_prefix="    needs: firestore_readiness\n    if: always() || needs.firestore_readiness.result == 'failure'\n",
    )
    assert policy.workflow_gate_violations(bypassing, name='bypass.yml', dockerfiles=dockerfiles)

    guarded = _synthetic_deploy(
        '      - uses: actions/checkout@v7\n' + push,
        extra_jobs=gate_job + _SYNTHETIC_GATE,
        job_prefix="    needs: firestore_readiness\n    if: always() && needs.firestore_readiness.result == 'success'\n",
    )
    assert policy.workflow_gate_violations(guarded, name='guarded.yml', dockerfiles=dockerfiles) == []


def test_firestore_gate_policy_fails_closed_on_unexpandable_local_action():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    synthetic = _synthetic_deploy(_SYNTHETIC_GATE + '      - uses: ./.github/actions/missing-composite\n')
    violations = policy.workflow_gate_violations(synthetic, name='missing-action.yml', dockerfiles=dockerfiles)
    assert any('cannot expand local action' in violation for violation in violations)

    hiding_action = {'.github/actions/ship/action.yml': """name: ship
runs:
  using: composite
  steps:
    - shell: bash
      run: |
        docker build -f backend/Dockerfile -t gcr.io/example/backend:abc1234 .
        docker push gcr.io/example/backend:abc1234
"""}
    hidden = _synthetic_deploy(_SYNTHETIC_GATE + '      - uses: ./.github/actions/ship\n')
    assert (
        policy.workflow_gate_violations(hidden, name='hidden.yml', local_actions=hiding_action, dockerfiles=dockerfiles)
        == []
    )
    hidden_ungated = _synthetic_deploy('      - uses: actions/checkout@v7\n      - uses: ./.github/actions/ship\n')
    assert policy.workflow_gate_violations(
        hidden_ungated, name='hidden-ungated.yml', local_actions=hiding_action, dockerfiles=dockerfiles
    )


def test_firestore_gate_policy_pins_qa_database_and_environment():
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    for workflow_name in ('jit_qa_cloud_run.yml', 'jit_qa_typesense_projection.yml'):
        workflow = (repo / '.github/workflows' / workflow_name).read_text(encoding='utf-8')
        wrong_db = workflow.replace('database: ${{ env.QA_FIRESTORE_DATABASE }}', 'database: (default)')
        assert policy.workflow_gate_violations(wrong_db, name=workflow_name, dockerfiles=dockerfiles)
        wrong_env = workflow.replace('environment: development', 'environment: qa-sandbox')
        assert policy.workflow_gate_violations(wrong_env, name=workflow_name, dockerfiles=dockerfiles)


def test_firestore_gate_policy_rejects_source_sha_workflow_commit_substitution():
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    for workflow_name in ('gcp_backend_listen_helm.yml', 'gcp_backend_pusher.yml'):
        workflow = (repo / '.github/workflows' / workflow_name).read_text(encoding='utf-8')
        mutated = re.sub(
            r'source_sha: \$\{\{ [^}]*\}\}',
            'source_sha: ${{ github.workflow_sha }}',
            workflow,
        )
        violations = policy.workflow_gate_violations(mutated, name=workflow_name, dockerfiles=dockerfiles)
        assert any('workflow commit' in violation for violation in violations), workflow_name


def test_firestore_gate_policy_rejects_orphaned_readiness_dependency():
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    workflow = (repo / '.github/workflows/gcp_backend.yml').read_text(encoding='utf-8')
    readiness_job = re.search(
        r'  firestore_readiness:\n(?:    .*\n|      .*\n|        .*\n|          .*\n|            .*\n)+', workflow
    )
    assert readiness_job is not None
    orphaned = workflow[: readiness_job.start()] + workflow[readiness_job.end() :]
    violations = policy.workflow_gate_violations(orphaned, name='orphan.yml', dockerfiles=dockerfiles)
    assert any('firestore_readiness' in violation for violation in violations)


_LANE_SOURCE_BINDINGS = {
    'gcp_backend.yml': '${{ steps.admitted_source.outputs.admitted_sha }}',
    'gcp_backend_auto_dev.yml': '${{ steps.admitted_source.outputs.admitted_sha }}',
    'desktop_backend_prod.yml': '${{ steps.admitted-source.outputs.source_sha }}',
    'desktop_backend_auto_dev.yml': '${{ steps.candidate-identity.outputs.source_sha }}',
    'gcp_llm_gateway.yml': '${{ env.CHECKED_OUT_SHA }}',
    'gcp_memory_maintenance_job.yml': '${{ env.CHECKED_OUT_SHA }}',
    'gcp_memory_maintenance_job_auto_dev.yml': '${{ github.sha }}',
    'gcp_notifications_job.yml': '${{ env.CHECKED_OUT_SHA }}',
    'gcp_x_connector_sync_job.yml': '${{ env.CHECKED_OUT_SHA }}',
    'gcp_daily_memory_sweep_job.yml': '${{ steps.admitted_source.outputs.admitted_sha }}',
    'gcp_daily_memory_sweep_job_auto_dev.yml': '${{ steps.admitted_source.outputs.admitted_sha }}',
    'gcp_day3_reengagement_email_job.yml': '${{ steps.admitted_source.outputs.admitted_sha }}',
    'gcp_day3_reengagement_email_job_auto_dev.yml': '${{ steps.admitted_source.outputs.admitted_sha }}',
    'gcp_frame_request_retention_job.yml': '${{ github.event.inputs.release_sha }}',
    'gcp_backend_pusher.yml': '${{ env.FIRESTORE_GATE_SOURCE_SHA }}',
    'gcp_backend_pusher_auto_deploy.yml': '${{ github.sha }}',
    'gcp_backend_listen_helm.yml': '${{ env.BACKEND_LISTEN_SOURCE_SHA }}',
    'jit_qa_cloud_run.yml': '${{ needs.admit.outputs.source_sha }}',
    'jit_qa_typesense_projection.yml': '${{ needs.admit.outputs.source_sha }}',
}


@pytest.mark.parametrize('workflow_name', sorted(_LANE_SOURCE_BINDINGS))
def test_firestore_gate_lane_source_binding(workflow_name):
    workflows = BACKEND_DIR.parent / '.github/workflows'
    text = (workflows / workflow_name).read_text(encoding='utf-8')
    expected = _LANE_SOURCE_BINDINGS[workflow_name]
    count = text.count(f'source_sha: {expected}')
    assert count >= 1, f'{workflow_name} must bind the gate source_sha to {expected}'
    assert 'source_sha: ${{ github.workflow_sha }}' not in text


def test_firestore_gate_lane_source_and_target_bindings():
    """Lane-specific source identities the dynamic discovery cannot infer."""
    repo = BACKEND_DIR.parent
    workflows = repo / '.github/workflows'

    pusher = (workflows / 'gcp_backend_pusher.yml').read_text(encoding='utf-8')
    assert 'echo "FIRESTORE_GATE_SOURCE_SHA=$QUALIFIED_SOURCE_SHA"' in pusher
    assert 'source_sha: ${{ env.CHECKED_OUT_SHA }}' not in pusher

    listen = (workflows / 'gcp_backend_listen_helm.yml').read_text(encoding='utf-8')
    assert 'echo "BACKEND_LISTEN_SOURCE_SHA=$(git rev-parse "${REQUESTED_TAG}^{commit}")" >> "$GITHUB_ENV"' in listen
    assert 'BACKEND_LISTEN_SOURCE_SHA=$CHECKED_OUT_SHA' not in listen
    assert 'BACKEND_LISTEN_SOURCE_SHA=$ROLLBACK_SHA' not in listen
    assert 'BACKEND_LISTEN_SOURCE_SHA=$SELECTED_SHA' not in listen
    # Rollback replays the operator's requested Helm revision verbatim; there is
    # no resolver step and no source-sha derivation on that lane.
    assert 'helm -n "$NS" rollback "$RELEASE" "$TARGET_REVISION" --wait --timeout 30m' in listen
    assert 'helm -n "$NS" rollback "$RELEASE" --wait --timeout 30m' in listen
    assert 'TARGET_REVISION: ${{ github.event.inputs.helm_revision }}' in listen
    assert 'BACKEND_LISTEN_ROLLBACK_REVISION' not in listen
    assert 'BACKEND_LISTEN_SOURCE_SHA=$RUNNING_TAG' not in listen
    gate_condition = "if: ${{ env.BACKEND_LISTEN_SOURCE_SHA != '' }}"
    assert listen.count(gate_condition) == 2

    for jit_name in ('jit_qa_cloud_run.yml', 'jit_qa_typesense_projection.yml'):
        jit = (workflows / jit_name).read_text(encoding='utf-8')
        assert 'project_id: ${{ env.QA_PROJECT }}' in jit, jit_name
        assert 'database: ${{ env.QA_FIRESTORE_DATABASE }}' in jit, jit_name

    auto_dev = (workflows / 'gcp_backend_auto_dev.yml').read_text(encoding='utf-8')
    assert "verify_credential_project: 'true'" in auto_dev

    scope_match = re.search(r"grep -Eq '([^']+)' <<<\"\$changed_files\"", auto_dev)
    assert scope_match, 'auto-dev scope grep must keep its changed-files contract'
    pattern = scope_match.group(1)
    for gate_path in (
        '.github/actions/firestore-readiness/action.yml',
        '.github/actions/deploy-backend-stack/action.yml',
    ):
        assert re.search(pattern, gate_path), f'auto deploy scope regex must match {gate_path}'


def test_listen_gate_is_the_conditional_source_sha_gate():
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    name = 'gcp_backend_listen_helm.yml'
    workflow = (repo / '.github/workflows' / name).read_text(encoding='utf-8')
    assert policy.workflow_gate_violations(workflow, name=name, dockerfiles=dockerfiles) == []

    gate_block = re.search(r'      - name: Verify serving Firestore indexes\n(?:        .*\n)+', workflow).group(0)
    removed = workflow.replace(gate_block, '')
    assert policy.workflow_gate_violations(removed, name=name, dockerfiles=dockerfiles)

    tolerated = workflow.replace(
        '        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
        '        continue-on-error: true\n        uses: ./.github/firestore-workflow/.github/actions/firestore-readiness',
        1,
    )
    assert policy.workflow_gate_violations(tolerated, name=name, dockerfiles=dockerfiles)

    unconditional = workflow.replace(
        gate_block, gate_block.replace("        if: ${{ env.BACKEND_LISTEN_SOURCE_SHA != '' }}\n", ''), 1
    )
    assert any(
        'listen readiness gate must be conditioned' in violation
        for violation in policy.workflow_gate_violations(unconditional, name=name, dockerfiles=dockerfiles)
    )

    control_block = re.search(
        r'      - name: Checkout immutable Firestore gate controls\n(?:        .*\n|          .*\n)+', workflow
    ).group(0)
    control_after = workflow.replace(control_block, '', 1).replace(gate_block, gate_block + control_block, 1)
    assert policy.workflow_gate_violations(control_after, name=name, dockerfiles=dockerfiles)

    unconditional_control = workflow.replace(
        control_block,
        control_block.replace("        if: ${{ env.BACKEND_LISTEN_SOURCE_SHA != '' }}\n", ''),
        1,
    )
    assert policy.workflow_gate_violations(unconditional_control, name=name, dockerfiles=dockerfiles)

    gate_steps = control_block + '\n' + gate_block
    assert gate_steps in workflow
    late = workflow.replace(gate_steps, '', 1).replace(
        '      - name: Upgrade backend-listen Helm chart',
        gate_steps + '      - name: Upgrade backend-listen Helm chart',
        1,
    )
    assert policy.workflow_gate_violations(late, name=name, dockerfiles=dockerfiles)

    after_config = workflow.replace(gate_steps, '', 1).replace(
        '      - name: Upgrade backend-secrets Helm chart',
        gate_steps + '      - name: Upgrade backend-secrets Helm chart',
        1,
    )
    assert policy.workflow_gate_violations(after_config, name=name, dockerfiles=dockerfiles)

    no_source = workflow.replace(
        '          echo "BACKEND_LISTEN_SOURCE_SHA=$(git rev-parse "${REQUESTED_TAG}^{commit}")" >> "$GITHUB_ENV"\n',
        '',
        1,
    )
    assert policy.workflow_gate_violations(no_source, name=name, dockerfiles=dockerfiles)

    kept_write = workflow.replace(
        '            echo "BACKEND_LISTEN_IMAGE_TAG=$RUNNING_TAG" >> "$GITHUB_ENV"\n            exit 0',
        '            echo "BACKEND_LISTEN_IMAGE_TAG=$RUNNING_TAG" >> "$GITHUB_ENV"\n'
        '            echo "BACKEND_LISTEN_SOURCE_SHA=$(git rev-parse HEAD)" >> "$GITHUB_ENV"\n            exit 0',
        1,
    )
    assert kept_write != workflow
    assert policy.workflow_gate_violations(kept_write, name=name, dockerfiles=dockerfiles)

    resolver = workflow + "\n        # helm -n ns get values rel --revision 2\n"
    assert policy.workflow_gate_violations(resolver, name=name, dockerfiles=dockerfiles)

    built = workflow.replace(
        '      - name: Carry forward config this workflow does not own',
        '      - run: docker push gcr.io/example/backend:abc1234\n'
        '      - name: Carry forward config this workflow does not own',
        1,
    )
    assert policy.workflow_gate_violations(built, name=name, dockerfiles=dockerfiles)


def test_firestore_gate_checkouts_are_sparse():
    """Controls and admitted-source checkouts fetch only what the gate needs."""
    repo = BACKEND_DIR.parent
    controls_sparse = (
        '          path: .github/firestore-workflow\n'
        '          persist-credentials: false\n'
        '          fetch-depth: 1\n'
        '          sparse-checkout: |\n'
        '            .github/actions/firestore-readiness\n'
        '            backend/scripts\n'
        '            backend/database\n'
    )
    gated = 0
    for path in (repo / '.github/workflows').glob('*.yml'):
        text = path.read_text(encoding='utf-8')
        count = text.count('path: .github/firestore-workflow')
        assert text.count(controls_sparse) == count, path
        gated += count
    assert gated == len(_LANE_SOURCE_BINDINGS)

    action = (repo / '.github/actions/firestore-readiness/action.yml').read_text(encoding='utf-8')
    assert (
        '        path: .github/firestore-source\n'
        '        persist-credentials: false\n'
        '        fetch-depth: 1\n'
        '        sparse-checkout: backend/database\n'
    ) in action


def _local_actions(repo):
    actions_dir = repo / '.github/actions'
    return {
        str(path.relative_to(repo)): path.read_text(encoding='utf-8')
        for pattern in ('action.yml', 'action.yaml')
        for path in actions_dir.rglob(pattern)
    }


def test_backend_gcr_publishers_are_exactly_the_gated_builders():
    """Only the gated builder workflows may publish the backend GCR repository."""
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    known = policy._known_image_names(dockerfiles)
    local_actions = _local_actions(repo)
    # Workflows publish only by pushing gcr.io refs directly or through local
    # composites that do so (transitively); anything else cannot ship an image.
    push_actions = {key for key, body in local_actions.items() if policy._GCR_HOST.search(body)}
    while True:
        push_names = {key.rsplit('/', 2)[-2] for key in push_actions}
        grown = push_actions | {
            key
            for key, body in local_actions.items()
            if any(f'./.github/actions/{action_name}' in body for action_name in push_names)
        }
        if grown == push_actions:
            break
        push_actions = grown
    push_refs = {f'./.github/actions/{key.rsplit("/", 2)[-2]}' for key in push_actions}
    publishers: set[str] = set()
    for path in sorted((repo / '.github/workflows').glob('*.yml')):
        text = path.read_text(encoding='utf-8')
        if not policy._GCR_HOST.search(text) and not any(ref in text for ref in push_refs):
            continue
        document = policy._yaml_document(text)
        for job_id, job in (document.get('jobs') or {}).items():
            if not isinstance(job, dict) or not isinstance(job.get('steps'), list):
                continue
            errors: list[str] = []
            expanded = policy._expand_steps(job['steps'], local_actions, path.name, job_id, errors)
            job_state = {'var_images': {}, 'tag_images': {}, 'env': {}, 'built_firestore': False}
            for step in expanded:
                _shipments, _unregistered, published = policy._step_shipments(
                    step, document, job, dockerfiles, known, job_state
                )
                if 'backend' in published:
                    publishers.add(path.name)
    assert publishers == {'gcp_backend.yml', 'gcp_backend_auto_dev.yml'}


def test_cutover_consumes_gated_images_without_building():
    """Cutover is exempt only because it consumes; adding a build/push fails."""
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    local_actions = _local_actions(repo)
    name = 'sync_ledger_fence_cutover.yml'
    workflow = (repo / '.github/workflows' / name).read_text(encoding='utf-8')
    assert (
        policy.workflow_gate_violations(workflow, name=name, local_actions=local_actions, dockerfiles=dockerfiles) == []
    )

    built = workflow.replace(
        '      - name: Upload standby cutover state',
        '      - run: docker push gcr.io/example/backend:abc1234\n      - name: Upload standby cutover state',
        1,
    )
    assert built != workflow
    assert policy.workflow_gate_violations(built, name=name, local_actions=local_actions, dockerfiles=dockerfiles)

    # Only the named cutover workflow may invoke the consume helper ungated.
    renamed = policy.workflow_gate_violations(
        workflow, name='renamed_cutover.yml', local_actions=local_actions, dockerfiles=dockerfiles
    )
    assert renamed


def test_new_workflow_pushing_backend_repository_is_ungated_violation():
    policy = _workflow_policy()
    dockerfiles = policy._runtime_images(BACKEND_DIR.parent)
    synthetic = _synthetic_deploy(
        '      - uses: actions/checkout@v7\n      - run: docker push gcr.io/example/backend:anytag\n'
    )
    assert policy.workflow_gate_violations(synthetic, name='synthetic.yml', dockerfiles=dockerfiles)


def test_no_customer_data_gate_for_central_or_qa():
    policy = _workflow_policy()
    repo = BACKEND_DIR.parent
    dockerfiles = policy._runtime_images(repo)
    actions_dir = repo / '.github/actions'
    local_actions = {
        str(path.relative_to(repo)): path.read_text(encoding='utf-8')
        for pattern in ('action.yml', 'action.yaml')
        for path in actions_dir.rglob(pattern)
    }
    for workflow_name in (
        'gcp_backend.yml',
        'gcp_backend_auto_dev.yml',
        'jit_qa_cloud_run.yml',
        'jit_qa_typesense_projection.yml',
    ):
        workflow = (repo / '.github/workflows' / workflow_name).read_text(encoding='utf-8')
        violations = policy.workflow_gate_violations(
            workflow, name=workflow_name, local_actions=local_actions, dockerfiles=dockerfiles
        )
        assert violations == [], violations
        assert 'project_id: based-hardware' not in workflow, workflow_name


def test_firestore_gate_contract_selects_the_coverage_guard(selector_and_all_tests):
    selector, all_tests = selector_and_all_tests
    contracts = json.loads((BACKEND_DIR / 'testing/workflow_contracts.json').read_text(encoding='utf-8'))
    readiness = next(workflow for workflow in contracts['workflows'] if workflow['id'] == 'firestore_schema_readiness')
    assert '.github/actions/firestore-readiness/action.yml' in readiness['sources']
    assert '.github/workflows/**' in readiness['sources']
    assert 'tests/unit/test_workflow_contracts.py' in readiness['tests']

    selected, _reason = selector.tests_for_changed_paths(
        ['.github/workflows/gcp_models.yml'],
        all_tests,
    )
    assert 'tests/unit/test_workflow_contracts.py' in selected
    assert 'tests/unit/test_reconcile_firestore_indexes.py' in selected


def _workflow_run_step(workflow_name: str, step_name: str):
    document = yaml.safe_load((BACKEND_DIR.parent / '.github/workflows' / workflow_name).read_text(encoding='utf-8'))
    for job in document['jobs'].values():
        for step in job.get('steps') or []:
            if isinstance(step, dict) and step.get('name') == step_name:
                return step
    raise AssertionError(f'{workflow_name} has no step {step_name}')


def _render_run(run: str, substitutions: dict[str, str]) -> str:
    def replace(match):
        key = match.group(1).strip()
        if key in substitutions:
            return substitutions[key]
        raise AssertionError(f'unbound workflow expression {key}')

    rendered = re.sub(r'\$\{\{\s*([^}]+?)\s*\}\}', replace, run)
    assert '${{' not in rendered
    return rendered


_GIT_STUB = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
while args and args[0] == '-C':
    args = args[2:]
tags_file = os.environ.get('STUB_GIT_TAGS', '')
tags = json.load(open(tags_file)) if tags_file and os.path.exists(tags_file) else {}
ancestors_file = os.environ.get('STUB_GIT_ANCESTORS', '')
ancestors = set(json.load(open(ancestors_file))) if ancestors_file and os.path.exists(ancestors_file) else set()
cmd = args[0]
if cmd == 'fetch':
    sys.exit(0)
if cmd == 'cat-file':
    sys.exit(0 if args[-1].removesuffix('^{commit}') in tags else 1)
if cmd == 'merge-base':
    sys.exit(0 if args[2] in ancestors else 1)
if cmd == 'rev-parse':
    ref = args[-1]
    if ref in ('HEAD', 'HEAD^{commit}'):
        print(os.environ['STUB_GIT_HEAD']); sys.exit(0)
    if ref == 'origin/main':
        print(os.environ.get('STUB_GIT_MAIN', '')); sys.exit(0)
    sha = tags.get(ref.removesuffix('^{commit}'))
    if sha:
        print(sha[:7] if '--short=7' in args else sha)
        sys.exit(0)
    sys.exit(1)
sys.exit(1)
"""

_KUBECTL_STUB = """#!/usr/bin/env python3
import os, sys
if 'get' in sys.argv and 'deploy/' in ' '.join(sys.argv):
    image = os.environ.get('STUB_KUBECTL_IMAGE', '')
    if image:
        print(image)
        sys.exit(0)
sys.exit(1)
"""

_GCLOUD_STUB = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:3] == ['container', 'images', 'describe']:
    ref = args[3]
    tag = ref.rsplit(':', 1)[-1]
    tags = json.load(open(os.environ['STUB_GIT_TAGS']))
    sys.exit(0 if tag in tags else 1)
if args[:2] == ['config', 'get-value']:
    print(os.environ.get('STUB_GCLOUD_PROJECT', '(unset)'))
    sys.exit(0)
if args[:2] == ['auth', 'print-access-token']:
    print('stub-token')
    sys.exit(0)
if 'indexes' in args and 'composite' in args and 'list' in args:
    sys.stdout.write(os.environ.get('STUB_GCLOUD_INDEXES', '[]'))
    sys.exit(0)
sys.exit(1)
"""


def _stub_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (
        ('git', _GIT_STUB),
        ('kubectl', _KUBECTL_STUB),
        ('gcloud', _GCLOUD_STUB),
    ):
        stub = bin_dir / name
        stub.write_text(body, encoding='utf-8')
        stub.chmod(0o755)
    return bin_dir


def _run_step(run: str, env: dict[str, str], substitutions: dict[str, str], tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    env_file = tmp_path / 'github.env'
    env_file.touch()
    proc = subprocess.run(
        ['bash', '-c', _render_run(run, substitutions)],
        env={**os.environ, **env, 'GITHUB_ENV': str(env_file)},
        capture_output=True,
        text=True,
    )
    outputs = {}
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                outputs[key] = value
    return proc, outputs


def _listen_env(tmp_path: Path, tags: dict, *, image='', ancestors=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / 'tags.json').write_text(json.dumps(tags), encoding='utf-8')
    (tmp_path / 'ancestors.json').write_text(
        json.dumps(ancestors if ancestors is not None else list(tags) + list(tags.values())), encoding='utf-8'
    )
    return {
        'STUB_GIT_TAGS': str(tmp_path / 'tags.json'),
        'STUB_GIT_ANCESTORS': str(tmp_path / 'ancestors.json'),
        'STUB_GIT_HEAD': 'f' * 40,
        'STUB_GIT_MAIN': 'f' * 40,
        'STUB_KUBECTL_IMAGE': image,
    }


_LISTEN_SUBSTITUTIONS = {
    'vars.ENV': 'prod',
    'vars.GCP_PROJECT_ID': 'test-project',
    'github.event.inputs.environment': 'prod',
}


def test_listen_deploy_tag_resolution_executes_against_stubbed_tools(tmp_path):
    step = _workflow_run_step('gcp_backend_listen_helm.yml', 'Resolve backend-listen image tag')
    run = step['run']
    bin_dir = _stub_bin(tmp_path)
    base_env = {'PATH': f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    case = tmp_path / 'kept-tag'
    env = (
        base_env
        | _listen_env(case, {'abc1234': 'c' * 40}, image='gcr.io/test-project/backend:abc1234')
        | {'REQUESTED_TAG': ''}
    )
    proc, outputs = _run_step(run, env, _LISTEN_SUBSTITUTIONS, case)
    assert proc.returncode == 0, proc.stderr
    assert outputs['BACKEND_LISTEN_IMAGE_TAG'] == 'abc1234'
    # The kept lane replays an already-gated image; it must not resolve a SHA.
    assert 'BACKEND_LISTEN_SOURCE_SHA' not in outputs

    # Even when the kept tag cannot be resolved locally, the kept lane exits
    # before any git lookup and still emits no source SHA.
    case = tmp_path / 'kept-tag-unresolvable'
    env = base_env | _listen_env(case, {}, image='gcr.io/test-project/backend:eeeeeee') | {'REQUESTED_TAG': ''}
    proc, outputs = _run_step(run, env, _LISTEN_SUBSTITUTIONS, case)
    assert proc.returncode == 0, proc.stderr
    assert outputs['BACKEND_LISTEN_IMAGE_TAG'] == 'eeeeeee'
    assert 'BACKEND_LISTEN_SOURCE_SHA' not in outputs

    case = tmp_path / 'explicit-tag'
    env = (
        base_env
        | _listen_env(case, {'ddddddd': 'd' * 40}, image='gcr.io/test-project/backend:abc1234')
        | {'REQUESTED_TAG': 'ddddddd'}
    )
    proc, outputs = _run_step(run, env, _LISTEN_SUBSTITUTIONS, case)
    assert proc.returncode == 0, proc.stderr
    assert outputs['BACKEND_LISTEN_IMAGE_TAG'] == 'ddddddd'
    assert outputs['BACKEND_LISTEN_SOURCE_SHA'] == 'd' * 40

    case = tmp_path / 'missing-tag'
    env = base_env | _listen_env(case, {'abc1234': 'c' * 40}, image='') | {'REQUESTED_TAG': ''}
    proc, _ = _run_step(run, env, _LISTEN_SUBSTITUTIONS, case)
    assert proc.returncode == 1


def _composite_control_root(tmp_path: Path) -> Path:
    control = tmp_path / 'firestore-workflow'
    (control / '.github' / 'actions' / 'firestore-readiness').mkdir(parents=True)
    scripts_dir = control / 'backend' / 'scripts'
    database_dir = control / 'backend' / 'database'
    scripts_dir.mkdir(parents=True)
    database_dir.mkdir(parents=True)
    backend = BACKEND_DIR
    for name in ('reconcile_firestore_indexes.py', 'firestore_field_indexes.py'):
        (scripts_dir / name).write_text((backend / 'scripts' / name).read_text(encoding='utf-8'), encoding='utf-8')
    for name in ('__init__.py', 'firestore_index_registry.py', 'firestore_query_types.py', 'review_queries.py'):
        (database_dir / name).write_text((backend / 'database' / name).read_text(encoding='utf-8'), encoding='utf-8')
    (scripts_dir / '__init__.py').write_text('', encoding='utf-8')
    return control


def _composite_source_root(tmp_path: Path, manifest) -> Path:
    source = tmp_path / 'firestore-source'
    database_dir = source / 'backend' / 'database'
    database_dir.mkdir(parents=True)
    (database_dir / '__init__.py').write_text('', encoding='utf-8')
    (database_dir / 'firestore_index_registry.py').write_text(
        'import json\n\n\ndef firebase_index_manifest():\n    return json.loads('
        + repr(json.dumps(manifest))
        + ")\n\n\nif __name__ == '__main__':\n    print(json.dumps(firebase_index_manifest()))\n",
        encoding='utf-8',
    )
    (source / 'firestore.indexes.json').write_text(json.dumps(manifest), encoding='utf-8')
    return source


def _composite_run_steps():
    document = yaml.safe_load(
        (BACKEND_DIR.parent / '.github/actions/firestore-readiness/action.yml').read_text(encoding='utf-8')
    )
    return [step for step in document['runs']['steps'] if 'run' in step]


def _run_composite(
    tmp_path: Path,
    *,
    live_indexes,
    source_sha='e' * 40,
    head_sha=None,
    credentials='{}',
    verify_credential_project='false',
    run_validate_step=False,
):
    workspace = tmp_path / 'ws'
    control = _composite_control_root(tmp_path)
    source = _composite_source_root(
        tmp_path,
        {
            'indexes': [
                {
                    'collectionGroup': 'target_group',
                    'queryScope': 'COLLECTION',
                    'fields': [
                        {'fieldPath': 'a', 'order': 'ASCENDING'},
                        {'fieldPath': 'b', 'order': 'DESCENDING'},
                        {'fieldPath': '__name__', 'order': 'DESCENDING'},
                    ],
                }
            ],
            'fieldOverrides': [],
        },
    )
    checked_out = workspace / '.github' / 'firestore-source'
    checked_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, checked_out)
    runner_temp = tmp_path / 'runner-temp'
    runner_temp.mkdir(exist_ok=True)
    _stub_bin(tmp_path)
    credentials_path = tmp_path / 'credentials.json'
    credentials_path.write_text(credentials or '', encoding='utf-8')
    indexes_file = tmp_path / 'live-indexes.json'
    indexes_file.write_text(json.dumps(live_indexes), encoding='utf-8')

    substitutions = {
        'inputs.source_sha': source_sha,
        'inputs.project_id': 'dev-project',
        'inputs.database': '(default)',
        'inputs.credentials_json': credentials,
        'inputs.verify_credential_project': verify_credential_project,
        'inputs.artifact_suffix': '',
        'runner.temp': str(runner_temp),
        'github.run_id': '1',
        'github.run_attempt': '1',
        'github.action_path': str(control / '.github' / 'actions' / 'firestore-readiness'),
        'github.workspace': str(workspace),
        'steps.firestore-readonly-auth.outputs.credentials_file_path': str(credentials_path),
        'steps.firestore-readonly-auth.outputs.project_id': 'dev-project',
    }
    env = {
        'PATH': f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        'STUB_GIT_TAGS': str(tmp_path / 'no-tags.json'),
        'STUB_GIT_ANCESTORS': str(tmp_path / 'no-ancestors.json'),
        'STUB_GIT_HEAD': head_sha or source_sha,
        'STUB_GCLOUD_INDEXES': json.dumps(live_indexes),
        'GITHUB_WORKSPACE': str(workspace),
    }

    steps = {step['name']: step for step in _composite_run_steps()}

    def run_named(name):
        step = steps[name]
        step_env = {key: _render_run(str(value), substitutions) for key, value in (step.get('env') or {}).items()}
        return subprocess.run(
            ['bash', '-c', _render_run(step['run'], substitutions)],
            env={**os.environ, **env, **step_env},
            capture_output=True,
            text=True,
        )

    result = run_named('Validate Firestore readiness inputs')
    if result.returncode != 0:
        return result, None
    result = run_named('Verify admitted Firestore source identity')
    if result.returncode != 0:
        return result, None
    check = run_named('Verify serving Firestore indexes')
    validated = None
    if check.returncode != 0 and run_validate_step:
        validated = run_named('Validate blocked Firestore schema proposal')
    return check, validated


def test_firestore_readiness_composite_executes_hermetically(tmp_path):
    index = {
        'collectionGroup': 'target_group',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'a', 'order': 'ASCENDING'},
            {'fieldPath': 'b', 'order': 'DESCENDING'},
            {'fieldPath': '__name__', 'order': 'DESCENDING'},
        ],
    }
    ready_live = [
        {
            'name': 'projects/dev-project/databases/(default)/collectionGroups/target_group/indexes/x',
            'queryScope': 'COLLECTION',
            'fields': index['fields'],
            'state': 'READY',
        }
    ]

    check, _ = _run_composite(tmp_path / 'ready', live_indexes=ready_live)
    assert check.returncode == 0, check.stderr
    assert 'Firestore index readiness passed' in check.stdout

    check, validated = _run_composite(tmp_path / 'missing', live_indexes=[], run_validate_step=True)
    assert check.returncode == 1
    assert '::error title=Firestore index readiness failed::' in check.stdout
    assert 'COLLECTION/target_group' in check.stdout + check.stderr
    assert validated is not None and validated.returncode == 0, validated.stderr if validated else ''
    proposals = list((tmp_path / 'missing' / 'runner-temp').glob('firestore-schema-proposal-*.json'))
    assert len(proposals) == 1

    check, _ = _run_composite(tmp_path / 'bad-sha', live_indexes=ready_live, source_sha='not-a-sha')
    assert check.returncode == 1
    assert 'Invalid Firestore source SHA' in check.stdout

    check, _ = _run_composite(tmp_path / 'no-creds', live_indexes=ready_live, credentials='')
    assert check.returncode == 1
    assert 'Missing Firestore read-only credentials' in check.stdout

    check, _ = _run_composite(tmp_path / 'mismatch', live_indexes=ready_live, head_sha='0' * 40)
    assert check.returncode == 1
    assert 'Firestore source mismatch' in check.stdout


def test_notifications_job_deploy_restores_singleton_before_action_and_reattaches():
    workflow = yaml.safe_load((BACKEND_DIR.parent / '.github/workflows/gcp_notifications_job.yml').read_text())
    steps = workflow['jobs']['deploy']['steps']
    deploy_index = next(i for i, step in enumerate(steps) if step.get('id') == 'deploy')
    deploy = steps[deploy_index]
    assert deploy['uses'] == 'google-github-actions/deploy-cloudrun@v3'
    assert deploy['with']['job'] == '${{ env.SERVICE }}'
    assert deploy['with']['env_vars'] == '${{ steps.runtime-env.outputs.notifications_job_env_vars }}'
    assert deploy['with']['secrets'] == '${{ steps.runtime-env.outputs.notifications_job_secrets }}'
    assert '--container' not in deploy['with']['flags']
    detach = steps[deploy_index - 1]
    attach = steps[deploy_index + 1]
    assert 'attach_cloud_run_gmp_sidecar.py' in detach['run']
    assert '--job --detach' in detach['run']
    assert 'attach_cloud_run_gmp_sidecar.py' in attach['run']
    assert '--job' in attach['run'] and '--detach' not in attach['run']
    assert 'if' not in detach and 'if' not in attach
    assert workflow['concurrency']['cancel-in-progress'] is False
