"""Configuration axes for the external-structure foreground deadline lane.

Companion to ``test_external_structure_foreground_deadline.py`` (incident and
structurer-level fix): the route-ref/deploy readers, usage classification, and
the inventory contract, mirroring the ``test_chat_metadata_deadline_invariance``
pattern for the seventh instance of the foreground-deadline class.

Failure-Class: FC-foreground-call-inherits-background-deadline — guard
surface: this suite enumerates the lane's configuration axes so a future edit
that restores the background deadline on any branch fails here.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-hermetic-tests")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

import utils.llm.model_config as model_config  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

FEATURE = "external_structure"


# ---------------------------------------------------------------------------
# Deadline resolution surface
# ---------------------------------------------------------------------------


def test_feature_request_timeout_returns_the_foreground_budget():
    assert model_config.feature_request_timeout(FEATURE) == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_feature_request_timeout_returns_none_for_background_features():
    for background in ("conv_folder", "conv_discard", "chat_extraction", "daily_summary_simple"):
        assert model_config.feature_request_timeout(background) is None


def test_the_foreground_budget_stays_inside_the_finalization_timeout_middleware():
    """Route budgets cap finalization far above one minute; the foreground
    deadline must stay comfortably inside them, not negotiate with them."""
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS < 120.0


def test_the_background_gateway_deadline_is_what_the_feature_used_to_inherit():
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    assert DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS < model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_the_foreground_family_covers_every_whole_content_lane():
    assert model_config._FOREGROUND_TIMEOUT_FEATURES == frozenset(
        {
            "conv_structure",
            "conv_app_result",
            "daily_summary",
            "memory_l1",
            "chat_metadata_extraction",
            "external_structure",
        }
    )


def test_the_declaration_is_a_member_not_a_call_site_override():
    """The deadline must come from the route map, not from an explicit argument
    at the two call sites — regenerating the seam would otherwise drop it."""
    import re

    source = (BACKEND_DIR / "utils" / "llm" / "external_integrations.py").read_text()
    for call in re.findall(r"get_llm\('external_structure'[^)]*\)", source):
        assert "request_timeout" not in call, call


# ---------------------------------------------------------------------------
# Route-ref surface (the deploy/config readers)
# ---------------------------------------------------------------------------


def test_route_ref_resolves_the_explicit_route_for_the_feature():
    from utils.llm.gateway_client import feature_auto_lane_id
    from utils.llm.model_config import ExplicitRouteRef, get_model, get_provider, get_route_options, get_route_ref

    before_model = get_model(FEATURE)
    before_provider = get_provider(FEATURE)

    route_ref = get_route_ref(FEATURE)

    assert route_ref == ExplicitRouteRef(
        feature=FEATURE,
        model=before_model,
        provider=before_provider,
        options=get_route_options(FEATURE, before_model, before_provider),
    )
    # Reading the route ref must not flip the profile maps.
    assert get_model(FEATURE) == before_model
    assert get_provider(FEATURE) == before_provider
    # The generated lane id the gateway resolves for this feature.
    assert feature_auto_lane_id(FEATURE) == "omi:auto:external-structure"


def test_unknown_feature_still_fails_closed():
    from utils.llm.model_config import UnknownLLMFeature, get_route_ref

    with pytest.raises(UnknownLLMFeature):
        get_route_ref("external_structure_typo")


def test_byok_provider_lookup_matches_the_profile():
    assert model_config.get_byok_provider(FEATURE) == "openai"


def test_profiles_cover_the_feature_on_every_tier():
    for profile_name, profile in model_config.MODEL_QOS_PROFILES.items():
        assert FEATURE in profile, f"missing from {profile_name}"


def test_the_lane_budget_is_ninety_seconds_and_the_primary_is_pinned():
    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    by_feature = {item["feature"]: item for item in overrides}
    assert by_feature[FEATURE]["request_timeout_ms"] == 90000
    assert by_feature[FEATURE]["primary"] == {"provider": "openai", "model": "gpt-6-luna"}


def test_the_generated_lane_request_budget_really_covers_the_client_deadline():
    """Load the whole prod-mode gateway config the way the deployed service
    does: the generated route's server-side budget must be at least the client
    foreground deadline, not just present in the override file."""
    from llm_gateway.gateway.config_loader import load_gateway_config

    config = load_gateway_config(prod_mode=True)
    route = config.route_artifacts["route.external_structure.model_config.001"]
    assert route.timeouts.request_ms >= model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS * 1000


def test_the_lane_keeps_its_structured_output_capability():
    """The deadline change must not touch what the lane advertises: the two
    structurers ride the structured-output json_schema capability."""
    from llm_gateway.gateway.config_loader import load_gateway_config

    config = load_gateway_config(prod_mode=True)
    lane = config.lanes["omi:auto:external-structure"]
    assert lane.capabilities.structured_output.value == "json_schema"


def test_the_serving_lane_budgets_of_the_foreground_family_stay_consistent():
    """Sibling foreground lanes that declare a raised budget all cover their
    client deadline; the flex lanes keep their documented long budgets."""
    from llm_gateway.gateway.config_loader import load_gateway_config

    config = load_gateway_config(prod_mode=True)
    assert config.route_artifacts["route.chat_metadata_extraction.model_config.001"].timeouts.request_ms == 90000
    assert config.route_artifacts["route.external_structure.model_config.001"].timeouts.request_ms == 90000
    assert config.route_artifacts["route.memory_conflict_flex.model_config.001"].timeouts.request_ms == 900000
    assert config.route_artifacts["route.x_memory_extraction_flex.model_config.001"].timeouts.request_ms == 900000


def test_the_client_deadline_never_exceeds_the_lane_budget():
    """For every foreground feature with a raised lane budget: client seconds
    <= lane milliseconds — the invariant the 30s default broke."""
    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    from llm_gateway.gateway.config_loader import load_gateway_config

    config = load_gateway_config(prod_mode=True)
    for item in overrides:
        if "request_timeout_ms" not in item:
            continue
        if model_config.feature_request_timeout(item["feature"]) is None:
            continue
        route = config.route_artifacts[f"route.{item['feature']}.model_config.001"]
        assert model_config.feature_request_timeout(item["feature"]) * 1000 <= route.timeouts.request_ms


# ---------------------------------------------------------------------------
# Inventory contract (the model_endpoint_inventory.yaml readers)
# ---------------------------------------------------------------------------


def test_the_feature_stays_listed_in_the_inventory_request_shapes():
    inventory = yaml.safe_load((BACKEND_DIR / "docs" / "llm" / "model_endpoint_inventory.yaml").read_text())
    listed = set()
    for values in inventory["model_config_features"]["request_shapes"].values():
        listed.update(values)
    assert FEATURE in listed


def test_the_inventory_surface_entry_still_names_the_feature():
    inventory = yaml.safe_load((BACKEND_DIR / "docs" / "llm" / "model_endpoint_inventory.yaml").read_text())
    surfaces = [s for s in inventory["surfaces"] if s.get("feature") == FEATURE]
    assert surfaces, "the external_integrations surface entry disappeared"
    assert any(
        "external_integrations.py::feature:external_structure" in call for s in surfaces for call in s["call_sites"]
    )


# ---------------------------------------------------------------------------
# Usage classification (the cost dashboards read this)
# ---------------------------------------------------------------------------


def test_usage_units_classify_the_feature_as_conversation_extraction():
    from database.usage_units import feature_class

    assert feature_class("external_structure") == "conversation_extraction"


def test_usage_classification_is_unchanged_for_the_foreground_family():
    from database.usage_units import feature_class

    assert feature_class("conv_structure") == "conversation_extraction"
    assert feature_class("memory_l1") == "conversation_extraction"
    assert feature_class("chat_metadata_extraction") == "chat"


# ---------------------------------------------------------------------------
# get_llm resolution order end to end (the deadline travels every branch)
# ---------------------------------------------------------------------------


def _capturing_gateway(monkeypatch, captured):
    import utils.llm.clients as clients

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, streaming=streaming, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)


def test_gateway_lane_id_matches_the_feature_route(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    import utils.llm.clients as clients

    clients.get_llm(FEATURE)
    assert captured["lane_id"] == "omi:auto:external-structure"


def test_streaming_flag_passes_through_the_managed_branch(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    import utils.llm.clients as clients

    clients.get_llm(FEATURE, streaming=True)
    assert captured["streaming"] is True


def test_background_features_do_not_gain_the_foreground_budget(monkeypatch):
    """Control: conv_discard keeps the client default — the nano binary lanes
    must not inherit the 60s budget from this fix."""
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    import utils.llm.clients as clients

    clients.get_llm("conv_discard")
    assert "request_timeout" not in captured["options"]


def test_gateway_mode_and_byok_use_distinct_cached_clients(monkeypatch):
    """The deadline is part of the client cache key: a foreground-deadline
    client and a background client on the same provider must not share one."""
    from langchain_core.callbacks import BaseCallbackHandler

    import utils.llm.clients as clients

    class _Probe(BaseCallbackHandler):
        def on_llm_end(self, *args, **kwargs):
            return None

    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.llm.providers._usage_callback", _Probe())
    monkeypatch.setattr("utils.llm.usage_tracker.get_usage_callback", lambda: _Probe())

    foreground = clients.get_llm(FEATURE)
    background = clients.get_llm("conv_discard")
    assert foreground is not background


def test_distinct_deadlines_resolve_distinct_clients(monkeypatch):
    """external_structure (60s) and chat_extraction (background) on the same
    provider must never share a cached client after the deadline change."""
    from langchain_core.callbacks import BaseCallbackHandler

    import utils.llm.clients as clients

    class _Probe(BaseCallbackHandler):
        def on_llm_end(self, *args, **kwargs):
            return None

    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.llm.providers._usage_callback", _Probe())
    monkeypatch.setattr("utils.llm.usage_tracker.get_usage_callback", lambda: _Probe())

    foreground = clients.get_llm(FEATURE)
    background = clients.get_llm("chat_extraction")
    assert foreground is not background
