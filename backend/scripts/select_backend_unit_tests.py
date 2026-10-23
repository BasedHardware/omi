#!/usr/bin/env python3
"""Select backend unit tests for either a full run or a changed-file PR run."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple, cast

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
WORKFLOW_CONTRACTS_PATH = BACKEND_DIR / 'testing' / 'workflow_contracts.json'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.support.firestore_serving_query_inventory import is_serving_query_inventory_path  # noqa: E402
from tests.support.background_task_ratchet_scope import is_background_task_ratchet_path  # noqa: E402

FULL_TEST_ROOTS = (
    BACKEND_DIR / 'tests' / 'unit',
    BACKEND_DIR / 'tests' / 'services',
    BACKEND_DIR / 'tests' / 'routers',
)
FULL_TEST_GLOBS = (BACKEND_DIR / 'tests',)

# Hermetic e2e tests selected by workflow contracts / memory policy core — not part of --all.
EXTRA_DISCOVERABLE_TESTS = (BACKEND_DIR / 'testing' / 'e2e' / 'test_canonical_memory_pipeline.py',)

LEGACY_UNLISTED_TESTS = {
    'tests/test_cache_manager.py',
    'tests/unit/test_diarizer_dockerfile.py',
    'tests/unit/test_lazy_conversation_processing.py',
}

FULL_RUN_PATHS = (
    '.github/workflows/backend-unit-tests.yml',
    'backend/pylock.toml',
    'backend/pylock.macos.toml',
    'backend/pylock.macos-x86_64.toml',
    'backend/pylock.runtime.toml',
    'backend/pylock.windows.toml',
    'backend/pyproject.toml',
    'backend/requirements.txt',
    'backend/test-preflight.sh',
    'backend/test.sh',
    'backend/tests/conftest.py',
    'backend/tests/unit/conftest.py',
    'backend/scripts/select_backend_unit_tests.py',
)

FULL_RUN_PREFIXES = (
    'backend/database/',
    'backend/models/',
    'backend/testing/',
)

# Explicit cross-cutting paths only. Do not use `backend/*` or
# `backend/utils/*.py` — those force the full suite for docs/AGENTS edits and
# every flat utils module before AREA_TESTS can narrow.
FULL_RUN_GLOBS = (
    'backend/main.py',
    'backend/dependencies.py',
    'backend/scripts/update-python-lock.sh',
    'backend/scripts/sync-python-deps.sh',
    'backend/utils/executors.py',
    'backend/utils/log_sanitizer.py',
    'backend/utils/http_client.py',
    'backend/utils/async_tasks.py',
    'backend/utils/encryption.py',
)

# Intentionally narrow exceptions to the generic model/database full-suite
# fallback so local pre-push feedback stays focused; CI still owns --all.
# Every entry must be mapped to a narrow area in AREA_TESTS below, so the
# exception still selects that area's contracts instead of nothing.
NARROW_FULL_RUN_EXCEPTIONS = frozenset(
    {
        # location-context consent area
        'backend/database/users.py',
        'backend/models/geolocation.py',
        'backend/models/users.py',
        # in-app CSAT surface
        'backend/database/csat.py',
    }
)

MEMORY_POLICY_CORE_PATH_PREFIXES = ('backend/utils/memory/',)

MEMORY_POLICY_CORE_PATH_GLOBS = (
    'backend/database/memory_*.py',
    'backend/models/product_memory.py',
    'backend/models/memory_search_gateway.py',
    'backend/routers/memory_*.py',
    'backend/routers/memories.py',
)

MEMORY_POLICY_CORE_TESTS = (
    'tests/unit/test_inv_mem_1_guard.py',
    'testing/e2e/test_canonical_memory_pipeline.py',
)

# Monitoring telemetry contract sources (#9587). Referenced from both the
# AREA_TESTS path->test mapping and is_selectable_backend_path's
# intentional-exception check below — single source so the two lists cannot
# drift apart and silently stop selecting the monitoring unit contracts.
MONITORING_CONTRACT_SOURCES = (
    'backend/charts/monitoring/prometheus-adapter/',
    'backend/scripts/diff_prod_adapter.py',
    'backend/charts/parakeet/',
    'backend/charts/backend-listen/',
    'backend/charts/pusher/',
    'backend/charts/vad/',
    'backend/charts/diarizer/',
    'backend/charts/nllb-translation/',
    'backend/scripts/alert_backtest.py',
    'backend/charts/monitoring/metric-inventory.prod.json',
    'backend/charts/monitoring/expected-targets.prod.yaml',
    'backend/charts/monitoring/kube-prometheus-stack/',
    'backend/charts/monitoring/alerts/',
    'backend/charts/monitoring/notifications/',
    'backend/charts/monitoring/alert-rules.json',
    'backend/charts/monitoring/live-alert-gate.json',
    'backend/charts/monitoring/prometheus-stackdriver-exporter/',
    'backend/charts/parakeet/templates/servicemonitor.yaml',
)

# Serving query contract checks are a cross-cutting guard, not an area-specific
# selection. Keep this list complete even when a change also selects narrower
# tests. The inventory predicate below is shared with the AST inventory's scope.
FIRESTORE_INDEX_GUARD_TESTS = (
    'tests/unit/test_firestore_query_shapes.py',
    'tests/unit/test_firestore_outside_query_contract.py',
    'tests/unit/test_firestore_caller_witnesses.py',
    'tests/unit/test_firestore_runtime_witnesses.py',
    'tests/unit/test_firestore_index_rules.py',
    'tests/unit/test_firestore_query_contract.py',
    'tests/unit/test_firestore_field_indexes.py',
)

FIRESTORE_INDEX_GUARD_SUPPORT_PREFIX = 'backend/tests/support/firestore_'
FIRESTORE_INDEX_GUARD_SCHEMA_PATHS = frozenset(
    {'firestore.indexes.json', 'backend/database/firestore_index_registry.py'}
)

# Background-task ratchet: un-awaited background work on the Cloud Tasks
# handler request paths must survive revision draining (#22198). The scanned
# module set is owned by the ratchet itself
# (tests/support/background_task_ratchet_scope.py); selection uses that
# module's cheap prefix superset over the same scope constants, so a change
# to any module the scanner can reach — including transitive closure members
# like services/users/account_deletion.py —
# always runs the ratchet, and a new un-awaited site cannot slip past
# changed-file CI and only fail a later --all run. The ratchet's own test
# asserts the walk never escapes the selection prefixes.
# Contract (e)/(c) ratchets (legacy-sync retirement, lane 14): the reason-label AST check scans every
# backend module's ``.labels(...)`` calls, and the batch-stage env ratchet scans the batch, enrichment,
# workers and outbox modules. A PR that adds a violation must fail in its own changed-file CI.
REASON_LABEL_ENUM_TESTS = ('tests/unit/test_reason_label_enums.py',)
BATCH_STAGE_ENV_RATCHET_TESTS = ('tests/unit/test_batch_stage_env_ratchet.py',)
BATCH_STAGE_ENV_RATCHET_PREFIXES = (
    'backend/utils/batch_pipeline/',
    'backend/database/batch_pipeline_',
    'backend/utils/enrichment/',
    'backend/utils/workers/',
    'backend/database/outbox',
)


def is_reason_label_scope_path(path: str) -> bool:
    return path.startswith('backend/') and path.endswith('.py') and not path.startswith('backend/tests/')


BACKGROUND_TASK_RATCHET_TESTS = (
    'tests/unit/test_background_task_ratchet.py',
    'tests/unit/test_revision_drain_harness.py',
)

# Shared with the canonical release manifest's named trigger. Do not copy the
# inventory's directory exclusions into a second set of workflow path globs.
FIRESTORE_INDEX_GUARD_CONTROL_PATHS = frozenset(
    {
        'backend/scripts/select_backend_unit_tests.py',
        'backend/scripts/run_firestore_index_guard.py',
        'backend/scripts/generate_firestore_indexes.py',
        'backend/firestore-guard-requirements.txt',
        'backend/openapi-requirements.txt',
        'backend/.python-version',
        'backend/pyproject.toml',
        'backend/test.sh',
        'backend/tests/conftest.py',
        'backend/tests/unit/conftest.py',
        'backend/tests/unit/memory_import_isolation.py',
        'backend/testing/hermetic_network.py',
    }
)


def is_firestore_index_guard_path(path: str) -> bool:
    path = normalize_changed_path(path)
    return (
        path in FIRESTORE_INDEX_GUARD_SCHEMA_PATHS
        or path in FIRESTORE_INDEX_GUARD_CONTROL_PATHS
        or path.startswith(FIRESTORE_INDEX_GUARD_SUPPORT_PREFIX)
        or path.startswith('backend/scripts/firestore_')
        and path.endswith('.py')
        or path.removeprefix('backend/') in FIRESTORE_INDEX_GUARD_TESTS
        or is_serving_query_inventory_path(path)
    )


AREA_TESTS = (
    (
        # Task-target routes whose expected retries must stay 409 (contract (d)). #22431 moved
        # FirstSummaryCallbackPending and a router edit could no longer see the stale EXPECTED_RETRIES
        # key: routers/batch_pipeline.py selected no route test. utils/enrichment/ stays unmapped on
        # purpose so it keeps the full-suite fallback (which includes these tests).
        ('backend/routers/batch_pipeline.py', 'backend/routers/sync.py', 'backend/utils/sync/reprocess.py'),
        (),
        (
            'tests/unit/test_batch_pipeline_serving.py',
            'tests/unit/test_sync_reprocess_coalesce.py',
            'tests/unit/test_sync_enrichment_*.py',
            'tests/unit/test_enrichment_route.py',
            'tests/unit/test_task_target_retry_semantics.py',
            'tests/unit/test_cloud_tasks_queue_model.py',
        ),
    ),
    (
        # Legacy-sync retirement shared stubs (lane 1); owners extend the test list.
        ('backend/utils/workers/', 'backend/utils/observability/reasons.py', 'backend/utils/rollout/'),
        (),
        (
            'tests/unit/test_workers_consumer_contract.py',
            'tests/unit/test_reason_label_enums.py',
            'tests/unit/test_runtime_percent.py',
            'tests/unit/test_ramp_controller.py',
        ),
    ),
    (
        (
            'backend/config/plan_catalog',
            'backend/scripts/generate_plan_catalog.py',
            'backend/models/users.py',
            'backend/utils/subscription.py',
            'backend/utils/subscription_state_machine.py',
            'backend/utils/overage.py',
            'backend/utils/fair_use.py',
            'backend/utils/sync/rate_limit.py',
            'backend/scripts/support/find_stripe_entitlement_mismatches.py',
            'backend/routers/payment.py',
            'backend/routers/retired_desktop_proactivity.py',
            'backend/database/phone_call_config.py',
        ),
        (),
        (
            'tests/unit/test_plan_catalog_contract.py',
            'tests/unit/test_subscription_*.py',
            'tests/unit/test_user_subscription_wire_contract.py',
            'tests/unit/test_stripe_*.py',
            'tests/unit/test_payment_price_id_validation.py',
            'tests/unit/test_chat_quota.py',
            'tests/unit/test_fair_use_*.py',
            'tests/unit/test_phone_call*.py',
            'tests/unit/test_desktop_proactivity.py',
            'tests/unit/test_sync_fair_use_gate.py',
        ),
    ),
    (
        (
            'backend/database/users.py',
            'backend/models/geolocation.py',
            'backend/models/users.py',
            'backend/routers/developer.py',
            'backend/routers/users.py',
            'backend/utils/retrieval/agentic.py',
            'backend/utils/retrieval/graph.py',
        ),
        (),
        ('tests/unit/test_location_context_consent.py', 'tests/unit/test_chat_async_offload.py'),
    ),
    (
        (
            'backend/database/csat.py',
            'backend/routers/csat.py',
        ),
        (),
        ('tests/unit/test_csat.py', 'tests/unit/test_desktop_rest_inventory.py'),
    ),
    (
        ('backend/llm_gateway/',),
        (),
        ('tests/unit/test_llm_gateway_*.py',),
    ),
    (
        ('backend/mcp/', 'backend/routers/mcp'),
        (),
        ('tests/unit/test_mcp_*.py', 'tests/unit/test_oauth_callback_uid_guard.py'),
    ),
    (
        (
            'backend/utils/stt/',
            'backend/config/prerecorded_stt',
            'backend/pusher/',
            'backend/routers/transcribe',
            'backend/routers/listen',
        ),
        (),
        (
            'tests/unit/test_*audio*.py',
            'tests/unit/test_*listen*.py',
            'tests/unit/test_parakeet_*.py',
            'tests/unit/test_*pusher*.py',
            'tests/unit/test_*speaker*.py',
            'tests/unit/test_*speech*.py',
            'tests/unit/test_*stt*.py',
            'tests/unit/test_*streaming*.py',
            'tests/unit/test_*sync*.py',
            'tests/unit/test_*transcribe*.py',
            'tests/unit/test_*vad*.py',
            'tests/unit/utils/test_listen_pusher_session.py',
        ),
    ),
    (
        ('backend/parakeet/',),
        (),
        ('tests/unit/test_parakeet_*.py',),
    ),
    (
        ('backend/scripts/verify_pusher_live_alert_route.py',),
        (),
        ('tests/unit/test_verify_pusher_live_alert_route.py',),
    ),
    (
        MONITORING_CONTRACT_SOURCES,
        (),
        (
            'tests/unit/test_monitoring_*.py',
            'tests/unit/test_journey_observability.py',
            'tests/unit/test_verify_pusher_live_alert_route.py',
        ),
    ),
    (
        ('backend/services/users/', 'backend/routers/users'),
        (),
        (
            'tests/services/users/test_*.py',
            'tests/routers/test_users.py',
            'tests/unit/test_users_*.py',
            'tests/unit/test_delete_account_*.py',
            'tests/unit/test_claim_deletion_*.py',
            'tests/unit/test_agent_vm_account_cleanup.py',
        ),
    ),
    (
        ('backend/routers/conversations', 'backend/services/conversations/', 'backend/utils/conversations'),
        (),
        (
            'tests/unit/test_conversation*.py',
            'tests/unit/test_conversations*.py',
            'tests/unit/test_folder_*.py',
            'tests/unit/test_retrieval_*.py',
        ),
    ),
    (
        ('backend/routers/memories', 'backend/services/memories/', 'backend/utils/memories'),
        (),
        ('tests/unit/test_memories_*.py', 'tests/unit/test_memory_*.py'),
    ),
    (
        ('backend/routers/action_items', 'backend/services/action_items/', 'backend/utils/action_items'),
        (),
        ('tests/unit/test_action_item*.py', 'tests/unit/test_dev_api_action_items_poison.py'),
    ),
    (
        ('backend/routers/payment', 'backend/services/payment/', 'backend/utils/payments'),
        (),
        (
            'tests/unit/test_payment_*.py',
            'tests/unit/test_stripe_*.py',
            'tests/unit/test_subscription_*.py',
            'tests/unit/test_available_plans_resilience.py',
            'tests/unit/test_trial_metadata.py',
            'tests/unit/test_paywall_reconnect_gate.py',
            'tests/unit/test_chat_quota.py',
        ),
    ),
    (
        ('backend/routers/apps', 'backend/services/apps/', 'backend/utils/apps'),
        (),
        ('tests/unit/test_apps_*.py', 'tests/unit/test_app_*.py', 'tests/unit/test_create_persona_user_none.py'),
    ),
    (
        ('backend/utils/social.py',),
        (),
        ('tests/unit/test_social_*.py',),
    ),
    (
        ('backend/routers/folders', 'backend/services/folders/', 'backend/utils/folders'),
        (),
        ('tests/unit/test_folder_*.py',),
    ),
    (
        ('backend/routers/developer', 'backend/services/developer/', 'backend/utils/developer'),
        (),
        ('tests/unit/test_dev_api_*.py', 'tests/unit/test_developer_*.py'),
    ),
    (
        ('backend/routers/sync', 'backend/services/sync/', 'backend/utils/sync'),
        (),
        ('tests/unit/test_sync_*.py', 'tests/unit/test_audio_merge_tasks.py'),
    ),
    (
        ('backend/routers/storage', 'backend/services/storage/', 'backend/utils/storage'),
        (),
        ('tests/unit/test_storage_*.py', 'tests/unit/test_file_upload*.py'),
    ),
    (
        ('backend/routers/notifications', 'backend/services/notifications/', 'backend/utils/notifications'),
        (),
        ('tests/unit/test_*notification*.py', 'tests/unit/test_mentor_notifications.py'),
    ),
    (
        ('backend/routers/twilio', 'backend/services/twilio/', 'backend/utils/twilio'),
        (),
        ('tests/unit/test_twilio_*.py', 'tests/unit/test_phone_*.py'),
    ),
    (
        ('backend/routers/geocoding', 'backend/services/geocoding/', 'backend/utils/geocoding'),
        (),
        ('tests/unit/test_*geocoding*.py', 'tests/unit/test_location_maps_status_guard.py'),
    ),
    (
        ('backend/routers/rate', 'backend/services/rate', 'backend/utils/rate'),
        (),
        ('tests/unit/test_rate_*.py',),
    ),
    (
        (
            'backend/database/users.py',
            'backend/database/csat.py',
        ),
        (),
        (
            'tests/unit/test_firestore_query_shapes.py',
            'tests/unit/test_firestore_index_rules.py',
            'tests/unit/test_firestore_shape_recorder.py',
        ),
    ),
    (
        # Cloud Tasks handler request paths: background work there must survive revision draining.
        # Superseded by the shared ratchet-scope guard in tests_for_changed_paths
        # (tests/support/background_task_ratchet_scope.py), which selects the
        # ratchet for *every* module the scanner walks, not just these seeds.
        (
            'backend/tests/unit/fixtures/revision_drain.py',
            'backend/tests/unit/fixtures/background_task_baseline.json',
        ),
        (),
        (
            'tests/unit/test_background_task_ratchet.py',
            'tests/unit/test_revision_drain_harness.py',
        ),
    ),
)


def discover_unit_tests() -> list[str]:
    tests: set[Path] = set()
    for root in FULL_TEST_ROOTS:
        tests.update(root.rglob('test_*.py'))
    for root in FULL_TEST_GLOBS:
        tests.update(root.glob('test_*.py'))
    return sorted(
        test_path
        for test_path in (_backend_relative(path) for path in tests if path.is_file())
        if test_path not in LEGACY_UNLISTED_TESTS
    )


def discover_all_tests() -> list[str]:
    """Unit tests plus workflow-contract extras (e2e) for PR path selection only."""
    tests = {Path(BACKEND_DIR / path) for path in discover_unit_tests()}
    for path in EXTRA_DISCOVERABLE_TESTS:
        if path.is_file():
            tests.add(path)
    return sorted(_backend_relative(path) for path in tests if path.is_file())


def _backend_relative(path: Path) -> str:
    return path.relative_to(BACKEND_DIR).as_posix()


def normalize_changed_path(path: str) -> str:
    path = path.strip()
    if not path:
        return ''
    path = path.replace('\\', '/')
    while path.startswith('./'):
        path = path[2:]
    return path


def is_full_run_path(path: str) -> bool:
    if path in NARROW_FULL_RUN_EXCEPTIONS:
        return False
    if path in FULL_RUN_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in FULL_RUN_PREFIXES):
        return True
    return any(path_matches(path, pattern) for pattern in FULL_RUN_GLOBS)


def is_selectable_backend_path(path: str) -> bool:
    """Return True for backend paths that can select or force unit tests.

    Docs, AGENTS, and most chart/dashboard artifacts are ignored so editing them
    does not trip the unmapped-path full-suite fallback. Monitoring telemetry
    contract sources (#9587) are an intentional exception so inventory/values
    drift still selects the monitoring unit contracts.
    """
    if not path.startswith('backend/'):
        return False
    if path.endswith('.md'):
        return False
    # Duration exemptions are not product sources. Treating this list as an
    # unmapped backend path would select the full unit suite on every edit.
    if path == 'backend/tests/fast_unit_duration_allowlist.txt':
        return False
    if path.startswith('backend/docs/'):
        return False
    if path.startswith('backend/charts/'):
        monitoring_contract_prefixes = MONITORING_CONTRACT_SOURCES
        return any(
            path == prefix or path.startswith(prefix) if prefix.endswith('/') else path == prefix
            for prefix in monitoring_contract_prefixes
        )
    return True


def path_matches(path: str, pattern: str) -> bool:
    if pattern.endswith('/**'):
        return path.startswith(pattern[:-3].rstrip('/') + '/')
    return PurePosixPath(path).match(pattern)


def is_memory_policy_core_path(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in MEMORY_POLICY_CORE_PATH_PREFIXES):
        return True
    return any(path_matches(path, pattern) for pattern in MEMORY_POLICY_CORE_PATH_GLOBS)


def load_workflow_contracts() -> List[Dict[str, Any]]:
    if not WORKFLOW_CONTRACTS_PATH.exists():
        return []
    data: object = json.loads(WORKFLOW_CONTRACTS_PATH.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        return []
    typed_data: Dict[str, Any] = cast(Dict[str, Any], data)
    workflows_raw: Any = typed_data.get('workflows', [])
    return cast(List[Dict[str, Any]], workflows_raw) if isinstance(workflows_raw, list) else []


def workflow_contract_tests_for_path(path: str, all_tests: List[str]) -> Set[str]:
    selected: Set[str] = set()
    for workflow in load_workflow_contracts():
        sources: Tuple[str, ...] = tuple(workflow.get('sources') or ())
        if not any(path_matches(path, source) for source in sources):
            continue
        tests_raw = workflow.get('tests') or ()
        selected.update(test for test in tests_raw if test in all_tests)
    return selected


def workflow_contract_matches_path(path: str) -> bool:
    for workflow in load_workflow_contracts():
        sources: Tuple[str, ...] = tuple(workflow.get('sources') or ())
        if any(path_matches(path, source) for source in sources):
            return True
    return False


def tests_for_changed_paths(changed_paths: list[str], all_tests: list[str]) -> tuple[list[str], str]:
    changed_paths = [path for path in (normalize_changed_path(path) for path in changed_paths) if path]
    if not changed_paths:
        return all_tests, 'no changed paths were provided'

    selected: set[str] = set()
    # Cross-cutting cap guard: a new model endpoint must declare a funded gate.
    # Keep this separate from AREA_TESTS so unknown sources retain full-suite fallback.
    if any(
        path.startswith(('backend/routers/', 'backend/utils/llm/'))
        or path
        in {
            'backend/utils/generated_compute.py',
            'backend/utils/funded_processing.py',
            'backend/docs/llm/model_endpoint_inventory.yaml',
        }
        for path in changed_paths
    ):
        selected.update(
            test for test in ('tests/unit/test_generated_compute_inventory_guardrails.py',) if test in all_tests
        )
    if any(is_firestore_index_guard_path(path) for path in changed_paths):
        selected.update(test for test in FIRESTORE_INDEX_GUARD_TESTS if test in all_tests)
    if any(is_background_task_ratchet_path(path) for path in changed_paths):
        selected.update(test for test in BACKGROUND_TASK_RATCHET_TESTS if test in all_tests)
    if any(is_reason_label_scope_path(path) for path in changed_paths):
        selected.update(test for test in REASON_LABEL_ENUM_TESTS if test in all_tests)
    if any(path.startswith(BATCH_STAGE_ENV_RATCHET_PREFIXES) for path in changed_paths):
        selected.update(test for test in BATCH_STAGE_ENV_RATCHET_TESTS if test in all_tests)
    backend_paths = [path for path in changed_paths if is_selectable_backend_path(path)]
    test_paths = [path for path in backend_paths if path.startswith('backend/tests/') and path.endswith('.py')]

    for path in changed_paths:
        selected.update(workflow_contract_tests_for_path(path, all_tests))

    for path in backend_paths:
        if is_full_run_path(path):
            return all_tests, f'{path} requires the full backend unit suite'

    for path in test_paths:
        backend_relative = path.removeprefix('backend/')
        if backend_relative in all_tests:
            selected.add(backend_relative)

    removed_or_unlisted_tests = [path for path in test_paths if path.removeprefix('backend/') not in all_tests]
    if removed_or_unlisted_tests:
        return all_tests, f'{removed_or_unlisted_tests[0]} was removed or is outside backend test discovery'

    mapped_backend_sources: set[str] = set()
    for path in backend_paths:
        if path in test_paths:
            continue
        if workflow_contract_matches_path(path):
            mapped_backend_sources.add(path)
        for source_prefixes, source_globs, test_globs in AREA_TESTS:
            if any(path.startswith(prefix) for prefix in source_prefixes) or any(
                path_matches(path, pattern) for pattern in source_globs
            ):
                mapped_backend_sources.add(path)
                selected.update(match_tests(all_tests, test_globs))

    if any(is_memory_policy_core_path(path) for path in backend_paths):
        mapped_backend_sources.update(path for path in backend_paths if is_memory_policy_core_path(path))
        selected.update(test for test in MEMORY_POLICY_CORE_TESTS if test in all_tests)

    unmapped_backend_sources = [
        path for path in backend_paths if path not in test_paths and path not in mapped_backend_sources
    ]
    if unmapped_backend_sources:
        return all_tests, f'{unmapped_backend_sources[0]} did not match a backend test-selection contract'

    if not backend_paths:
        if selected:
            return sorted(selected), 'selected backend unit tests from changed paths and workflow contracts'
        return [], 'no backend files changed'
    if selected:
        return sorted(selected), 'selected backend unit tests from changed paths and workflow contracts'
    return all_tests, 'backend changes did not match a narrow area'


def match_tests(all_tests: list[str], test_globs: tuple[str, ...]) -> set[str]:
    return {test for test in all_tests if any(fnmatch.fnmatch(test, pattern) for pattern in test_globs)}


def read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def existing_tests(paths: list[str], all_tests: list[str]) -> list[str]:
    all_test_set = set(all_tests)
    missing = [path for path in paths if path not in all_test_set]
    if missing:
        missing_list = ', '.join(missing)
        raise SystemExit(f'Selected backend unit tests do not exist: {missing_list}')
    return sorted(dict.fromkeys(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--all', action='store_true', help='print every backend unit test file')
    mode.add_argument('--changed-files', type=Path, help='file containing repo-relative changed paths')
    mode.add_argument('--from-test-list', type=Path, help='file containing backend-relative test paths')
    parser.add_argument('--output', type=Path, help='write selected tests to this file instead of stdout')
    parser.add_argument('--reason-output', type=Path, help='write the selection reason to this file')
    args = parser.parse_args()

    all_tests = discover_all_tests()
    reason = 'full backend unit suite'
    if args.all:
        selected = discover_unit_tests()
    elif args.from_test_list:
        selected = existing_tests(read_lines(args.from_test_list), all_tests)
        reason = 'using provided backend unit test list'
    else:
        selected, reason = tests_for_changed_paths(read_lines(args.changed_files), all_tests)

    output = '\n'.join(selected)
    if output:
        output += '\n'
    if args.output:
        args.output.write_text(output, encoding='utf-8', newline='\n')
    else:
        print(output, end='')
    if args.reason_output:
        args.reason_output.write_text(reason + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
