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
    assert product_memory.V17MemoryItem is v17_product_memory.V17MemoryItem


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


def test_memory_collections_alias_reexports_match_v17():
    from database import memory_collections, v17_collections

    assert memory_collections.V17Collections is v17_collections.V17Collections


def test_memory_apply_store_alias_reexports_match_v17():
    from database import memory_apply_store, v17_memory_apply_store

    assert memory_apply_store.V17FirestoreApplyError is v17_memory_apply_store.V17FirestoreApplyError
    assert memory_apply_store.MissingV17Document is v17_memory_apply_store.MissingV17Document
    assert memory_apply_store.apply_long_term_patch_firestore is v17_memory_apply_store.apply_long_term_patch_firestore
    assert memory_apply_store.atomic_bump_source_generation is v17_memory_apply_store.atomic_bump_source_generation


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
        memory_vector_repair_outbox.build_v17_vector_repair_purge_outbox_records
        is v17_vector_repair_outbox.build_v17_vector_repair_purge_outbox_records
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


def test_memory_contracts_extended_alias_reexports_match_v17():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.L1MemoryArchiveItem is v17_memory_contracts.L1MemoryArchiveItem
    assert memory_contracts.WorkingMemoryObservation is v17_memory_contracts.WorkingMemoryObservation
    assert memory_contracts.L2MemoryRoute is v17_memory_contracts.L2MemoryRoute
    assert memory_contracts.derive_allowed_use is v17_memory_contracts.derive_allowed_use


def test_product_memory_read_service_alias_reexports_match_v17():
    from utils.memory import product_memory_read_service, v17_product_memory_read_service

    assert (
        product_memory_read_service.DEFAULT_PRODUCT_MEMORY_READ_LIMIT
        is v17_product_memory_read_service.DEFAULT_PRODUCT_MEMORY_READ_LIMIT
    )
    assert product_memory_read_service.fetch_archive_product_memory_search is (
        v17_product_memory_read_service.fetch_archive_product_memory_search
    )


def test_memory_read_api_alias_reexports_match_v17():
    from utils.memory import memory_read_api, v17_read_api

    assert memory_read_api.query_default_product_memory_items is v17_read_api.query_default_product_memory_items
    assert memory_read_api.query_durable_memory is v17_read_api.query_durable_memory


def test_vector_search_service_alias_reexports_match_v17():
    from utils.memory import vector_search_service, v17_vector_search_service

    assert (
        vector_search_service.DEFAULT_V17_VECTOR_MAX_CANDIDATES
        is v17_vector_search_service.DEFAULT_V17_VECTOR_MAX_CANDIDATES
    )
    assert vector_search_service.fetch_default_v17_vector_memory_search is (
        v17_vector_search_service.fetch_default_v17_vector_memory_search
    )


def test_default_read_rollout_alias_reexports_match_v17():
    from utils.memory import default_read_rollout, v17_default_read_rollout

    assert default_read_rollout.V17DefaultReadRolloutDecision is v17_default_read_rollout.V17DefaultReadRolloutDecision


def test_projections_alias_reexports_match_v17():
    from utils.memory import projections, v17_projections

    assert projections.rebuild_v17_memory_projections is v17_projections.rebuild_v17_memory_projections


def test_vector_search_telemetry_alias_reexports_match_v17():
    from utils.memory import vector_search_telemetry, v17_vector_search_telemetry

    assert vector_search_telemetry.emit_v17_vector_search_telemetry is (
        v17_vector_search_telemetry.emit_v17_vector_search_telemetry
    )


def test_chat_memory_adapter_alias_reexports_match_v17():
    from utils.memory import chat_memory_adapter, v17_chat_memory_adapter

    assert chat_memory_adapter.V17ChatMemorySearchResult is v17_chat_memory_adapter.V17ChatMemorySearchResult


def test_developer_memory_adapter_alias_reexports_match_v17():
    from utils.memory import developer_memory_adapter, v17_developer_memory_adapter

    assert (
        developer_memory_adapter.read_v17_developer_default_memory_rollout
        is v17_developer_memory_adapter.read_v17_developer_default_memory_rollout
    )


def test_patch_adapter_alias_reexports_match_v17():
    from utils.memory import patch_adapter, v17_patch_adapter

    assert patch_adapter.apply_v17_patch_to_ledger_state is v17_patch_adapter.apply_v17_patch_to_ledger_state


def test_product_authorization_alias_reexports_match_v17():
    from utils.memory import product_authorization, v17_product_authorization

    assert product_authorization.ReadGlobalGate is v17_product_authorization.ReadGlobalGate


def test_non_active_route_report_alias_reexports_match_v17():
    from utils.memory import non_active_route_report, v17_non_active_route_report

    assert (
        non_active_route_report.fetch_non_active_route_audit_report
        is v17_non_active_route_report.fetch_non_active_route_audit_report
    )


def test_non_active_route_audit_alias_reexports_match_v17():
    from utils.memory import non_active_route_audit, v17_non_active_route_audit

    assert non_active_route_audit.build_non_active_route_audit_report is (
        v17_non_active_route_audit.build_non_active_route_audit_report
    )


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
