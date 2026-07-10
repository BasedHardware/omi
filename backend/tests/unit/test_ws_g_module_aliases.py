"""WS-G retained module alias shims — import parity for deferred router/env aliases."""

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
    install_memory_product_router_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module", autouse=True)
def _ws_g_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    ensure_utils_memory_packages_importable()
    install_database_client_stub()
    yield
    restore_sys_modules(saved)


def test_memory_contracts_l1_l2_symbol_aliases_are_identity():
    from models import memory_contracts

    assert memory_contracts.WorkingObservation is memory_contracts.WorkingMemoryObservation
    assert memory_contracts.WorkingObservationArchiveItem is memory_contracts.L1MemoryArchiveItem
    assert memory_contracts.PromotionRoute is memory_contracts.L2MemoryRoute


@pytest.mark.slow
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
    from models import memory_contracts

    assert memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE == "durable_memory_patch"
    assert memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE is memory_contracts.DURABLE_MEMORY_PATCH_FACT_SOURCE


def test_memory_collections_neutral_symbols_are_canonical():
    from database import memory_collections

    assert memory_collections.MemoryCollections is memory_collections.MemoryCollections


def test_memory_collections_frozen_path_strings_unchanged():
    from database.memory_collections import MemoryCollections

    paths = MemoryCollections(uid="uid-test")
    assert paths.memory_items == "users/uid-test/memory_items"
    assert paths.memory_operations == "users/uid-test/memory_operations"
    assert paths.memory_outbox == "users/uid-test/memory_outbox"
    assert paths.memory_control_state == "users/uid-test/memory_control/state"
    assert paths.memory_apply_control_state == "users/uid-test/memory_state/apply_control"
    assert paths.memory_lineage == "users/uid-test/memory_lineage"
    assert paths.memory_evidence == "users/uid-test/memory_evidence"
    assert paths.memory_runs == "users/uid-test/memory_runs"
    assert paths.non_active_memory_routes == "users/uid-test/non_active_memory_routes"
    assert paths.short_term_lifecycle_transitions == "users/uid-test/short_term_lifecycle_transitions"
    assert paths.legacy_fallback == "users/uid-test/memory_legacy_fallback"
    assert paths.memory_commits == "users/uid-test/memory_commits"
    assert paths.memory_state == "users/uid-test/memory_state"
    assert paths.memory_state_head == "users/uid-test/memory_state/head"
    assert paths.v3_compatibility_projection_state == "users/uid-test/v3_compatibility_projection/state"
    assert paths.v3_compatibility_projection_items == "users/uid-test/v3_compatibility_projection_items"


def test_memory_rollout_neutral_symbols_are_canonical():
    from config import memory_rollout

    assert memory_rollout.MemoryRolloutMode is memory_rollout.MemoryRolloutMode
    assert memory_rollout.MemoryRolloutConfig is memory_rollout.MemoryRolloutConfig
    assert memory_rollout.MemoryRolloutState is memory_rollout.MemoryRolloutState
    assert memory_rollout.MemoryRolloutCapabilities is memory_rollout.MemoryRolloutCapabilities
    assert memory_rollout.MemoryRolloutStageGate is memory_rollout.MemoryRolloutStageGate


def test_rollout_mode_env_dual_read_legacy_only():
    from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value

    assert rollout_mode_env_value({"MEMORY_MODE": "read"}) == "read"
    assert MemoryRolloutMode(rollout_mode_env_value({"MEMORY_MODE": "read"})) == MemoryRolloutMode.read


def test_rollout_mode_env_dual_read_neutral_precedence(monkeypatch):
    from config.memory_rollout import MemoryRolloutMode, MemoryRolloutConfig, rollout_mode_env_value

    monkeypatch.setenv("MEMORY_MODE", "shadow")
    monkeypatch.setenv("MEMORY_MODE", "read")
    assert rollout_mode_env_value() == "read"
    assert MemoryRolloutConfig.from_env().mode == MemoryRolloutMode.read


@pytest.mark.parametrize(
    ("set_sequence", "expected_raw", "expected_enabled_users"),
    [
        (["uid-a,uid-b"], "uid-a,uid-b", {"uid-a", "uid-b"}),
        (["legacy-only", "neutral-only"], "neutral-only", {"neutral-only"}),
    ],
)
def test_rollout_enabled_users_env_dual_read(monkeypatch, set_sequence, expected_raw, expected_enabled_users):
    from config.memory_rollout import MemoryRolloutConfig, rollout_enabled_users_env_raw

    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)
    for value in set_sequence:
        monkeypatch.setenv("MEMORY_ENABLED_USERS", value)
    assert rollout_enabled_users_env_raw() == expected_raw
    assert MemoryRolloutConfig.from_env().enabled_users == expected_enabled_users


def test_rollout_env_dual_read_does_not_use_canonical_cohort(monkeypatch):
    from config.memory_rollout import MemoryRolloutConfig
    from utils.memory.memory_system import resolve_memory_system, MemorySystem

    from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)
    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)
    set_canonical_cohort(monkeypatch, "cohort-user")
    monkeypatch.setenv("MEMORY_MODE", "read")
    monkeypatch.setenv("MEMORY_ENABLED_USERS", "rollout-user")

    assert MemoryRolloutConfig.from_env().enabled_users == {"rollout-user"}
    assert resolve_memory_system("cohort-user") == MemorySystem.LEGACY
    assert resolve_memory_system("rollout-user") == MemorySystem.LEGACY


def test_rollout_mode_does_not_flip_cohort_membership(monkeypatch):
    from config.memory_rollout import MemoryRolloutMode, MemoryRolloutConfig
    from utils.memory.memory_system import MemorySystem, resolve_memory_system

    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)
    monkeypatch.setenv("MEMORY_MODE", MemoryRolloutMode.read.value)
    monkeypatch.setenv("MEMORY_ENABLED_USERS", "rollout-only-user")

    assert MemoryRolloutConfig.from_env().mode == MemoryRolloutMode.read
    assert resolve_memory_system("rollout-only-user") == MemorySystem.LEGACY


@pytest.mark.parametrize(
    ("legacy_key", "neutral_key", "legacy_value", "neutral_value", "reader", "expected"),
    [
        ("MEMORY_V3_GET_ENABLED", "MEMORY_V3_GET_ENABLED", "false", "true", "rollout_v3_get_enabled_env_value", True),
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
        ("MEMORY_V3_GET_ENABLED", "MEMORY_V3_GET_ENABLED", "true", "rollout_v3_get_enabled_env_value", True),
    ],
)
def test_rollout_extended_env_dual_read_legacy_fallback(legacy_key, neutral_key, legacy_value, reader, expected):
    from config import memory_rollout

    assert getattr(memory_rollout, reader)({legacy_key: legacy_value}) == expected


@pytest.mark.parametrize(
    ("neutral_key", "legacy_key", "reader", "expected"),
    [
        ("MEMORY_V3_GET_ENABLED", "MEMORY_V3_GET_ENABLED", "rollout_v3_get_enabled_env_value", False),
    ],
)
def test_rollout_extended_env_dual_read_unset_defaults(neutral_key, legacy_key, reader, expected):
    from config import memory_rollout

    assert getattr(memory_rollout, reader)({}) == expected


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
    install_memory_product_router_stubs(fastapi_stub, auth_stub)
    from routers import memory_admin, memory_product

    return saved, memory_product, memory_admin


def test_main_registers_memory_product_and_admin_routes():
    saved, memory_product, memory_admin = _import_memory_router_modules_under_stubs()
    try:
        product_routes = _router_method_path_pairs(memory_product.router)
        admin_routes = _router_method_path_pairs(memory_admin.router)

        assert set(path for _method, path in product_routes) == {
            "/memory/search",
            "/memory/vector/search",
            "/memory/archive/search",
        }
        assert set(path for _method, path in admin_routes) == {
            "/memory/admin/users/{uid}/read-rollout-decision",
            "/memory/admin/users/{uid}/non-active-route-report",
            "/memory/admin/users/{uid}/short-term-lifecycle/run",
        }
    finally:
        restore_sys_modules(saved)
