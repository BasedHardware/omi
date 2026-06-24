"""WS-G retained module alias shims — import parity for deferred v17 chain only."""

import os
import sys

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import pytest

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_v17_product_router_stubs,
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
    from utils.llm.working_observations import L1MemoryArchiveItems, WorkingObservationBatch

    assert L1MemoryArchiveItems is WorkingObservationBatch


def test_l2_memory_route_response_alias_is_identity():
    from utils.llm.promotion_routes import L2MemoryRouteResponse, PromotionRouteResponse

    assert L2MemoryRouteResponse is PromotionRouteResponse


def test_working_observations_shim_namespace_parity():
    import importlib

    canonical = importlib.import_module("utils.llm.working_observations")
    legacy = importlib.import_module("utils.llm.working_memory")
    exports = [
        "L1MemoryArchiveItems",
        "WorkingObservationBatch",
        "_CLIENT_IMPORT_ERROR",
        "_build_l1_messages",
        "_content_from_response",
        "_persist_l1_archive_route_outcomes",
        "_source_type_instructions",
        "_with_deterministic_archive_ids",
        "extract_l1_memory_archive_items_from_text",
        "get_llm",
        "logger",
        "persist_non_active_route_outcome",
    ]
    for export in exports:
        assert getattr(legacy, export) is getattr(canonical, export), f"working_memory.{export}"


def test_promotion_routes_shim_namespace_parity():
    import importlib

    canonical = importlib.import_module("utils.llm.promotion_routes")
    legacy = importlib.import_module("utils.llm.l2_memory_routes")
    exports = [
        "L2MemoryRouteResponse",
        "PromotionRouteResponse",
        "_CLIENT_IMPORT_ERROR",
        "_QUOTE_WRAPPER_RE",
        "_canonical_json",
        "_content_from_response",
        "_is_quote_wrapper",
        "classify_l2_memory_route",
        "get_llm",
        "l2_memory_route_prompt",
        "logger",
        "promotion_route_prompt",
    ]
    for export in exports:
        assert getattr(legacy, export) is getattr(canonical, export), f"l2_memory_routes.{export}"


def test_promotion_proposals_shim_namespace_parity():
    import importlib

    canonical = importlib.import_module("utils.llm.promotion_proposals")
    legacy = importlib.import_module("utils.llm.durable_memory_patches")
    exports = [
        "PROMOTION_RUBRIC",
        "CandidateOutcome",
        "CandidateOutcomeStatus",
        "DurableMemoryPatchProposal",
        "DurableMemoryPatchProposals",
        "DurableMemorySynthesisResult",
        "PromotionProposal",
        "PromotionProposals",
        "PromotionSynthesisResult",
        "SynthesisStatus",
        "_CLIENT_IMPORT_ERROR",
        "_CONTROL_FIELDS",
        "_QUOTE_WRAPPER_RE",
        "_candidate_outcome_for_patch",
        "_canonical_json",
        "_content_from_response",
        "_is_quote_wrapper",
        "_logical_patch_payload",
        "_packet_evidence_ids",
        "_proposal_to_patch",
        "_raw_payload_from_response_text",
        "_retrieved_memory_ids",
        "_valid_non_quote_wrapper_patches",
        "_with_deterministic_patch_ids",
        "_with_production_safety_guards",
        "_with_server_control_ids",
        "durable_memory_patch_prompt",
        "get_llm",
        "logger",
        "promotion_proposal_prompt",
        "synthesize_durable_memory_patch_result",
        "synthesize_durable_memory_patches",
    ]
    for export in exports:
        assert getattr(legacy, export) is getattr(canonical, export), f"durable_memory_patches.{export}"


def test_promotion_proposal_symbol_aliases_are_identity():
    from utils.llm.promotion_proposals import (
        DurableMemoryPatchProposal,
        DurableMemoryPatchProposals,
        DurableMemorySynthesisResult,
        PromotionProposal,
        PromotionProposals,
        PromotionSynthesisResult,
        durable_memory_patch_prompt,
        promotion_proposal_prompt,
    )

    assert PromotionProposal is DurableMemoryPatchProposal
    assert PromotionProposals is DurableMemoryPatchProposals
    assert PromotionSynthesisResult is DurableMemorySynthesisResult
    assert promotion_proposal_prompt is durable_memory_patch_prompt


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


def test_memory_rollout_neutral_symbols_are_canonical():
    from config import memory_rollout

    assert memory_rollout.V17Mode is memory_rollout.MemoryRolloutMode
    assert memory_rollout.V17RolloutConfig is memory_rollout.MemoryRolloutConfig
    assert memory_rollout.V17RolloutState is memory_rollout.MemoryRolloutState
    assert memory_rollout.V17Capabilities is memory_rollout.MemoryRolloutCapabilities
    assert memory_rollout.V17StageGate is memory_rollout.MemoryRolloutStageGate


def test_rollout_mode_env_dual_read_legacy_only():
    from config.memory_rollout import V17Mode, rollout_mode_env_value

    assert rollout_mode_env_value({"V17_MODE": "read"}) == "read"
    assert V17Mode(rollout_mode_env_value({"V17_MODE": "read"})) == V17Mode.read


def test_rollout_mode_env_dual_read_neutral_precedence(monkeypatch):
    from config.memory_rollout import V17Mode, V17RolloutConfig, rollout_mode_env_value

    monkeypatch.setenv("V17_MODE", "shadow")
    monkeypatch.setenv("MEMORY_MODE", "read")
    assert rollout_mode_env_value() == "read"
    assert V17RolloutConfig.from_env().mode == V17Mode.read


def test_rollout_enabled_users_env_dual_read_legacy_only(monkeypatch):
    from config.memory_rollout import V17RolloutConfig, rollout_enabled_users_env_raw

    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)
    monkeypatch.setenv("V17_MEMORY_ENABLED_USERS", "uid-a,uid-b")
    assert rollout_enabled_users_env_raw() == "uid-a,uid-b"
    assert V17RolloutConfig.from_env().enabled_users == {"uid-a", "uid-b"}


def test_rollout_enabled_users_env_dual_read_neutral_precedence(monkeypatch):
    from config.memory_rollout import V17RolloutConfig, rollout_enabled_users_env_raw

    monkeypatch.setenv("V17_MEMORY_ENABLED_USERS", "legacy-only")
    monkeypatch.setenv("MEMORY_ENABLED_USERS", "neutral-only")
    assert rollout_enabled_users_env_raw() == "neutral-only"
    assert V17RolloutConfig.from_env().enabled_users == {"neutral-only"}


def test_rollout_env_dual_read_does_not_use_canonical_cohort(monkeypatch):
    from config.memory_rollout import V17RolloutConfig
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
    from config.memory_rollout import V17Mode, V17RolloutConfig
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
    from config.memory_rollout import V17RolloutConfig

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


def test_memory_contracts_memory_tier_side_effect_reexport():
    from models import product_memory, v17_memory_contracts

    assert v17_memory_contracts.MemoryTier is product_memory.MemoryTier


def test_memory_contracts_extended_alias_reexports_match_v17():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.L1MemoryArchiveItem is v17_memory_contracts.L1MemoryArchiveItem
    assert memory_contracts.WorkingMemoryObservation is v17_memory_contracts.WorkingMemoryObservation
    assert memory_contracts.L2MemoryRoute is v17_memory_contracts.L2MemoryRoute
    assert memory_contracts.derive_allowed_use is v17_memory_contracts.derive_allowed_use


def test_patch_adapter_alias_reexports_match_v17():
    from utils.memory import patch_adapter, v17_patch_adapter

    assert patch_adapter.apply_v17_patch_to_ledger_state is v17_patch_adapter.apply_v17_patch_to_ledger_state


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


def _router_method_path_pairs(router):
    pairs = set()
    for route in router.routes:
        if isinstance(route, tuple):
            pairs.add((route[0], route[1]))
            continue
        for method in route.methods:
            if method != "HEAD":
                pairs.add((method, route.path))
    return pairs


def _import_memory_router_modules_under_stubs():
    import types

    class _APIRouter:
        def __init__(self):
            self.routes = []

        def get(self, path, **kwargs):
            def decorator(func):
                self.routes.append(("GET", path, kwargs, func))
                return func

            return decorator

        def post(self, path, **kwargs):
            def decorator(func):
                self.routes.append(("POST", path, kwargs, func))
                return func

            return decorator

    def _identity(default=None, **_kwargs):
        return default

    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.APIRouter = _APIRouter
    fastapi_stub.Depends = _identity
    fastapi_stub.Header = _identity
    fastapi_stub.HTTPException = Exception
    fastapi_stub.Query = _identity

    auth_stub = types.ModuleType("utils.other.endpoints")
    auth_stub.get_current_user_uid = lambda: "u1"

    router_module_names = (
        "routers.memory_product",
        "routers.memory_admin",
    )
    saved = snapshot_sys_modules(["fastapi", "database._client", "utils.other.endpoints", *router_module_names])
    for name in router_module_names:
        sys.modules.pop(name, None)
    install_v17_product_router_stubs(fastapi_stub, auth_stub)
    from routers import memory_admin, memory_product

    return saved, memory_product, memory_admin


def test_main_registers_memory_product_and_admin_routes():
    saved, memory_product, memory_admin = _import_memory_router_modules_under_stubs()
    try:
        product_routes = _router_method_path_pairs(memory_product.router)
        admin_routes = _router_method_path_pairs(memory_admin.router)

        assert ("GET", "/memory/search") in product_routes
        assert ("GET", "/v17/memory/search") in product_routes
        assert ("GET", "/memory/vector/search") in product_routes
        assert ("GET", "/v17/memory/vector/search") in product_routes
        assert ("GET", "/memory/archive/search") in product_routes
        assert ("GET", "/v17/memory/archive/search") in product_routes
        assert ("GET", "/v17/admin/users/{uid}/read-rollout-decision") in admin_routes
        assert ("GET", "/v17/admin/users/{uid}/non-active-route-report") in admin_routes
        assert ("POST", "/v17/admin/users/{uid}/short-term-lifecycle/run") in admin_routes
    finally:
        restore_sys_modules(saved)
