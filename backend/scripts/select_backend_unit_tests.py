#!/usr/bin/env python3
"""Select backend unit tests for either a full run or a changed-file PR run."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple, cast

import argparse
import fnmatch
import json
import os
import sys
import zlib
from pathlib import Path
from pathlib import PurePosixPath

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
WORKFLOW_CONTRACTS_PATH = BACKEND_DIR / 'testing' / 'workflow_contracts.json'
RUNTIME_IMAGES_PATH = BACKEND_DIR / 'runtime_images.json'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.support.firestore_serving_query_inventory import is_serving_query_inventory_path  # noqa: E402
from tests.support.background_task_ratchet_scope import is_background_task_ratchet_path  # noqa: E402
from tests.support.sync_legacy_ratchet_scope import is_sync_legacy_ratchet_path  # noqa: E402
from scripts.backend_import_graph import ImportGraph, cached_import_graph  # noqa: E402

# Kill switch for import-graph selection: on unless set to 0/false/off. Off
# restores the pre-graph behaviour exactly (every graph-eligible path forces
# the full suite again). CI passes the repository variable of the same name.
GRAPH_SELECTION_ENV = 'BACKEND_UNIT_GRAPH_SELECTION'


def graph_selection_enabled() -> bool:
    return os.environ.get(GRAPH_SELECTION_ENV, '1').strip().lower() not in {'0', 'false', 'off', 'no'}


def import_graph() -> ImportGraph:
    return cached_import_graph(BACKEND_DIR)


FULL_TEST_ROOTS = (
    BACKEND_DIR / 'tests' / 'unit',
    BACKEND_DIR / 'tests' / 'services',
    BACKEND_DIR / 'tests' / 'routers',
    BACKEND_DIR / 'scripts' / 'jobstore_operator' / 'tests',
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
    'backend/scripts/backend_import_graph.py',
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
    'backend/charts/monitoring/core-features/recording-rules.yaml',
    'backend/charts/backend-secrets/',
    'backend/charts/monitoring/prometheus-adapter/',
    'backend/scripts/diff_prod_adapter.py',
    'backend/charts/parakeet/',
    'backend/charts/backend-listen/',
    'backend/charts/pusher/',
    'backend/charts/vad/',
    'backend/charts/diarizer/',
    'backend/charts/nllb-translation/',
    'backend/charts/batch-pipeline-worker/',
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

# Batch census completeness guard (W3 / SCA-1921): a new job/projection state or
# an unregistered reason vocabulary must fail the PR that adds it, not only the
# post-merge ``--all`` run. The scanned writer sites and vocabularies live in
# config/batch_census.py and tests/unit/test_batch_census_registry.py; selection
# uses their prefixes so an edit to any registered writer or enum always runs the
# guard. ``backend/config/batch_census.py`` is not otherwise mapped to a narrow
# area, so it selects its importers through the import graph.
CENSUS_GUARD_TESTS = ('tests/unit/test_batch_census_registry.py',)
CENSUS_GUARD_PREFIXES = (
    'backend/utils/batch_pipeline/',
    'backend/database/batch_pipeline_',
    'backend/utils/observability/reasons.py',
    'backend/config/batch_census.py',
    'backend/config/batch_census_selectors.py',
    'backend/database/jobstore/',
    'backend/tests/support/batch_census_sql_selectors.py',
    'backend/scripts/batch_pipeline_poll_state_census.py',
)
# Census exporter (W3 / SCA-2119): a change to the sampler, the gauge families or
# the scheduler glue must run the exporter contract in the same PR. The registry
# entry already runs the completeness guard above.
CENSUS_EXPORT_TESTS = ('tests/unit/test_batch_census_export.py',)
CENSUS_EXPORT_PREFIXES = (
    'backend/database/batch_census_export.py',
    'backend/utils/observability/batch_census.py',
    'backend/utils/sync/batch_census.py',
    'backend/scripts/generate_batch_census_alerts.py',
)
BATCH_STAGE_ENV_RATCHET_PREFIXES = (
    'backend/utils/batch_pipeline/',
    'backend/database/batch_pipeline_',
    'backend/utils/enrichment/',
    'backend/utils/workers/',
    'backend/database/outbox',
)


# Flag budget (ADR 0006): a new env read anywhere in the pipeline env surface, or an edit to the
# allowlist itself, must fail in its own changed-file CI. tests/unit/test_flag_budget.py asserts these
# prefixes cover its SCOPE.
FLAG_BUDGET_TESTS = ('tests/unit/test_flag_budget.py',)
FLAG_BUDGET_PREFIXES = (
    'backend/utils/pusher_audio_projection.py',
    'backend/utils/batch_pipeline/',
    'backend/diarizer/batch_pipeline',
    'backend/config/batch_pipeline',
    'backend/config/batch_language_recovery.py',
    'backend/config/listen_reconnect.py',
    'backend/utils/sync/',
    'backend/utils/stt/',
    'backend/config/policy/',
    'backend/config/prerecorded_',
    'backend/config/live_stt_',
    'backend/config/transcription_final_pass.py',
    'backend/config/flag_budget.json',
    'backend/parakeet/language_gate.py',
)


def is_reason_label_scope_path(path: str) -> bool:
    return path.startswith('backend/') and path.endswith('.py') and not path.startswith('backend/tests/')


BACKGROUND_TASK_RATCHET_TESTS = (
    'tests/unit/test_background_task_ratchet.py',
    'tests/unit/test_revision_drain_harness.py',
)

# Legacy-sync import ratchet: no new importer of the retiring legacy sync
# modules (plan C class (a)) may slip past changed-file CI and only fail the
# post-merge --all run. Selection uses the shared scope predicate
# (tests/support/sync_legacy_ratchet_scope.py) so the ratchet runs for every
# importer path its walk can scan, mirroring the background-task ratchet.
# Only the ratchet itself: test_workflow_contracts.py stays out of this
# cross-cutting set — it covers the background-task ratchet and other
# workflows, and is selected by its own declared contract sources
# (testing/workflow_contracts.json) plus the backend/testing/ full-run prefix.
SYNC_LEGACY_RATCHET_TESTS = ('tests/unit/test_sync_legacy_import_ratchet.py',)

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
        'backend/config/batch_census_selectors.py',
        'backend/tests/support/batch_census_selector_guard.py',
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


LIFECYCLE_INVARIANT_TESTS = (
    'tests/unit/test_lifecycle_state_table_writers.py',
    'tests/unit/test_lifecycle_invariants.py',
)
LIFECYCLE_SOURCE_REGRESSION_TESTS = {
    'backend/utils/batch_pipeline/scheduler.py': ('tests/unit/test_batch_pipeline_scheduler.py',),
    'backend/utils/fair_use.py': ('tests/unit/test_lifecycle_ladder_properties.py',),
    'backend/database/fair_use.py': ('tests/unit/test_lifecycle_ladder_properties.py',),
}

AREA_TESTS = (
    # Isolated-router tests stub google.cloud.firestore_v1 as a non-package and load routers.conversations
    # (or process_conversation) fresh. A module-level import added to these four modules can break them
    # without the import graph selecting them (main red after #25734, fixed by #25739). Other modules on
    # that chain are not mapped here.
    (
        (
            'backend/database/conversations_v3.py',
            'backend/database/conversations_v3_processing.py',
            'backend/database/home_feed_writer.py',
            'backend/database/home_feed_fields.py',
        ),
        (),
        (
            'tests/unit/test_conversations_date_range_validation.py',
            'tests/unit/test_conversations_merge_duplicate_guard.py',
            'tests/unit/test_dev_api_lock_bypass.py',
            'tests/unit/test_lock_bypass_fixes.py',
            'tests/unit/test_recovery_rule_skip.py',
            'tests/unit/test_client_processing_finalize.py',
            'tests/unit/test_process_conversation_duplicate_capture.py',
        ),
    ),
    (
        ('backend/scripts/jobstore_operator/',),
        (),
        ('scripts/jobstore_operator/tests/test_*.py',),
    ),
    # Source-effective lever declarations and expiry metadata share the existing unit lane.
    (
        (
            'backend/config/firestore_read_levers.py',
            'backend/deploy/runtime_env/',
            'backend/deploy/runtime_env.yaml',
            'backend/deploy/compose_runtime_env.py',
            'backend/deploy/generate_read_lever_manifest.py',
            'backend/deploy/firestore_read_levers_manifest.json',
            'backend/charts/batch-pipeline-worker/',
            'backend/charts/backend-listen/',
            'backend/charts/pusher/',
        ),
        (),
        (
            'tests/unit/test_backend_runtime_env_validator.py',
            'tests/unit/test_batch_pipeline_chart.py',
            'tests/unit/test_config_train.py',
            'tests/unit/test_runtime_env_sources.py',
        ),
    ),
    (
        (
            'backend/utils/conversations/',
            'backend/utils/batch_pipeline/',
            'backend/database/record_audio.py',
            'backend/database/record_partial.py',
            'backend/database/conversation_finalization_jobs.py',
            'backend/database/episodes.py',
            'backend/database/episode_timeline.py',
            'backend/utils/episodes/',
            'backend/utils/fair_use.py',
            'backend/database/fair_use.py',
            'backend/utils/sync/assignment.py',
            'backend/utils/sync/bridge_pending.py',
            'backend/tests/support/lifecycle_state_table.py',
            'backend/charts/monitoring/alerts/',
        ),
        ('backend/database/batch_pipeline_*.py',),
        LIFECYCLE_INVARIANT_TESTS,
    ),
    (
        ('backend/charts/incluster-guards/',),
        (
            'backend/charts/monitoring/prometheus-adapter/*_omi_prometheus_adapter.yaml',
            'backend/charts/parakeet/*_omi_parakeet_values.yaml',
        ),
        (
            'tests/unit/test_incluster_guards.py',
            'tests/unit/test_gpu_fleet_retirement.py',
            'tests/unit/test_streaming_gpu_teardown.py',
        ),
    ),
    (('backend/config/flag_budget.json',), (), FLAG_BUDGET_TESTS),
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
            'tests/unit/test_firestore_unattributed_reads_alert.py',
            'tests/unit/test_timeliness_metrics_are_scraped.py',
            'tests/unit/test_serving_podmonitoring_chart.py',
            'tests/unit/test_firestore_attribution_charts.py',
            'tests/unit/test_backend_secrets_chart.py',
            'tests/unit/test_batch_pipeline_chart.py',
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
        ('tests/unit/test_*notification*.py',),
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


def is_prefix_only_full_run_path(path: str) -> bool:
    """True when only a blanket FULL_RUN_PREFIXES entry forces the full suite.

    Explicit cross-cutting paths (FULL_RUN_PATHS, FULL_RUN_GLOBS) keep forcing
    it: they are build inputs or entry points whose effect is not an import.
    """
    if path in FULL_RUN_PATHS or any(path_matches(path, pattern) for pattern in FULL_RUN_GLOBS):
        return False
    return any(path.startswith(prefix) for prefix in FULL_RUN_PREFIXES)


def is_graph_resolvable_path(path: str) -> bool:
    """A present, parseable backend module the import graph can follow.

    Deleted, renamed-away, non-Python and unparseable inputs return False so
    their callers keep the full-suite fallback: the graph cannot see who
    depended on a module that no longer exists, or on a data file.
    """
    if not graph_selection_enabled() or not path.startswith('backend/') or not path.endswith('.py'):
        return False
    if not (REPO_DIR / path).is_file():
        return False
    relative = path.removeprefix('backend/')
    graph = import_graph()
    return graph.module_for_path(relative) is not None and relative not in graph.unparseable


def is_undiscovered_test_file(path: str) -> bool:
    name = path.rsplit('/', 1)[-1]
    return path.startswith(('backend/tests/', 'backend/testing/')) and name.startswith('test_') and name.endswith('.py')


def is_referenced_data_path(path: str, all_tests: list[str]) -> bool:
    """A present non-Python backend file that some test reaches by naming it.

    Only unmapped data files use this. Blanket full-run prefixes, explicit
    full-run paths, and files nothing names (directory scans, globs) keep the
    full-suite fallback.
    """
    if not graph_selection_enabled() or not path.startswith('backend/') or path.endswith('.py'):
        return False
    if is_full_run_path(path) or not (REPO_DIR / path).is_file():
        return False
    return bool(import_graph().dependent_tests(path.removeprefix('backend/'), all_tests))


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
    if path.startswith('backend/charts/incluster-guards/'):
        return True
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


def deployment_workflow_contract_errors(
    registry: dict[str, Any], contracts: list[dict[str, Any]], all_tests: list[str]
) -> list[str]:
    """Require explicit, executable selector coverage of the deployment registry.

    #25261 changed a deploy workflow without selecting its contract test;
    #25272 repaired that instance. Wildcard contracts cannot cover new entries.
    """
    workflows = {path for image in registry['images'] for path in image.get('deployment_workflows', [])} | {
        path
        for service in registry['services'].values()
        for path in service.get('current_deploy', [])
        if path.startswith('.github/workflows/')
    }
    discovered = set(all_tests)
    errors = []
    for path in sorted(workflows):
        exact_contracts = [contract for contract in contracts if path in (contract.get('sources') or [])]
        if not exact_contracts:
            errors.append(f'{path}: registered deployment workflow has no exact-path workflow contract')
        elif not any(discovered.intersection(contract.get('tests') or []) for contract in exact_contracts):
            errors.append(f'{path}: exact-path workflow contracts select no existing discovered backend tests')
        elif not (REPO_DIR / path).is_file():
            errors.append(f'{path}: registered deployment workflow does not exist; update registry and exact mapping')
    return errors


def workflow_contract_matches_path(path: str) -> bool:
    for workflow in load_workflow_contracts():
        sources: Tuple[str, ...] = tuple(workflow.get('sources') or ())
        if any(path_matches(path, source) for source in sources):
            return True
    return False


def tests_for_changed_paths(
    changed_paths: list[str], all_tests: list[str], *, allow_full_suite: bool = True
) -> tuple[list[str], str]:
    changed_paths = [path for path in (normalize_changed_path(path) for path in changed_paths) if path]
    if not changed_paths:
        return (all_tests if allow_full_suite else []), 'no changed paths were provided'

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
    # Add the timeliness contract without classifying an otherwise-unmapped
    # producer/deploy edit as narrow: retain its existing full-suite fallback.
    if any(
        path.startswith(('backend/utils/batch_pipeline/', 'backend/database/batch_pipeline_'))
        or path == 'backend/deploy/cloud_run_gmp_sync.yaml'
        for path in changed_paths
    ):
        selected.update(
            test
            for test in (
                'tests/unit/test_timeliness_metrics_are_scraped.py',
                'tests/unit/test_enrichment_llm_cost_metrics_are_scraped.py',
            )
            if test in all_tests
        )
    if any(is_firestore_index_guard_path(path) for path in changed_paths):
        selected.update(test for test in FIRESTORE_INDEX_GUARD_TESTS if test in all_tests)
    if any(is_background_task_ratchet_path(path) for path in changed_paths):
        selected.update(test for test in BACKGROUND_TASK_RATCHET_TESTS if test in all_tests)
    if any(is_reason_label_scope_path(path) for path in changed_paths):
        selected.update(test for test in REASON_LABEL_ENUM_TESTS if test in all_tests)
    # The AST inventory also discovers a new writer in a previously unrelated
    # module. Keep the source fallback unchanged while always running its guard.
    if any(path.startswith(('backend/database/', 'backend/utils/')) and path.endswith('.py') for path in changed_paths):
        selected.update(test for test in LIFECYCLE_INVARIANT_TESTS if test in all_tests)
    if any(path.startswith('backend/') and path.endswith('.py') for path in changed_paths):
        selected.update(
            test
            for test in (
                'tests/unit/test_lifecycle_state_table_writers.py',
                'tests/unit/test_batch_account_authority_writers.py',
            )
            if test in all_tests
        )
    for path in changed_paths:
        selected.update(test for test in LIFECYCLE_SOURCE_REGRESSION_TESTS.get(path, ()) if test in all_tests)
    if any(is_sync_legacy_ratchet_path(path) for path in changed_paths):
        selected.update(test for test in SYNC_LEGACY_RATCHET_TESTS if test in all_tests)
    if any(path.startswith(CENSUS_GUARD_PREFIXES) for path in changed_paths):
        selected.update(test for test in CENSUS_GUARD_TESTS if test in all_tests)
    if any(path.startswith(CENSUS_EXPORT_PREFIXES) for path in changed_paths):
        selected.update(test for test in CENSUS_EXPORT_TESTS if test in all_tests)
    if any(path.startswith(BATCH_STAGE_ENV_RATCHET_PREFIXES) for path in changed_paths):
        selected.update(test for test in BATCH_STAGE_ENV_RATCHET_TESTS if test in all_tests)
    if any(path.startswith(FLAG_BUDGET_PREFIXES) for path in changed_paths):
        selected.update(test for test in FLAG_BUDGET_TESTS if test in all_tests)
    backend_paths = [path for path in changed_paths if is_selectable_backend_path(path)]
    test_paths = [path for path in backend_paths if path.startswith('backend/tests/') and path.endswith('.py')]

    for path in changed_paths:
        selected.update(workflow_contract_tests_for_path(path, all_tests))

    # Paths the import graph selects for instead of the full suite. Each one is
    # still also run through the contract and area mappings below (union).
    graph_paths: list[str] = []
    for path in backend_paths:
        if allow_full_suite and is_full_run_path(path):
            if is_prefix_only_full_run_path(path) and is_graph_resolvable_path(path):
                graph_paths.append(path)
                continue
            return all_tests, f'{path} requires the full backend unit suite'

    for path in test_paths:
        backend_relative = path.removeprefix('backend/')
        if backend_relative in all_tests:
            selected.add(backend_relative)

    removed_or_unlisted_tests = [path for path in test_paths if path.removeprefix('backend/') not in all_tests]
    if allow_full_suite:
        # Support modules, fixtures and helpers under backend/tests/ are not
        # discovered tests, but the tests that import them are. A deleted
        # test-tree module keeps the full-suite fallback.
        unresolved = [path for path in removed_or_unlisted_tests if not is_graph_resolvable_path(path)]
        if unresolved:
            return all_tests, f'{unresolved[0]} was removed or is outside backend test discovery'
        graph_paths.extend(removed_or_unlisted_tests)

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
                # These are additive guards. They cannot turn a previously
                # unmapped implementation path into a narrow two-file suite.
                if test_globs != LIFECYCLE_INVARIANT_TESTS:
                    mapped_backend_sources.add(path)
                selected.update(match_tests(all_tests, test_globs))

    if any(is_memory_policy_core_path(path) for path in backend_paths):
        mapped_backend_sources.update(path for path in backend_paths if is_memory_policy_core_path(path))
        selected.update(test for test in MEMORY_POLICY_CORE_TESTS if test in all_tests)

    unmapped_backend_sources = [
        path
        for path in backend_paths
        if path not in test_paths and path not in mapped_backend_sources and path not in graph_paths
    ]
    if allow_full_suite and unmapped_backend_sources:
        unresolved = [
            path
            for path in unmapped_backend_sources
            if not is_graph_resolvable_path(path) and not is_referenced_data_path(path, all_tests)
        ]
        if unresolved:
            return all_tests, f'{unresolved[0]} did not match a backend test-selection contract'
        graph_paths.extend(unmapped_backend_sources)

    graph_skipped_only = False
    if graph_paths:
        graph = import_graph()
        resolved: list[str] = []
        for path in graph_paths:
            dependents = graph.dependent_tests(path.removeprefix('backend/'), all_tests)
            if not dependents and is_undiscovered_test_file(path):
                # An integration or e2e test outside unit discovery that no
                # unit test imports: its own workflow runs it.
                continue
            if not dependents and allow_full_suite:
                # Nothing imports or names it: a guard-only selection would
                # be a silent gap, so this path still runs everything.
                return all_tests, f'{path} has no import-graph dependents'
            selected.update(dependents)
            resolved.append(path)
        if any(path.endswith('.py') for path in resolved):
            # Ratchets that scan source trees see every module without importing it.
            selected.update(graph.tree_scan_tests(all_tests))
        graph_skipped_only = not resolved

    if not backend_paths:
        if selected:
            return sorted(selected), 'selected backend unit tests from changed paths and workflow contracts'
        return [], 'no backend files changed'
    if graph_skipped_only and not unmapped_backend_sources:
        # Any guard tests already selected (lifecycle writers, contracts) still run.
        return (
            sorted(selected),
            'only integration/e2e test files outside unit discovery changed; their own workflows run them',
        )
    if selected:
        if graph_paths:
            return sorted(selected), (
                'selected backend unit tests from changed paths, workflow contracts and the import graph '
                f'({len(graph_paths)} path(s) resolved by import graph, e.g. {graph_paths[0]})'
            )
        return sorted(selected), 'selected backend unit tests from changed paths and workflow contracts'
    return (all_tests if allow_full_suite else []), 'backend changes did not match a narrow area'


def focused_tests_for_changed_paths(changed_paths: list[str], all_tests: list[str]) -> list[str]:
    """Keep known affected contracts even when another path requires broad CI.

    Contracts precede directly changed tests so a bounded local run cannot lose
    them to a large test-only diff. Each group is stable and deduplicated. This
    is only pre-push feedback; the ordinary selector retains full-suite fallbacks.
    """
    selected, _ = tests_for_changed_paths(changed_paths, all_tests, allow_full_suite=False)
    changed_tests = {normalize_changed_path(path).removeprefix('backend/') for path in changed_paths}
    return sorted(set(selected) - changed_tests) + sorted(set(selected) & changed_tests)


def rotation_slice(test: str, total: int) -> int:
    """Stable slice index for a test path; independent of suite order and growth."""
    return zlib.crc32(test.encode('utf-8')) % total


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
    mode.add_argument('--check-deployment-contracts', action='store_true', help='validate deployment selector coverage')
    parser.add_argument('--output', type=Path, help='write selected tests to this file instead of stdout')
    parser.add_argument('--reason-output', type=Path, help='write the selection reason to this file')
    parser.add_argument(
        '--focused-output', type=Path, help='write affected contracts then changed tests for bounded pre-push'
    )
    parser.add_argument(
        '--rotation',
        help=(
            'K/N: also select every full-suite test in rotating slice K of N (stable crc32 of the path). '
            'Main pushes use this so the whole suite is covered across N runs, not on every run. The slices '
            'partition exactly what --all runs; contract-only extras such as the canonical-memory e2e are '
            'outside --all and are selected by their contracts instead.'
        ),
    )
    args = parser.parse_args()
    if args.focused_output and not args.changed_files:
        parser.error('--focused-output requires --changed-files')
    rotation: tuple[int, int] | None = None
    if args.rotation:
        try:
            slice_text, total_text = args.rotation.split('/', 1)
            rotation = (int(slice_text), int(total_text))
        except ValueError:
            parser.error('--rotation must be K/N with integers')
        if rotation[1] < 1 or not 0 <= rotation[0] < rotation[1]:
            parser.error('--rotation needs N >= 1 and 0 <= K < N')

    all_tests = discover_all_tests()
    errors = deployment_workflow_contract_errors(
        json.loads(RUNTIME_IMAGES_PATH.read_text(encoding='utf-8')), load_workflow_contracts(), all_tests
    )
    if errors:
        raise SystemExit('\n'.join(errors))
    if args.check_deployment_contracts:
        print('Deployment workflow selector contracts passed.')
        return
    reason = 'full backend unit suite'
    if args.all:
        selected = discover_unit_tests()
    elif args.from_test_list:
        selected = existing_tests(read_lines(args.from_test_list), all_tests)
        reason = 'using provided backend unit test list'
    else:
        changed_paths = read_lines(args.changed_files)
        selected, reason = tests_for_changed_paths(changed_paths, all_tests)
        if args.focused_output:
            focused = focused_tests_for_changed_paths(changed_paths, all_tests)
            args.focused_output.write_text(''.join(test + '\n' for test in focused), encoding='utf-8', newline='\n')

    if rotation is not None and not args.all:
        slice_index, slice_total = rotation
        rotated = [test for test in discover_unit_tests() if rotation_slice(test, slice_total) == slice_index]
        before = len(set(selected))
        selected = sorted(set(selected) | set(rotated))
        reason = (
            f'{reason}; plus rotating full-suite slice {slice_index}/{slice_total} (+{len(selected) - before} files)'
        )

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
