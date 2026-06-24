"""WS-G additive module alias shims — import parity only."""

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_g_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    ensure_utils_memory_packages_importable()
    install_database_client_stub()
    yield
    restore_sys_modules(saved)


def test_product_memory_alias_reexports_match_v17():
    from models import product_memory, v17_product_memory

    assert product_memory.MemoryItemStatus is v17_product_memory.MemoryItemStatus
    assert product_memory.MemoryTier is v17_product_memory.MemoryTier
    assert product_memory.MemoryLayer is v17_product_memory.MemoryLayer
    assert product_memory.MemoryLayer is product_memory.MemoryTier
    assert product_memory.MemoryItem is v17_product_memory.MemoryItem
    assert product_memory.V17MemoryItem is v17_product_memory.V17MemoryItem
    assert product_memory.MemoryItem is product_memory.V17MemoryItem
    assert product_memory.MemoryItemAlias is v17_product_memory.MemoryItemAlias
    assert product_memory.V17MemoryItemAlias is v17_product_memory.V17MemoryItemAlias
    assert product_memory.MemoryItemAlias is product_memory.V17MemoryItemAlias


def test_memory_contracts_alias_reexports_match_v17():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.LifecycleState is v17_memory_contracts.LifecycleState
    assert memory_contracts.DurablePatchDecision is v17_memory_contracts.DurablePatchDecision
    assert memory_contracts.deterministic_contract_id is v17_memory_contracts.deterministic_contract_id


def test_memory_contracts_l1_l2_symbol_aliases_are_identity():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.WorkingObservation is v17_memory_contracts.WorkingMemoryObservation
    assert memory_contracts.WorkingObservationArchiveItem is v17_memory_contracts.L1MemoryArchiveItem
    assert memory_contracts.PromotionRoute is v17_memory_contracts.L2MemoryRoute


def test_working_memory_batch_alias_is_identity():
    from utils.llm.working_memory import L1MemoryArchiveItems, WorkingObservationBatch

    assert L1MemoryArchiveItems is WorkingObservationBatch


def test_l2_memory_route_response_alias_is_identity():
    from utils.llm.l2_memory_routes import L2MemoryRouteResponse, PromotionRouteResponse

    assert L2MemoryRouteResponse is PromotionRouteResponse


def test_memory_contracts_durable_patch_fact_source_aliases():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE == "durable_memory_patch"
    assert memory_contracts.V17_DURABLE_MEMORY_PATCH_FACT_SOURCE is memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE
    assert v17_memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE is memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE


def test_memory_collections_alias_reexports_match_v17():
    from database import memory_collections, v17_collections

    assert memory_collections.V17Collections is v17_collections.V17Collections
    assert memory_collections.MemoryCollections is v17_collections.V17Collections
    assert v17_collections.V17Collections is memory_collections.MemoryCollections


def test_memory_collections_neutral_symbols_are_canonical():
    from database import memory_collections

    assert memory_collections.V17Collections is memory_collections.MemoryCollections


def test_memory_collections_frozen_path_strings_unchanged():
    from database.memory_collections import MemoryCollections

    paths = MemoryCollections(uid="uid-test")
    assert paths.memory_items == "users/uid-test/memory_items"
    assert paths.memory_operations == "users/uid-test/memory_operations"
    assert paths.memory_outbox == "users/uid-test/memory_outbox"
    assert paths.memory_control_state == "users/uid-test/memory_control/state"
    assert paths.memory_lineage == "users/uid-test/memory_lineage"
    assert paths.memory_evidence == "users/uid-test/memory_evidence"
    assert paths.memory_runs == "users/uid-test/memory_runs"
    assert paths.non_active_memory_routes == "users/uid-test/non_active_memory_routes"
    assert paths.short_term_lifecycle_transitions == "users/uid-test/short_term_lifecycle_transitions"
    assert paths.legacy_fallback == "users/uid-test/memory_legacy_fallback"
    assert paths.memory_commits == "users/uid-test/memory_commits"
    assert paths.memory_state_head == "users/uid-test/memory_state/head"
    assert paths.v3_compatibility_projection_state == "users/uid-test/v3_compatibility_projection/state"
    assert paths.v3_compatibility_projection_items == "users/uid-test/v3_compatibility_projection_items"


def test_memory_apply_store_alias_reexports_match_v17():
    from database import memory_apply_store, v17_memory_apply_store

    assert memory_apply_store.MemoryFirestoreApplyError is v17_memory_apply_store.V17FirestoreApplyError
    assert memory_apply_store.V17FirestoreApplyError is v17_memory_apply_store.V17FirestoreApplyError
    assert memory_apply_store.MissingV17Document is v17_memory_apply_store.MissingV17Document
    assert memory_apply_store.apply_long_term_patch_firestore is v17_memory_apply_store.apply_long_term_patch_firestore
    assert memory_apply_store.atomic_bump_source_generation is v17_memory_apply_store.atomic_bump_source_generation


def test_memory_apply_store_neutral_symbols_are_canonical():
    from database import memory_apply_store

    assert memory_apply_store.V17FirestoreApplyError is memory_apply_store.MemoryFirestoreApplyError


def test_memory_vector_metadata_alias_reexports_match_v17():
    from database import memory_vector_metadata, v17_vector_metadata

    assert (
        memory_vector_metadata.V17_MEMORY_VECTOR_SCHEMA_VERSION is v17_vector_metadata.V17_MEMORY_VECTOR_SCHEMA_VERSION
    )
    assert memory_vector_metadata.V17_MEMORY_VECTOR_ID_PREFIX is v17_vector_metadata.V17_MEMORY_VECTOR_ID_PREFIX
    assert memory_vector_metadata.RESTRICTED_SENSITIVITY_LABELS is v17_vector_metadata.RESTRICTED_SENSITIVITY_LABELS
    assert memory_vector_metadata.ParsedV17VectorHit is v17_vector_metadata.ParsedV17VectorHit
    assert (
        memory_vector_metadata.deterministic_v17_memory_vector_id
        is v17_vector_metadata.deterministic_v17_memory_vector_id
    )
    assert (
        memory_vector_metadata.build_v17_memory_vector_metadata is v17_vector_metadata.build_v17_memory_vector_metadata
    )
    assert (
        memory_vector_metadata.build_v17_default_memory_vector_filter
        is v17_vector_metadata.build_v17_default_memory_vector_filter
    )
    assert (
        memory_vector_metadata.build_v17_archive_memory_vector_filter
        is v17_vector_metadata.build_v17_archive_memory_vector_filter
    )
    assert memory_vector_metadata.parse_v17_search_vector_hit is v17_vector_metadata.parse_v17_search_vector_hit
    assert memory_vector_metadata.MEMORY_VECTOR_SCHEMA_VERSION is v17_vector_metadata.MEMORY_VECTOR_SCHEMA_VERSION
    assert memory_vector_metadata.build_memory_vector_metadata is v17_vector_metadata.build_memory_vector_metadata
    assert (
        memory_vector_metadata.build_default_memory_vector_filter
        is v17_vector_metadata.build_default_memory_vector_filter
    )
    assert (
        memory_vector_metadata.build_archive_memory_vector_filter
        is v17_vector_metadata.build_archive_memory_vector_filter
    )
    assert memory_vector_metadata.parse_memory_search_vector_hit is v17_vector_metadata.parse_memory_search_vector_hit


def test_memory_rollout_alias_reexports_match_v17():
    from config import memory_rollout, v17_memory

    assert memory_rollout.V17Mode is v17_memory.V17Mode
    assert memory_rollout.V17RolloutConfig is v17_memory.V17RolloutConfig
    assert memory_rollout.V17Capabilities is v17_memory.V17Capabilities
    assert memory_rollout.parse_enabled_users is v17_memory.parse_enabled_users
    assert memory_rollout.rollout_mode_env_value is v17_memory.rollout_mode_env_value
    assert memory_rollout.rollout_enabled_users_env_raw is v17_memory.rollout_enabled_users_env_raw
    assert v17_memory.V17Mode is memory_rollout.MemoryRolloutMode
    assert v17_memory.V17RolloutConfig is memory_rollout.MemoryRolloutConfig
    assert v17_memory.V17Capabilities is memory_rollout.MemoryRolloutCapabilities
    assert v17_memory.V17RolloutState is memory_rollout.MemoryRolloutState
    assert v17_memory.V17StageGate is memory_rollout.MemoryRolloutStageGate


def test_memory_rollout_neutral_symbols_are_canonical():
    from config import memory_rollout

    assert memory_rollout.V17Mode is memory_rollout.MemoryRolloutMode
    assert memory_rollout.V17RolloutConfig is memory_rollout.MemoryRolloutConfig
    assert memory_rollout.V17RolloutState is memory_rollout.MemoryRolloutState
    assert memory_rollout.V17Capabilities is memory_rollout.MemoryRolloutCapabilities
    assert memory_rollout.V17StageGate is memory_rollout.MemoryRolloutStageGate


def test_rollout_mode_env_dual_read_legacy_only():
    from config.v17_memory import V17Mode, rollout_mode_env_value

    assert rollout_mode_env_value({"V17_MODE": "read"}) == "read"
    assert V17Mode(rollout_mode_env_value({"V17_MODE": "read"})) == V17Mode.read


def test_rollout_mode_env_dual_read_neutral_precedence(monkeypatch):
    from config.v17_memory import V17Mode, V17RolloutConfig, rollout_mode_env_value

    monkeypatch.setenv("V17_MODE", "shadow")
    monkeypatch.setenv("MEMORY_MODE", "read")
    assert rollout_mode_env_value() == "read"
    assert V17RolloutConfig.from_env().mode == V17Mode.read


def test_rollout_enabled_users_env_dual_read_legacy_only(monkeypatch):
    from config.v17_memory import V17RolloutConfig, rollout_enabled_users_env_raw

    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)
    monkeypatch.setenv("V17_MEMORY_ENABLED_USERS", "uid-a,uid-b")
    assert rollout_enabled_users_env_raw() == "uid-a,uid-b"
    assert V17RolloutConfig.from_env().enabled_users == {"uid-a", "uid-b"}


def test_rollout_enabled_users_env_dual_read_neutral_precedence(monkeypatch):
    from config.v17_memory import V17RolloutConfig, rollout_enabled_users_env_raw

    monkeypatch.setenv("V17_MEMORY_ENABLED_USERS", "legacy-only")
    monkeypatch.setenv("MEMORY_ENABLED_USERS", "neutral-only")
    assert rollout_enabled_users_env_raw() == "neutral-only"
    assert V17RolloutConfig.from_env().enabled_users == {"neutral-only"}


def test_rollout_env_dual_read_does_not_use_canonical_cohort(monkeypatch):
    from config.v17_memory import V17RolloutConfig
    from utils.memory.memory_system import resolve_memory_system, MemorySystem

    monkeypatch.delenv("V17_MODE", raising=False)
    monkeypatch.delenv("V17_MEMORY_ENABLED_USERS", raising=False)
    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)
    monkeypatch.setenv("MEMORY_CANONICAL_USERS", "cohort-user")
    monkeypatch.setenv("MEMORY_MODE", "read")
    monkeypatch.setenv("MEMORY_ENABLED_USERS", "rollout-user")

    assert V17RolloutConfig.from_env().enabled_users == {"rollout-user"}
    assert resolve_memory_system("cohort-user") == MemorySystem.CANONICAL
    assert resolve_memory_system("rollout-user") == MemorySystem.LEGACY


def test_rollout_mode_does_not_flip_cohort_membership(monkeypatch):
    from config.v17_memory import V17Mode, V17RolloutConfig
    from utils.memory.memory_system import MemorySystem, resolve_memory_system

    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
    monkeypatch.setenv("MEMORY_MODE", V17Mode.read.value)
    monkeypatch.setenv("MEMORY_ENABLED_USERS", "rollout-only-user")

    assert V17RolloutConfig.from_env().mode == V17Mode.read
    assert resolve_memory_system("rollout-only-user") == MemorySystem.LEGACY


@pytest.mark.parametrize(
    ("legacy_key", "neutral_key", "legacy_value", "neutral_value", "reader", "expected"),
    [
        (
            "V17_BACKFILL_ENABLED",
            "MEMORY_BACKFILL_ENABLED",
            "true",
            "false",
            "rollout_backfill_enabled_env_value",
            False,
        ),
        (
            "V17_BACKFILL_DAILY_LIMIT",
            "MEMORY_BACKFILL_DAILY_LIMIT",
            "5",
            "10",
            "rollout_backfill_daily_limit_env_value",
            10,
        ),
        (
            "V17_ARCHIVE_OPT_IN_ENABLED",
            "MEMORY_ARCHIVE_OPT_IN_ENABLED",
            "false",
            "true",
            "rollout_archive_opt_in_enabled_env_value",
            True,
        ),
        ("V17_V3_GET_ENABLED", "MEMORY_V3_GET_ENABLED", "false", "true", "rollout_v3_get_enabled_env_value", True),
    ],
)
def test_rollout_extended_env_dual_read_neutral_precedence(
    legacy_key, neutral_key, legacy_value, neutral_value, reader, expected
):
    from config import memory_rollout

    assert getattr(memory_rollout, reader)({legacy_key: legacy_value, neutral_key: neutral_value}) == expected


@pytest.mark.parametrize(
    ("legacy_key", "neutral_key", "legacy_value", "reader", "expected"),
    [
        ("V17_BACKFILL_ENABLED", "MEMORY_BACKFILL_ENABLED", "true", "rollout_backfill_enabled_env_value", True),
        ("V17_BACKFILL_DAILY_LIMIT", "MEMORY_BACKFILL_DAILY_LIMIT", "7", "rollout_backfill_daily_limit_env_value", 7),
        (
            "V17_ARCHIVE_OPT_IN_ENABLED",
            "MEMORY_ARCHIVE_OPT_IN_ENABLED",
            "true",
            "rollout_archive_opt_in_enabled_env_value",
            True,
        ),
        ("V17_V3_GET_ENABLED", "MEMORY_V3_GET_ENABLED", "true", "rollout_v3_get_enabled_env_value", True),
    ],
)
def test_rollout_extended_env_dual_read_legacy_fallback(legacy_key, neutral_key, legacy_value, reader, expected):
    from config import memory_rollout

    assert getattr(memory_rollout, reader)({legacy_key: legacy_value}) == expected


@pytest.mark.parametrize(
    ("neutral_key", "legacy_key", "reader", "expected"),
    [
        ("MEMORY_BACKFILL_ENABLED", "V17_BACKFILL_ENABLED", "rollout_backfill_enabled_env_value", False),
        ("MEMORY_BACKFILL_DAILY_LIMIT", "V17_BACKFILL_DAILY_LIMIT", "rollout_backfill_daily_limit_env_value", 0),
        (
            "MEMORY_ARCHIVE_OPT_IN_ENABLED",
            "V17_ARCHIVE_OPT_IN_ENABLED",
            "rollout_archive_opt_in_enabled_env_value",
            False,
        ),
        ("MEMORY_V3_GET_ENABLED", "V17_V3_GET_ENABLED", "rollout_v3_get_enabled_env_value", False),
    ],
)
def test_rollout_extended_env_dual_read_unset_defaults(neutral_key, legacy_key, reader, expected):
    from config import memory_rollout

    assert getattr(memory_rollout, reader)({}) == expected


def test_rollout_config_from_env_uses_extended_dual_read(monkeypatch):
    from config.v17_memory import V17RolloutConfig

    monkeypatch.delenv("V17_BACKFILL_ENABLED", raising=False)
    monkeypatch.delenv("V17_BACKFILL_DAILY_LIMIT", raising=False)
    monkeypatch.delenv("V17_ARCHIVE_OPT_IN_ENABLED", raising=False)
    monkeypatch.setenv("MEMORY_BACKFILL_ENABLED", "true")
    monkeypatch.setenv("MEMORY_BACKFILL_DAILY_LIMIT", "12")
    monkeypatch.setenv("MEMORY_ARCHIVE_OPT_IN_ENABLED", "true")

    config = V17RolloutConfig.from_env()
    assert config.backfill_enabled is True
    assert config.backfill_daily_limit == 12
    assert config.archive_opt_in_enabled is True


def test_memory_non_active_routes_alias_reexports_match_v17():
    from database import memory_non_active_routes, v17_non_active_memory_routes

    assert memory_non_active_routes.NonActiveRoute is v17_non_active_memory_routes.NonActiveRoute
    assert (
        memory_non_active_routes.persist_non_active_route_outcome
        is v17_non_active_memory_routes.persist_non_active_route_outcome
    )


def test_memory_compatibility_projection_alias_reexports_match_v17():
    from database import memory_compatibility_projection, v17_v3_compatibility_projection

    assert (
        memory_compatibility_projection.read_v17_v3_compatibility_projection_page
        is v17_v3_compatibility_projection.read_v17_v3_compatibility_projection_page
    )


def test_memory_app_key_grants_alias_reexports_match_v17():
    from database import memory_app_key_grants, v17_app_key_memory_grants

    assert (
        memory_app_key_grants.V17AppKeyMemoryGrantStateRead is v17_app_key_memory_grants.V17AppKeyMemoryGrantStateRead
    )
    assert (
        memory_app_key_grants.read_v17_app_key_memory_grants_state
        is v17_app_key_memory_grants.read_v17_app_key_memory_grants_state
    )


def test_memory_vector_repair_outbox_alias_reexports_match_v17():
    from database import memory_vector_repair_outbox, v17_vector_repair_outbox

    assert (
        memory_vector_repair_outbox.V17_VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE
        is v17_vector_repair_outbox.V17_VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE
    )
    assert (
        memory_vector_repair_outbox.build_v17_vector_repair_purge_outbox_records
        is v17_vector_repair_outbox.build_v17_vector_repair_purge_outbox_records
    )
    assert (
        memory_vector_repair_outbox.write_v17_vector_repair_purge_outbox_records
        is v17_vector_repair_outbox.write_v17_vector_repair_purge_outbox_records
    )


def test_memory_vector_repair_outbox_worker_alias_reexports_match_v17():
    from database import memory_vector_repair_outbox_worker, v17_vector_repair_outbox_worker

    assert (
        memory_vector_repair_outbox_worker.run_v17_vector_repair_outbox_worker_tick
        is v17_vector_repair_outbox_worker.run_v17_vector_repair_outbox_worker_tick
    )


def test_memory_vector_repair_outbox_telemetry_alias_reexports_match_v17():
    from database import memory_vector_repair_outbox_telemetry, v17_vector_repair_outbox_telemetry

    assert (
        memory_vector_repair_outbox_telemetry.emit_v17_vector_repair_outbox_worker_telemetry
        is v17_vector_repair_outbox_telemetry.emit_v17_vector_repair_outbox_worker_telemetry
    )


def test_memory_vector_repair_pinecone_adapter_alias_reexports_match_v17():
    from database import memory_vector_repair_pinecone_adapter, v17_vector_repair_pinecone_adapter

    assert (
        memory_vector_repair_pinecone_adapter.make_v17_pinecone_vector_repairer
        is v17_vector_repair_pinecone_adapter.make_v17_pinecone_vector_repairer
    )


def test_memory_apply_alias_reexports_match_v17():
    from models import memory_apply, v17_memory_apply

    assert memory_apply.MemoryControlState is v17_memory_apply.MemoryControlState
    assert memory_apply.apply_long_term_patch_transaction is v17_memory_apply.apply_long_term_patch_transaction


def test_memory_search_gateway_alias_reexports_match_v17():
    from models import memory_search_gateway, v17_memory_search_gateway

    assert memory_search_gateway.SearchGatewayResult is v17_memory_search_gateway.SearchGatewayResult
    assert (
        memory_search_gateway.hydrate_and_filter_vector_hits is v17_memory_search_gateway.hydrate_and_filter_vector_hits
    )


def test_memory_operations_alias_reexports_match_v17():
    from models import memory_operations, v17_memory_operations

    assert memory_operations.MemoryOperation is v17_memory_operations.MemoryOperation
    assert memory_operations.build_operation_id is v17_memory_operations.build_operation_id


def test_memory_contracts_memory_tier_side_effect_reexport():
    from models import product_memory, v17_memory_contracts

    assert v17_memory_contracts.MemoryTier is product_memory.MemoryTier


def test_memory_contracts_extended_alias_reexports_match_v17():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.L1MemoryArchiveItem is v17_memory_contracts.L1MemoryArchiveItem
    assert memory_contracts.WorkingMemoryObservation is v17_memory_contracts.WorkingMemoryObservation
    assert memory_contracts.L2MemoryRoute is v17_memory_contracts.L2MemoryRoute
    assert memory_contracts.derive_allowed_use is v17_memory_contracts.derive_allowed_use


def test_product_memory_read_service_alias_reexports_match_v17():
    from utils.memory import product_memory_read_service, v17_product_memory_read_service

    for name in (
        "DEFAULT_PRODUCT_MEMORY_READ_LIMIT",
        "MAX_PRODUCT_MEMORY_READ_LIMIT",
        "fetch_archive_product_memory_search",
        "fetch_authoritative_product_memory_items",
        "fetch_default_product_memory_search",
    ):
        assert getattr(product_memory_read_service, name) is getattr(v17_product_memory_read_service, name)


def test_memory_read_api_alias_reexports_match_v17():
    from utils.memory import memory_read_api, v17_read_api

    for name in (
        "query_archive_product_memory_items",
        "query_default_product_memory_items",
        "query_durable_memory",
        "query_l1_archive",
        "query_memory_context",
        "query_working_memory",
    ):
        assert getattr(memory_read_api, name) is getattr(v17_read_api, name)


def test_memory_read_api_side_effect_reexports_match_v17():
    from utils.memory import memory_read_api, v17_read_api

    assert v17_read_api.MemoryLayer is memory_read_api.MemoryLayer
    assert v17_read_api.MemoryAccessPolicy is memory_read_api.MemoryAccessPolicy
    assert v17_read_api.V17MemoryItem is memory_read_api.V17MemoryItem


def test_vector_search_service_alias_reexports_match_v17():
    from utils.memory import vector_search_service, v17_vector_search_service

    for name in (
        "DEFAULT_V17_VECTOR_MAX_CANDIDATES",
        "DEFAULT_V17_VECTOR_MAX_QUERIES",
        "DEFAULT_V17_VECTOR_OVERFETCH_FACTOR",
        "DEFAULT_V17_VECTOR_SEARCH_LIMIT",
        "MAX_V17_VECTOR_MAX_QUERIES",
        "MAX_V17_VECTOR_OVERFETCH_FACTOR",
        "MAX_V17_VECTOR_SEARCH_LIMIT",
        "fetch_default_v17_vector_memory_search",
        "query_v17_memory_vector_candidates",
    ):
        assert getattr(vector_search_service, name) is getattr(v17_vector_search_service, name)


def test_vector_search_service_neutral_symbols_are_canonical():
    from utils.memory import vector_search_service

    assert vector_search_service.DEFAULT_VECTOR_SEARCH_LIMIT is vector_search_service.DEFAULT_V17_VECTOR_SEARCH_LIMIT
    assert vector_search_service.fetch_default_vector_memory_search is (
        vector_search_service.fetch_default_v17_vector_memory_search
    )


def test_default_read_rollout_alias_reexports_match_v17():
    from utils.memory import default_read_rollout, v17_default_read_rollout

    for name in (
        "DEFAULT_READ_OBSERVABILITY_CONSUMERS",
        "SUPPORTED_DEFAULT_READ_CONSUMERS",
        "V17DefaultReadRolloutDecision",
        "V17GlobalReadGateDecision",
        "V17LegacyMemoryWriteGuardDecision",
        "V17ReadDecision",
        "V17WriteConvergencePolicy",
        "V17_DEFAULT_READ_ROLLOUT_METRIC_NAME",
        "V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION",
        "V17_DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS",
        "V17_GLOBAL_READ_GATE_PATH",
        "V17_WRITE_CONVERGENCE_GATE_PATH",
        "assert_legacy_memory_write_allowed_for_default_read_decision",
        "read_v17_default_read_rollout",
        "read_v17_global_read_gate",
    ):
        assert getattr(default_read_rollout, name) is getattr(v17_default_read_rollout, name)


def test_default_read_rollout_neutral_symbols_are_canonical():
    from utils.memory import default_read_rollout

    assert default_read_rollout.V17ReadDecision is default_read_rollout.ReadDecision
    assert default_read_rollout.V17DefaultReadRolloutDecision is default_read_rollout.DefaultReadRolloutDecision
    assert default_read_rollout.V17_GLOBAL_READ_GATE_PATH is default_read_rollout.GLOBAL_READ_GATE_PATH


def test_projections_alias_reexports_match_v17():
    from utils.memory import projections, v17_projections

    assert projections.rebuild_v17_memory_projections is v17_projections.rebuild_v17_memory_projections
    assert projections.rebuild_memory_projections is v17_projections.rebuild_memory_projections


def test_projections_neutral_symbols_are_canonical():
    from utils.memory import projections

    assert projections.rebuild_v17_memory_projections is projections.rebuild_memory_projections


def test_vector_search_telemetry_alias_reexports_match_v17():
    from utils.memory import vector_search_telemetry, v17_vector_search_telemetry

    assert vector_search_telemetry.emit_v17_vector_search_telemetry is (
        v17_vector_search_telemetry.emit_v17_vector_search_telemetry
    )


def test_chat_memory_adapter_alias_reexports_match_v17():
    from utils.memory import chat_memory_adapter, v17_chat_memory_adapter

    for name in (
        "V17ChatDefaultMemoryRolloutDecision",
        "V17ChatMemorySearchResult",
        "V17_CHAT_MEMORY_BOUNDARY_NOTICE",
        "V17_CHAT_MEMORY_CONTENT_MAX_CHARS",
        "V17_CHAT_MEMORY_POLICY_MARKER",
        "list_v17_default_chat_memories_decision_text",
        "read_v17_chat_default_memory_rollout",
        "search_v17_default_chat_memories_text",
        "search_v17_default_chat_memories_vector_decision_text",
        "search_v17_default_chat_memories_vector_text",
    ):
        assert getattr(chat_memory_adapter, name) is getattr(v17_chat_memory_adapter, name)


def test_chat_memory_adapter_neutral_symbols_are_canonical():
    from utils.memory import chat_memory_adapter

    assert chat_memory_adapter.V17ChatMemorySearchResult is chat_memory_adapter.ChatMemorySearchResult
    assert chat_memory_adapter.V17_CHAT_MEMORY_BOUNDARY_NOTICE is chat_memory_adapter.CHAT_MEMORY_BOUNDARY_NOTICE


def test_developer_memory_adapter_alias_reexports_match_v17():
    from utils.memory import developer_memory_adapter, v17_developer_memory_adapter

    for name in (
        "V17DeveloperDefaultMemoryRolloutDecision",
        "V17DeveloperMemorySearchResult",
        "read_v17_developer_default_memory_rollout",
        "search_v17_default_developer_memories",
        "search_v17_default_developer_memories_vector",
    ):
        assert getattr(developer_memory_adapter, name) is getattr(v17_developer_memory_adapter, name)


def test_developer_memory_adapter_neutral_symbols_are_canonical():
    from utils.memory import developer_memory_adapter

    assert (
        developer_memory_adapter.V17DeveloperMemorySearchResult is developer_memory_adapter.DeveloperMemorySearchResult
    )


def test_patch_adapter_alias_reexports_match_v17():
    from utils.memory import patch_adapter, v17_patch_adapter

    assert patch_adapter.apply_v17_patch_to_ledger_state is v17_patch_adapter.apply_v17_patch_to_ledger_state


def test_product_authorization_alias_reexports_match_v17():
    from utils.memory import product_authorization, v17_product_authorization

    for name in (
        "EXTERNAL_V17_MEMORY_CONSUMERS",
        "ReadAppKeyGrantsState",
        "ReadGlobalGate",
        "ReadRollout",
        "V17AppKeyScopeGrantDecision",
        "V17MemoryGrantOperation",
        "V17ProductAuthorizationContext",
        "V17ProductAuthorizationDecision",
        "V17_MEMORY_OPERATION_REQUIRED_SCOPES",
        "authorize_v17_app_key_scope_memory_grant",
        "authorize_v17_external_default_memory_read",
        "authorize_v17_product_memory_route",
    ):
        assert getattr(product_authorization, name) is getattr(v17_product_authorization, name)


def test_product_authorization_neutral_symbols_are_canonical():
    from utils.memory import product_authorization

    assert product_authorization.V17ProductAuthorizationContext is product_authorization.ProductAuthorizationContext
    assert product_authorization.EXTERNAL_V17_MEMORY_CONSUMERS is product_authorization.EXTERNAL_MEMORY_CONSUMERS


def test_non_active_route_report_alias_reexports_match_v17():
    from utils.memory import non_active_route_report, v17_non_active_route_report

    assert (
        non_active_route_report.fetch_non_active_route_audit_report
        is v17_non_active_route_report.fetch_non_active_route_audit_report
    )


def test_non_active_route_audit_alias_reexports_match_v17():
    from utils.memory import non_active_route_audit, v17_non_active_route_audit

    for name in (
        "NonActiveRouteAuditEvidence",
        "NonActiveRouteAuditReport",
        "build_non_active_route_audit_report",
    ):
        assert getattr(non_active_route_audit, name) is getattr(v17_non_active_route_audit, name)


def test_v3_memory_read_service_alias_reexports_match_v17():
    from utils.memory import v17_v3_memory_read_service, v3_memory_read_service

    assert v3_memory_read_service.V17V3MemoryReadRequest is v17_v3_memory_read_service.V17V3MemoryReadRequest


def test_v3_production_runtime_alias_reexports_match_v17():
    from utils.memory import v17_v3_production_runtime, v3_production_runtime

    assert v3_production_runtime.build_v17_v3_production_runtime is (
        v17_v3_production_runtime.build_v17_v3_production_runtime
    )


def test_v3_request_adapter_alias_reexports_match_v17():
    from utils.memory import v17_v3_request_adapter, v3_request_adapter

    assert v3_request_adapter.adapt_v17_v3_request_parameters is v17_v3_request_adapter.adapt_v17_v3_request_parameters


def test_v3_response_adapter_alias_reexports_match_v17():
    from utils.memory import v17_v3_response_adapter, v3_response_adapter

    assert v3_response_adapter.adapt_v17_v3_memory_response is v17_v3_response_adapter.adapt_v17_v3_memory_response


def test_v3_route_planner_alias_reexports_match_v17():
    from utils.memory import v17_v3_route_planner, v3_route_planner

    assert v3_route_planner.plan_v17_v3_memory_route is v17_v3_route_planner.plan_v17_v3_memory_route


def test_v3_composed_get_service_alias_reexports_match_v17():
    from utils.memory import v17_v3_composed_get_service, v3_composed_get_service

    assert v3_composed_get_service.compose_v17_v3_get is v17_v3_composed_get_service.compose_v17_v3_get


def test_v3_control_state_adapter_alias_reexports_match_v17():
    from utils.memory import v17_v3_control_state_adapter, v3_control_state_adapter

    assert v3_control_state_adapter.read_v17_v3_control is v17_v3_control_state_adapter.read_v17_v3_control


def test_v3_limited_rollout_config_alias_reexports_match_v17():
    from utils.memory import v17_v3_limited_rollout_config, v3_limited_rollout_config

    assert v3_limited_rollout_config.ROUTE_SCOPE is v17_v3_limited_rollout_config.ROUTE_SCOPE


def test_v3_write_convergence_alias_reexports_match_v17():
    from utils.memory import v17_v3_write_convergence, v3_write_convergence

    assert v3_write_convergence.decide_v17_v3_write_convergence is (
        v17_v3_write_convergence.decide_v17_v3_write_convergence
    )


def test_v3_projection_readiness_alias_reexports_match_v17():
    from utils.memory import v17_v3_projection_readiness, v3_projection_readiness

    assert v3_projection_readiness.decide_v17_v3_projection_readiness is (
        v17_v3_projection_readiness.decide_v17_v3_projection_readiness
    )


def test_v3_f6_alias_reexports_match_v17():
    from utils.memory import v17_v3_f6, v3_f6

    assert v3_f6.build_pre_gcp_aggregate_report is v17_v3_f6.build_pre_gcp_aggregate_report
    assert v3_f6.verify_identity_iam is v17_v3_f6.verify_identity_iam


def test_v3_gcp_evidence_config_alias_reexports_match_v17():
    from utils.memory import v17_v3_gcp_evidence_config, v3_gcp_evidence_config

    assert v3_gcp_evidence_config.EvidenceTargetRegistry is v17_v3_gcp_evidence_config.EvidenceTargetRegistry


def test_v3_memory_read_service_side_effect_reexports_match_v17():
    from utils.memory import v17_v3_memory_read_service, v3_memory_read_service

    assert v3_memory_read_service.V17V3CompatibilityReadPath is v17_v3_memory_read_service.V17V3CompatibilityReadPath
    assert v3_memory_read_service.decide_v17_v3_compatibility is v17_v3_memory_read_service.decide_v17_v3_compatibility


def test_v3_memory_read_service_neutral_symbols_are_canonical():
    from utils.memory import v3_memory_read_service

    assert v3_memory_read_service.V17V3MemoryReadRequest is v3_memory_read_service.V3MemoryReadRequest
    assert v3_memory_read_service.V17_V3_READ_SOURCE is v3_memory_read_service.V3_READ_SOURCE


def test_v3_composed_get_service_neutral_symbols_are_canonical():
    from utils.memory import v3_composed_get_service

    assert v3_composed_get_service.V17V3ComposedCursor is v3_composed_get_service.V3ComposedCursor


def test_v3_projection_reader_contract_frozen_source_tags_unchanged():
    from utils.memory import v3_projection_reader_contract

    assert v3_projection_reader_contract.V17_V3_COMPATIBILITY_PROJECTION_SOURCE == "v17_memory_items_projection"
    assert v3_projection_reader_contract.V17_V3_COMPATIBILITY_PROJECTION_VERSION == "v3_memorydb_compatibility"


def test_v3_projection_readiness_frozen_source_tags_unchanged():
    from utils.memory import v3_projection_readiness

    assert v3_projection_readiness.V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE == "v17_derived_compatibility_projection"


def test_v3_f6_sub_shim_namespace_parity():
    import importlib

    base_exports = {
        "_validation": ["require_exact_fields"],
        "aggregate": [
            "F6_LOCAL_GATE_IDS",
            "GCP_ACCESS_GATE_IDS",
            "NON_CLAIMS",
            "build_pre_gcp_aggregate_report",
        ],
        "audit": [
            "AuditCorrelationResult",
            "AuditLogClient",
            "AuditLogEvent",
            "AuditQuery",
            "WRITE_METHOD_MARKERS",
            "assess_audit_correlation",
        ],
        "config": [
            "AUDIT_FIELDS",
            "AuditSettings",
            "EvidenceLimits",
            "EvidenceTarget",
            "EvidenceTargetRegistry",
            "INDEX_FIELDS",
            "LIMIT_FIELDS",
            "PLACEHOLDER_MARKERS",
            "TARGET_FIELDS",
            "ValidationError",
        ],
        "fingerprints": [
            "FINGERPRINT_RE",
            "HMAC_KEY",
            "FingerprintContractError",
            "RedactionContractError",
            "fingerprint",
        ],
        "identity_iam": [
            "FORBIDDEN_BROAD_ROLES",
            "FORBIDDEN_WRITE_PERMISSIONS",
            "IdentityIamSource",
            "IdentityIamTarget",
            "IdentityIamVerificationResult",
            "REQUIRED_READ_PERMISSIONS",
            "verify_identity_iam",
        ],
        "local_defaults": [
            "DEFAULT_APPROVED_METADATA_PATHS",
            "DEFAULT_EVIDENCE_TARGETS",
            "DEFAULT_INDEX_EXPECTATIONS",
        ],
        "local_doubles": [
            "FakeAuditLogClient",
            "FakeIdentityIamSource",
            "FakeReadEvidenceTransport",
        ],
        "local_smoke": ["build_report_from_current_local_contracts"],
        "pre_gcp_aggregate": [
            "F6_LOCAL_GATE_IDS",
            "GCP_ACCESS_GATE_IDS",
            "NON_CLAIMS",
            "build_pre_gcp_aggregate_report",
            "build_report_from_current_local_contracts",
        ],
        "protocol": [
            "ARTIFACT_VERSION_F6B",
            "ARTIFACT_VERSION_F6F",
            "ARTIFACT_VERSION_F6H",
            "AggregateDecision",
            "ArtifactVersion",
            "DECISION_BLOCKED_ON_GCP_ACCESS",
            "DECISION_NO_GO",
            "EvidenceTargetName",
            "GateStatus",
            "STATUS_BLOCKED",
            "STATUS_BLOCKED_ON_GCP_ACCESS",
            "STATUS_MISSING",
            "STATUS_PASS",
            "STATUS_PRE_GCP_READY",
            "TARGET_DEV",
            "TARGET_PROD",
        ],
        "read_evidence": [
            "EvidenceClientConfig",
            "GENERIC_OR_RAW_METHODS",
            "MUTATOR_TOKENS",
            "ReadEvidenceRequest",
            "ReadEvidenceTransport",
            "ReadOnlyEvidenceClient",
        ],
        "readonly_contracts": [
            "AuditCorrelationResult",
            "AuditLogClient",
            "AuditLogEvent",
            "AuditQuery",
            "EvidenceClientConfig",
            "FORBIDDEN_BROAD_ROLES",
            "FORBIDDEN_WRITE_PERMISSIONS",
            "FakeAuditLogClient",
            "FakeIdentityIamSource",
            "FakeReadEvidenceTransport",
            "GENERIC_OR_RAW_METHODS",
            "IdentityIamSource",
            "IdentityIamTarget",
            "IdentityIamVerificationResult",
            "MUTATOR_TOKENS",
            "REQUIRED_READ_PERMISSIONS",
            "ReadEvidenceRequest",
            "ReadEvidenceTransport",
            "ReadOnlyEvidenceClient",
            "RunRecord",
            "WRITE_METHOD_MARKERS",
            "_audit_method_is_write",
            "_method_family",
            "_method_is_forbidden",
            "assess_audit_correlation",
            "verify_identity_iam",
        ],
        "redaction": [
            "AUDIT_FIELDS",
            "FINGERPRINT_RE",
            "FORBIDDEN_FIELD_FRAGMENTS",
            "FORBIDDEN_VALUE_PATTERNS",
            "FingerprintContractError",
            "HMAC_KEY",
            "OBSERVATION_FIELDS",
            "READ_BOUNDS_FIELDS",
            "RedactionContractError",
            "TOP_LEVEL_FIELDS",
            "fingerprint",
            "render_redacted_evidence_json",
            "validate_redacted_evidence",
        ],
        "run_context": ["RunRecord"],
        "run_record": [
            "APPROVAL_FIELDS",
            "ExecutionWindow",
            "READ_BOUNDS_FIELDS",
            "RUN_RECORD_FIELDS",
            "RunRecordValidationError",
            "ValidatedRunRecord",
            "WINDOW_FIELDS",
            "validate_run_record",
        ],
    }
    for submodule, exports in base_exports.items():
        canonical = importlib.import_module(f"utils.memory.v3_f6.{submodule}")
        legacy = importlib.import_module(f"utils.memory.v17_v3_f6.{submodule}")
        for export in exports:
            assert getattr(canonical, export) is getattr(legacy, export), f"v17_v3_f6.{submodule}.{export}"
        if hasattr(legacy, "__all__"):
            for export in legacy.__all__:
                assert getattr(canonical, export) is getattr(legacy, export), f"v17_v3_f6.{submodule}.{export}"


def test_v3_cluster_shim_namespace_parity():
    import importlib

    pairs = [
        ("v3_compatibility", "v17_v3_compatibility"),
        ("v3_cursor", "v17_v3_cursor"),
        ("v3_memory_read_service", "v17_v3_memory_read_service"),
        ("v3_composed_get_service", "v17_v3_composed_get_service"),
        ("v3_production_runtime", "v17_v3_production_runtime"),
        ("v3_route_planner", "v17_v3_route_planner"),
        ("v3_f6_pre_gcp_aggregate", "v17_v3_f6_pre_gcp_aggregate"),
    ]
    for neutral_name, legacy_name in pairs:
        neutral = importlib.import_module(f"utils.memory.{neutral_name}")
        legacy = importlib.import_module(f"utils.memory.{legacy_name}")
        for export in legacy.__all__:
            assert getattr(neutral, export) is getattr(legacy, export), f"{legacy_name}.{export}"


def test_short_term_lifecycle_worker_alias_reexports_match_v17():
    from jobs import short_term_lifecycle_worker, v17_short_term_lifecycle_worker

    assert (
        short_term_lifecycle_worker.run_short_term_lifecycle_firestore
        is v17_short_term_lifecycle_worker.run_short_term_lifecycle_firestore
    )


def test_memory_product_alias_reexports_match_v17():
    import types

    sys.modules.setdefault("firebase_admin", types.ModuleType("firebase_admin"))
    auth_stub = types.ModuleType("utils.other.endpoints")
    auth_stub.get_current_user_uid = lambda: "u1"
    sys.modules.setdefault("utils.other.endpoints", auth_stub)

    from routers import memory_product, v17_memory_product

    assert memory_product.router is v17_memory_product.router
    assert memory_product.search_v17_product_memory is v17_memory_product.search_v17_product_memory


def test_memory_admin_alias_reexports_match_v17():
    import types

    sys.modules.setdefault("firebase_admin", types.ModuleType("firebase_admin"))
    auth_stub = types.ModuleType("utils.other.endpoints")
    auth_stub.get_current_user_uid = lambda: "u1"
    sys.modules.setdefault("utils.other.endpoints", auth_stub)

    from routers import memory_admin, v17_memory_admin

    assert memory_admin.router is v17_memory_admin.router
