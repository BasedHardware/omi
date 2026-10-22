"""Extra behavioral coverage for the chat-metadata foreground deadline lane.

Companion to ``test_chat_metadata_foreground_deadline.py`` (incident and
route-level fix): configuration axes, cache binding, BYOK branches, lane
budget, and the incident-reproduction controls, mirroring the
``test_memory_l1_deadline_invariance`` pattern for the sixth instance of the
foreground-deadline class.

Failure-Class: FC-foreground-call-inherits-background-deadline — guard
surface: this suite enumerates the lane's configuration axes so a future edit
that restores the background deadline on any branch fails here.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-hermetic-tests")

from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.callbacks import BaseCallbackHandler

# Import anthropic (which imports jiter) and the observability package BEFORE
# any stub fixture runs, for two import-order traps this suite originally hit:
#   - jiter's package __init__ cannot survive an evict-package/keep-.so-
#     submodule cycle (re-import then raises NameError inside jiter itself);
#   - utils.observability registers global Prometheus counters at import, and
#     a stub-block eviction followed by a re-exec in a later file re-registered
#     them into the same registry (Duplicated timeseries). Importing both here
#     puts them in stub_modules' restore set instead of the eviction set.
#   - the same eviction/re-exec cycle on google.ai.* proto modules poisons the
#     global proto descriptor pool (duplicate file name), so pre-import the
#     langchain_google_genai chain that clients.py pulls in.
import anthropic  # noqa: F401
import langchain_google_genai  # noqa: F401
import utils.observability  # noqa: F401

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

PROVIDER_FIRST_BYTE_SECONDS = 25.0


class _LLMUsageCallbackProbe(BaseCallbackHandler):
    """Real handler satisfying ChatOpenAI's callback validation, inert by design."""

    def on_llm_end(self, *args, **kwargs):
        return None


class _Extraction:
    people = ["David"]
    topics = ["running"]
    entities = ["Boston"]
    dates = ["next friday"]


def _deadline_resolving_get_llm(resolved, model_config, *, background_only=False):
    """Build a get_llm stub mirroring get_llm's own resolution order."""

    def _get_llm(feature, *args, **kwargs):
        from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

        deadline = kwargs.get("request_timeout")
        deadline = deadline if deadline is not None else model_config.feature_request_timeout(feature)
        if deadline is None:
            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        resolved.append((feature, deadline))

        class _Structured:
            def invoke(self, _prompt):
                if deadline < PROVIDER_FIRST_BYTE_SECONDS:
                    raise TimeoutError("Request timed out.")
                return _Extraction()

        class _Client:
            def with_structured_output(self, _schema):
                return _Structured()

        return _Client()

    return _get_llm


@pytest.fixture(scope="module", autouse=True)
def _load_chat(request):
    """Load utils.llm.chat fresh against stubbed heavy deps (shared pattern)."""
    from types import ModuleType

    from testing.import_isolation import load_module_fresh, stub_modules

    import utils.llm.model_config as model_config
    import utils.llm.prompt_cache as real_prompt_cache

    fakes: dict[str, ModuleType] = {}

    def add(name, mod):
        fakes[name] = mod
        return mod

    database_pkg = ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    add("database", database_pkg)
    for name in (
        "database._client",
        "database.users",
        "database.notifications",
        "database.goals",
        "database.apps",
        "database.redis_db",
        "database.auth",
    ):
        add(name, MagicMock(name=name))

    usage_tracker_mod = ModuleType("utils.llm.usage_tracker")
    usage_tracker_mod.track_usage = MagicMock()
    usage_tracker_mod.get_usage_callback = MagicMock(return_value=None)
    usage_tracker_mod.Features = type("Features", (), {"CONVERSATION_PROCESSING": "conversation_processing"})
    add("utils.llm.usage_tracker", usage_tracker_mod)

    prompt_cache_mod = ModuleType("utils.llm.prompt_cache")
    prompt_cache_mod.with_cache_write_opt_out = lambda runnable: runnable
    add("utils.llm.prompt_cache", prompt_cache_mod)

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "utils.llm.temporal", str(BACKEND_DIR / "utils" / "llm" / "temporal.py")
    )
    temporal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(temporal)
    add("utils.llm.temporal", temporal)

    llms_pkg = ModuleType("utils.llms")
    llms_pkg.__path__ = [str(BACKEND_DIR / "utils" / "llms")]
    add("utils.llms", llms_pkg)
    llms_memory = ModuleType("utils.llms.memory")
    llms_memory.get_prompt_memories = MagicMock(return_value="")
    add("utils.llms.memory", llms_memory)

    with stub_modules(fakes):
        chat = load_module_fresh("utils.llm.chat", str(BACKEND_DIR / "utils" / "llm" / "chat.py"))
        request.module.llm_chat = chat
        request.module.model_config = model_config
        request.module.real_prompt_cache = real_prompt_cache
        yield


@pytest.fixture
def resolved(monkeypatch):
    """Install the deadline-enforcing provider; report (feature, deadline) calls."""
    calls: list = []
    stub = _deadline_resolving_get_llm(calls, model_config)
    original = llm_chat.get_llm
    monkeypatch.setattr(llm_chat, "get_llm", stub)
    return calls


def _run_transcript():
    return llm_chat.retrieve_metadata_fields_from_transcript(
        uid="uid-meta-invariance",
        created_at=datetime(2026, 10, 20, 12, 0, 0),
        transcript_segment=[{"text": "Long conversation transcript content."}],
        tz="UTC",
    )


def _run_message():
    return llm_chat.retrieve_metadata_from_message(
        "uid-meta-invariance",
        datetime(2026, 10, 20, 12, 0, 0),
        "Long message body content.",
        "UTC",
    )


def _run_text():
    return llm_chat.retrieve_metadata_from_text(
        "uid-meta-invariance",
        datetime(2026, 10, 20, 12, 0, 0),
        "Long document text content.",
        "UTC",
        source_spec="notion",
    )


# ---------------------------------------------------------------------------
# Axis: the three whole-content entrypoints
# ---------------------------------------------------------------------------


def test_transcript_path_resolves_the_foreground_deadline(resolved):
    metadata = _run_transcript()
    assert metadata["people"] == ["david"]
    assert resolved == [("chat_metadata_extraction", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_message_path_resolves_the_foreground_deadline(resolved):
    metadata = _run_message()
    assert metadata["people"] == ["david"]
    assert resolved == [("chat_metadata_extraction", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_text_path_resolves_the_foreground_deadline(resolved):
    metadata = _run_text()
    assert metadata["people"] == ["david"]
    assert resolved == [("chat_metadata_extraction", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


# ---------------------------------------------------------------------------
# Axis: routing knobs on get_llm cannot drop the deadline
# ---------------------------------------------------------------------------


def test_byok_gateway_construction_carries_the_foreground_deadline(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_profile", lambda: None)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda provider: "byok-key" if provider == "openai" else None)

    def fake_byok_gateway(lane_id, *, provider, api_key, streaming, options, feature):
        captured.update(lane_id=lane_id, provider=provider, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm_for_byok", fake_byok_gateway)
    clients.get_llm("chat_metadata_extraction")
    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert captured["provider"] == "openai"


def test_byok_direct_construction_never_drops_below_the_foreground_deadline(monkeypatch):
    """The direct BYOK branch defaults to a 120s budget inside _create_byok_client;
    pin the real constructed kwargs so a future edit that shrinks the BYOK
    budget under the whole-content deadline fails here instead of in prod."""
    import utils.llm.clients as clients

    captured: dict = {}
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: False)
    monkeypatch.setattr("utils.llm.clients.get_byok_profile", lambda: None)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda provider: "byok-key" if provider == "openai" else None)
    monkeypatch.setattr(
        clients,
        "_cached_openai_chat",
        lambda model, key, kwargs: captured.update(model=model, kwargs=dict(kwargs)) or object(),
    )

    clients.get_llm("chat_metadata_extraction")

    assert captured["model"], "the BYOK branch did not construct a client"
    assert captured["kwargs"]["request_timeout"] >= model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_managed_route_uses_the_dedicated_lane_even_when_optional_gateway_is_off(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: False)
    monkeypatch.setattr("utils.llm.clients.should_route_company_paid_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)
    clients.get_llm("chat_metadata_extraction")
    assert captured["lane_id"] == "omi:auto:chat-metadata-extraction"
    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_the_shared_lane_still_resolves_without_a_request_timeout(monkeypatch):
    """Control: get_llm('chat_extraction') keeps the client default — the
    thirteen interactive prompts must not inherit the 60s budget."""
    import utils.llm.clients as clients

    captured: dict = {}
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(options=dict(options or {}))
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)
    clients.get_llm("chat_extraction")
    assert "request_timeout" not in captured["options"]


def test_gateway_mode_and_byok_use_distinct_cached_clients(monkeypatch):
    """The deadline is part of the client cache key: the foreground feature and
    the background sibling on the same provider must not share an instance."""
    import utils.llm.clients as clients

    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.llm.providers._usage_callback", _LLMUsageCallbackProbe())
    monkeypatch.setattr("utils.llm.usage_tracker.get_usage_callback", lambda: _LLMUsageCallbackProbe())

    foreground = clients.get_llm("chat_metadata_extraction")
    background = clients.get_llm("chat_extraction")
    assert foreground is not background


# ---------------------------------------------------------------------------
# Axis: the message/text boundary (different log text, same contract)
# ---------------------------------------------------------------------------


def test_message_boundary_logs_the_distinct_error_text(resolved, monkeypatch, caplog):
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
    import logging

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        metadata = _run_message()
    assert metadata == {"people": [], "topics": [], "entities": [], "dates": []}
    # The boundary logs a typed, path-attributed line (the raw ``e {e}``/
    # ``Error extracting metadata`` payloads could not name the failing type);
    # the message lane stays distinguishable from the transcript lane.
    records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert any(
        "metadata extraction failed" in record.getMessage() and "path=message" in record.getMessage()
        for record in records
    )


def test_text_boundary_also_returns_empty_under_the_background_deadline(resolved, monkeypatch):
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    assert _run_text() == {"people": [], "topics": [], "entities": [], "dates": []}


def test_background_deadline_control_on_all_three_paths(resolved, monkeypatch):
    """Restoring the background deadline reproduces the incident on every
    entrypoint — the proof the tests above bite."""
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    for run in (_run_transcript, _run_message, _run_text):
        resolved.clear()
        assert run() == {"people": [], "topics": [], "entities": [], "dates": []}
        assert resolved == [("chat_metadata_extraction", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)]


def test_the_provider_cost_still_exceeds_the_background_deadline():
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    assert PROVIDER_FIRST_BYTE_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_foreground_deadline_stays_inside_the_finalization_budget():
    """Finalization runs under a 1500s route budget; one conversation's
    metadata call must never wedge the worker."""
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS < 120.0


# ---------------------------------------------------------------------------
# Axis: cache binding survives the feature switch
# ---------------------------------------------------------------------------


def test_metadata_extraction_cache_binding_contract_holds_on_the_new_feature(monkeypatch):
    """Drive the real _process_extracted_metadata path with a fake model and
    the real with_cache_write_opt_out: the explicit-mode opt-out still arrives
    on the INVOKED runnable under the new feature key."""
    import utils.llm.gateway_client as gateway_client

    captured: dict = {}

    class _FakeModel:
        def __init__(self, state):
            self._state = state

        def bind(self, **kwargs):
            self._state["bound_kwargs"] = kwargs
            return self

        def with_structured_output(self, _schema):
            return self

        def invoke(self, _prompt):
            # with_cache_write_opt_out binds AFTER with_structured_output, so
            # the bound kwargs are what the transport would actually send.
            self._state["invoked_kwargs"] = dict(self._state.get("bound_kwargs") or {})
            return _Extraction()

    def _get_llm(feature, **kwargs):
        captured["feature"] = feature
        model = _FakeModel(captured)
        return model.bind(**kwargs) if kwargs else model

    real_opt_out = real_prompt_cache.with_cache_write_opt_out

    monkeypatch.setattr(llm_chat, "get_llm", _get_llm)
    monkeypatch.setattr(llm_chat, "track_usage", lambda *a, **k: nullcontext())
    monkeypatch.setattr(llm_chat, "add_filter_category_item", lambda *a, **k: None)
    monkeypatch.setattr(real_prompt_cache, "gpt56_explicit_cache_enabled", lambda: True)
    monkeypatch.setattr(real_prompt_cache, "_byok_request", lambda: False)
    monkeypatch.setattr(gateway_client, "should_route_features_through_gateway", lambda: True)

    llm_chat.with_cache_write_opt_out = real_opt_out
    llm_chat._process_extracted_metadata("uid-cache-binding", "one unique prompt", "2026-10-20")

    assert captured["feature"] == "chat_metadata_extraction"
    assert captured["invoked_kwargs"] == {
        "extra_body": {"prompt_cache_options": dict(real_prompt_cache.EXPLICIT_CACHE_OPTIONS)}
    }


# ---------------------------------------------------------------------------
# Axis: gateway lane budget guardrails
# ---------------------------------------------------------------------------


def test_new_lane_satisfies_the_gateway_coverage_guardrails():
    """The generated lane must appear wherever every configured feature's lane
    appears — the same invariant test_llm_gateway_coverage_guardrails pins."""
    import yaml

    from llm_gateway.gateway.config_loader import load_gateway_config
    from utils.llm.gateway_client import feature_auto_lane_id
    from utils.llm.model_config import get_all_configured_features

    config = load_gateway_config(prod_mode=True)
    missing = [f for f in get_all_configured_features() if feature_auto_lane_id(f) not in config.lanes]
    assert missing == []
    assert feature_auto_lane_id("chat_metadata_extraction") in config.lanes

    inventory = yaml.safe_load((BACKEND_DIR / "docs" / "llm" / "model_endpoint_inventory.yaml").read_text())
    listed = set()
    for values in inventory["model_config_features"]["request_shapes"].values():
        listed.update(values)
    assert "chat_metadata_extraction" in listed


def test_new_route_override_pins_reasoning_effort_like_every_luna_lane():
    import yaml

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    by_feature = {item["feature"]: item for item in overrides}
    assert by_feature["chat_metadata_extraction"]["provider_options"]["reasoning_effort"] == "low"


def test_lane_budget_is_90_seconds():
    import yaml

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    by_feature = {item["feature"]: item for item in overrides}
    assert by_feature["chat_metadata_extraction"]["request_timeout_ms"] == 90000


# ---------------------------------------------------------------------------
# Route-ref surfaces (the deploy/config readers)
# ---------------------------------------------------------------------------


def test_route_ref_resolves_the_explicit_route_for_the_new_feature():
    from utils.llm.gateway_client import feature_auto_lane_id
    from utils.llm.model_config import ExplicitRouteRef, get_model, get_provider, get_route_options, get_route_ref

    feature = "chat_metadata_extraction"
    before_model = get_model(feature)
    before_provider = get_provider(feature)

    route_ref = get_route_ref(feature)

    assert route_ref == ExplicitRouteRef(
        feature=feature,
        model=before_model,
        provider=before_provider,
        options=get_route_options(feature, before_model, before_provider),
    )
    # Reading the route ref must not flip the profile maps.
    assert get_model(feature) == before_model
    assert get_provider(feature) == before_provider
    # The generated lane id the gateway resolves for this feature.
    assert feature_auto_lane_id(feature) == "omi:auto:chat-metadata-extraction"


def test_unknown_feature_still_fails_closed():
    from utils.llm.model_config import UnknownLLMFeature, get_route_ref

    with pytest.raises(UnknownLLMFeature):
        get_route_ref("chat_metadata_extraction_typo")


def test_the_feature_appears_in_get_qos_info():
    import utils.llm.clients as clients

    info = clients.get_qos_info()
    assert info["chat_metadata_extraction"] == {
        "model": model_config.get_model("chat_metadata_extraction"),
        "profile": model_config.get_active_profile_name(),
        "provider": "openai",
    }


def test_byok_provider_lookup_matches_the_profile():
    from utils.llm.model_config import get_byok_provider

    assert get_byok_provider("chat_metadata_extraction") == "openai"


def test_profiles_cover_the_new_feature_on_every_tier():
    for profile_name, profile in model_config.MODEL_QOS_PROFILES.items():
        assert "chat_metadata_extraction" in profile, f"missing from {profile_name}"
