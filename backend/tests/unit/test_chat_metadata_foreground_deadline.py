"""Whole-conversation metadata extraction must not die on the background gateway deadline.

Live prod signature (pusher container, GCP, 2026-10-20/21, x52-69/30m, #2 in
the Loop S feed):

    ERROR:utils.llm.chat:e Request timed out.

Root cause: ``retrieve_metadata_fields_from_transcript`` and its message/text
siblings (through ``_process_extracted_metadata``) build their client with
``get_llm('chat_extraction')`` and no explicit deadline. The feature had no
entry in ``_FOREGROUND_TIMEOUT_FEATURES``, so the client inherited the
background gateway transport deadline (15s to first byte) while the extractors
feed the WHOLE conversation content — full transcript or entire external
message body — into one structured call. The provider timeout raised, the
``except`` arm logged the bare ``e {e}`` line and returned empty metadata, and
conversation finalization upserted a summary vector whose people / topics /
entities / dates search filters were all silently empty.

Sixth instance of the class (see
``docs/operational/chat-metadata-foreground-deadline.md``). The fix declares
the deadline on a dedicated feature route
(``model_config._FOREGROUND_TIMEOUT_FEATURES`` member
``chat_metadata_extraction``) — the deadline is a property of the call, not of
each call site. A dedicated key, not an entry on the shared
``chat_extraction`` feature, because that lane also serves thirteen short
interactive-chat prompts that must keep the background deadline.

Failure-Class: FC-foreground-call-inherits-background-deadline — a
finalization call that cannot complete without a dependency answered inside
the shared client deadline sized for cheap background work. Fixed by
declaring the foreground deadline on the feature route and pinned by driving
the real production functions against a provider slower than the background
deadline.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-hermetic-tests")

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

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

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# What the metadata extractor's provider really needs to answer a
# whole-conversation structured prompt. Longer than the 15s background
# first-byte deadline, comfortably inside the 60s foreground deadline.
PROVIDER_FIRST_BYTE_SECONDS = 25.0

_EXTRACTED_JSON = '{"people": ["David"], "topics": ["running"], "entities": ["Boston"], "dates": ["next friday"]}'

# Populated by the autouse ``_load_modules`` fixture before any test runs.
llm_chat = None
model_config = None


def _build_fakes() -> dict[str, ModuleType]:
    """Stub the heavy chat.py dependency chain the sanctioned way.

    ``database.*`` is stubbed to avoid the Firestore client construction at
    import; ``langchain`` is stubbed minimally for the module import; the LLM
    usage/caching helpers are stubbed because the deadline seam under test is
    ``get_llm`` itself, which every test installs explicitly.
    """
    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    database_pkg = ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    add("database", database_pkg)

    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock(name="db")
    client_mod.get_firestore_client = lambda: client_mod.db
    client_mod.get_data_plane_firestore_client = lambda: client_mod.db
    add("database._client", client_mod)

    for name in (
        "database.users",
        "database.notifications",
        "database.goals",
        "database.apps",
        "database.redis_db",
        "database.auth",
    ):
        add(name, MagicMock(name=name))

    usage_tracker_mod = ModuleType("utils.llm.usage_tracker")
    usage_tracker_mod.track_usage = MagicMock(name="track_usage")
    usage_tracker_mod.get_usage_callback = MagicMock(return_value=None)
    usage_tracker_mod.Features = type("Features", (), {"CONVERSATION_PROCESSING": "conversation_processing"})
    add("utils.llm.usage_tracker", usage_tracker_mod)

    prompt_cache_mod = ModuleType("utils.llm.prompt_cache")
    prompt_cache_mod.with_cache_write_opt_out = lambda runnable: runnable
    add("utils.llm.prompt_cache", prompt_cache_mod)

    temporal_real = load_real_temporal()
    add("utils.llm.temporal", temporal_real)

    llms_pkg = ModuleType("utils.llms")
    llms_pkg.__path__ = [str(BACKEND_DIR / "utils" / "llms")]
    add("utils.llms", llms_pkg)
    llms_memory = ModuleType("utils.llms.memory")
    llms_memory.get_prompt_memories = MagicMock(return_value="")
    add("utils.llms.memory", llms_memory)

    return fakes


def load_real_temporal() -> ModuleType:
    """Load the real pure module (date grounding) — it imports no DB layer."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "utils.llm.temporal", str(BACKEND_DIR / "utils" / "llm" / "temporal.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", autouse=True)
def _load_modules(request):
    """Load utils.llm.chat fresh against the stubbed deps (see header docstring)."""
    import utils.llm.model_config as real_model_config

    fakes = _build_fakes()
    with stub_modules(fakes):
        chat = load_module_fresh(
            "utils.llm.chat",
            str(BACKEND_DIR / "utils" / "llm" / "chat.py"),
        )
        request.module.llm_chat = chat
        request.module.model_config = real_model_config
        yield


class _DeadlineTrackingProvider:
    """Provider enforcing the resolved deadline the way the real transport does."""

    def __init__(self, resolved: list, invocations: list):
        self.resolved = resolved
        self.invocations = invocations

    def __call__(self, feature, *args, **kwargs):
        deadline = kwargs.get("request_timeout")
        deadline = deadline if deadline is not None else model_config.feature_request_timeout(feature)
        if deadline is None:
            from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        self.resolved.append((feature, deadline))

        structured = _StructuredInvoker(self, deadline)
        client = _ClientStub(structured)
        return client

    def invoke(self, deadline, prompt):
        self.invocations.append(prompt)
        if deadline < PROVIDER_FIRST_BYTE_SECONDS:
            raise TimeoutError("Request timed out.")
        return _Extraction()


class _StructuredInvoker:
    def __init__(self, provider: _DeadlineTrackingProvider, deadline: float):
        self._provider = provider
        self._deadline = deadline

    def invoke(self, prompt: str):
        return self._provider.invoke(self._deadline, prompt)


class _ClientStub:
    def __init__(self, structured: _StructuredInvoker):
        self._structured = structured

    def with_structured_output(self, _schema):
        return self._structured


class _Extraction:
    people = ["David"]
    topics = ["running"]
    entities = ["Boston"]
    dates = ["next friday"]


class LLMUsageCallbackProbe(BaseCallbackHandler):
    """Real handler satisfying ChatOpenAI's callback validation, inert by design."""

    def on_llm_end(self, *args, **kwargs):
        return None


@pytest.fixture
def provider():
    """Install the deadline-tracking provider as chat.py's get_llm.

    Patch the module object the tests call (the module-global ``llm_chat`` the
    autouse fixture installed), NOT a fresh ``import utils.llm.chat``: in a
    combined run an earlier file's stub teardown can restore the real chat
    module into sys.modules, and patching that object would leave the fresh
    copy's real ``get_llm`` in place — a live network client inside a unit
    test.
    """
    tracker = _DeadlineTrackingProvider(resolved=[], invocations=[])
    original = llm_chat.get_llm
    llm_chat.get_llm = tracker
    yield tracker
    llm_chat.get_llm = original


def _transcript_call(uid="uid-meta-deadline"):
    return llm_chat.retrieve_metadata_fields_from_transcript(
        uid=uid,
        created_at=datetime(2026, 10, 20, 12, 0, 0),
        transcript_segment=[{"text": "I went running with David near Boston, we talked about next friday."}],
        tz="UTC",
    )


def _message_call():
    return llm_chat.retrieve_metadata_from_message(
        "uid-meta-deadline",
        datetime(2026, 10, 20, 12, 0, 0),
        "Message from David about running in Boston next friday.",
        "UTC",
        source_spec="telegram",
    )


# ---------------------------------------------------------------------------
# 1. The feature route owns the deadline
# ---------------------------------------------------------------------------


def test_chat_metadata_extraction_declares_the_foreground_deadline():
    """Against unmodified source this fails: the feature inherited the client default."""
    assert (
        model_config.feature_request_timeout("chat_metadata_extraction")
        == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    )


def test_foreground_deadline_exceeds_what_the_provider_needs():
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > PROVIDER_FIRST_BYTE_SECONDS
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_the_foreground_family_stays_closed_over_its_members():
    """The class guard: every whole-content lane that runs in finalization."""
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


def test_the_shared_chat_extraction_feature_keeps_the_background_deadline():
    """The thirteen interactive-chat prompts on the shared lane stay bounded."""
    assert model_config.feature_request_timeout("chat_extraction") is None


def test_background_feature_keeps_the_default_deadline():
    assert model_config.feature_request_timeout("conv_folder") is None


# ---------------------------------------------------------------------------
# 2. Routing: the new feature resolves like its sibling chat lane
# ---------------------------------------------------------------------------


def test_route_resolution_matches_the_shared_chat_extraction_lane():
    """Same Luna route on managed traffic — only the deadline differs."""
    assert model_config.get_model("chat_metadata_extraction") == model_config.get_model("chat_extraction")
    assert model_config.get_provider("chat_metadata_extraction") == model_config.get_provider("chat_extraction")


def test_byok_route_avoids_luna():
    """A user's own OpenAI key cannot serve Luna; BYOK resolves gpt-4o-mini."""
    assert model_config.get_byok_provider("chat_metadata_extraction") == "openai"
    byok_profile = model_config.MODEL_QOS_PROFILES["byok"]
    assert byok_profile["chat_metadata_extraction"] == byok_profile["chat_extraction"]


def test_get_llm_gateway_mode_passes_the_foreground_deadline(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    clients.get_llm("chat_metadata_extraction")

    assert captured["lane_id"] == "omi:auto:chat-metadata-extraction"
    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert captured["feature"] == "chat_metadata_extraction"


def test_get_llm_managed_route_carries_the_foreground_deadline_even_when_optional_gateway_is_off(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: False)
    monkeypatch.setattr("utils.llm.clients.should_route_company_paid_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    clients.get_llm("chat_metadata_extraction")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_get_llm_byok_gateway_branch_carries_the_foreground_deadline(monkeypatch):
    import utils.llm.clients as clients

    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_profile", lambda: None)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda provider: "byok-key" if provider == "openai" else None)
    captured: dict = {}

    def fake_byok_gateway(lane_id, *, provider, api_key, streaming, options, feature):
        captured.update(
            lane_id=lane_id, provider=provider, api_key=api_key, options=dict(options or {}), feature=feature
        )
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm_for_byok", fake_byok_gateway)

    clients.get_llm("chat_metadata_extraction")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert captured["feature"] == "chat_metadata_extraction"


# ---------------------------------------------------------------------------
# 3. The extractors themselves, against a provider slower than the background deadline
# ---------------------------------------------------------------------------


def test_slow_provider_still_extracts_transcript_metadata(provider):
    """Against unmodified source this is the failure that shipped: timeout, empty filters."""
    metadata = _transcript_call()
    assert metadata["people"] == ["david"]
    assert metadata["topics"] == ["running"]
    assert provider.resolved == [("chat_metadata_extraction", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_slow_provider_still_extracts_message_metadata(provider):
    metadata = _message_call()
    assert metadata["people"] == ["david"]
    assert provider.resolved == [("chat_metadata_extraction", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_the_extractor_sends_whole_conversation_content(provider):
    """The prompt carries the full transcript — the call shape that needs 60s."""
    _transcript_call()
    assert provider.invocations, "the extractor never invoked the client"
    assert "running with David" in provider.invocations[0]


def test_extraction_seeds_the_filter_categories(provider):
    """The extracted filters are written to the user's filter categories."""
    calls: list = []
    original = llm_chat.add_filter_category_item
    llm_chat.add_filter_category_item = lambda uid, category, value: calls.append((category, value))
    try:
        _transcript_call()
    finally:
        llm_chat.add_filter_category_item = original
    assert ("people", "david") in calls
    assert ("topics", "running") in calls


def test_structured_source_alias_rides_the_same_lane(provider):
    """retrieve_metadata_fields_from_structured delegates to the transcript path."""

    class _Structured:
        title = "Morning run"
        overview = "Ran with David in Boston, planning next friday."

    metadata = llm_chat.retrieve_metadata_fields_from_structured(
        "uid-meta-deadline", datetime(2026, 10, 20, 12, 0, 0), _Structured(), "UTC"
    )
    assert metadata["people"] == ["david"]
    assert provider.resolved == [("chat_metadata_extraction", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


# ---------------------------------------------------------------------------
# 4. Control: the background deadline is what lost the metadata
# ---------------------------------------------------------------------------


def test_background_deadline_is_what_emptied_the_filters(provider, monkeypatch, caplog):
    """Put the background deadline back and the exact prod failure returns:
    the bare ``e Request timed out.`` ERROR line and empty search filters."""
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    import logging

    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        metadata = _transcript_call()

    assert metadata == {"people": [], "topics": [], "entities": [], "dates": []}
    assert any("Request timed out." in record.getMessage() for record in caplog.records)
    assert provider.resolved == [("chat_metadata_extraction", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)]


def test_background_deadline_message_path_also_returns_empty(provider, monkeypatch):
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    assert _message_call() == {"people": [], "topics": [], "entities": [], "dates": []}


def test_an_explicit_request_timeout_still_wins_over_the_route(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(options=dict(options or {}))
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    clients.get_llm("chat_metadata_extraction", request_timeout=42.0)

    assert captured["options"]["request_timeout"] == 42.0


# ---------------------------------------------------------------------------
# 5. The gateway lane's server-side budget covers the client deadline
# ---------------------------------------------------------------------------


def test_generated_lane_exists_and_its_budget_covers_the_client_deadline():
    """The generated lane omi:auto:chat-metadata-extraction must exist and allow
    the 60s foreground call: a lane budget shorter than the client deadline
    would abort the request server-side and reintroduce the prod failure with
    the deadline technically 'declared'."""
    import yaml

    from llm_gateway.gateway.config_loader import load_gateway_config
    from utils.llm.gateway_client import feature_auto_lane_id

    config = load_gateway_config(prod_mode=True)
    lane_id = feature_auto_lane_id("chat_metadata_extraction")
    assert lane_id in config.lanes
    route = config.route_artifacts[f"route.chat_metadata_extraction.model_config.001"]
    assert route.timeouts.request_ms >= model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS * 1000

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())
    override = next(
        item for item in overrides["generated_route_overrides"] if item["feature"] == "chat_metadata_extraction"
    )
    assert override["request_timeout_ms"] == 90000


def test_lane_primary_model_matches_the_shared_chat_extraction_lane():
    import yaml

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    by_feature = {item["feature"]: item for item in overrides}
    assert by_feature["chat_metadata_extraction"]["primary"] == by_feature["chat_extraction"]["primary"]


# ---------------------------------------------------------------------------
# 6. The real gateway client construction carries the deadline end to end
# ---------------------------------------------------------------------------


def test_real_gateway_client_construction_carries_the_foreground_timeout(monkeypatch):
    """No stub on the constructor: get_llm's managed branch must hand the
    foreground deadline to the real gateway client factory."""
    from langchain_core.callbacks import BaseCallbackHandler

    import utils.llm.clients as clients
    import utils.llm.providers as providers

    captured: dict = {}
    real_factory = providers.get_or_create_omi_gateway_llm

    def spy_factory(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, options=dict(options or {}), feature=feature)
        return real_factory(lane_id, streaming, options, feature=feature)

    monkeypatch.setattr(providers, "get_or_create_omi_gateway_llm", spy_factory)
    monkeypatch.setattr("utils.llm.clients.get_or_create_omi_gateway_llm", spy_factory)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    # The factory builds a real ChatOpenAI, which validates its callbacks: hand
    # it the real handler instead of the module-scope MagicMock stub.
    monkeypatch.setattr("utils.llm.providers._usage_callback", LLMUsageCallbackProbe())
    monkeypatch.setattr("utils.llm.usage_tracker.get_usage_callback", lambda: LLMUsageCallbackProbe())

    result = clients.get_llm("chat_metadata_extraction")

    assert captured["lane_id"] == "omi:auto:chat-metadata-extraction"
    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert result.request_timeout == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# 7. Prompt shapes: the deadline belongs to whole-content calls only
# ---------------------------------------------------------------------------


def test_transcript_prompt_carries_the_full_transcript_and_date_grounding(provider):
    _transcript_call()
    prompt = provider.invocations[0]
    assert "running with David near Boston" in prompt
    assert "Conversation Transcript" in prompt
    assert "2026-10-20" in prompt  # date_in_tz grounding of created_at


def test_structured_alias_feeds_the_note_text_not_a_second_pass(provider):
    class _Structured:
        title = "Morning run"
        overview = "Ran with David in Boston, planning next friday."

    llm_chat.retrieve_metadata_fields_from_structured(
        "uid-meta-deadline", datetime(2026, 10, 20, 12, 0, 0), _Structured(), "UTC"
    )
    prompt = provider.invocations[0]
    assert "Morning run" in prompt and "planning next friday" in prompt
    assert "Conversation Transcript" in prompt


def test_empty_content_never_invokes_the_provider(provider):
    """No transcript, no photos: the function short-circuits with empty filters."""
    metadata = llm_chat.retrieve_metadata_fields_from_transcript(
        uid="uid-meta-deadline", created_at=datetime(2026, 10, 20), transcript_segment=[], tz="UTC"
    )
    assert metadata == {"people": [], "topics": [], "entities": [], "dates": []}
    assert provider.resolved == [] and provider.invocations == []


def test_photo_descriptions_join_the_transcript_prompt(provider):
    from models.conversation_photo import ConversationPhoto

    photos = [ConversationPhoto(base64="x", description="Whiteboard with the Q2 numbers")]
    llm_chat.retrieve_metadata_fields_from_transcript(
        uid="uid-meta-deadline",
        created_at=datetime(2026, 10, 20, 12, 0, 0),
        transcript_segment=[{"text": "We reviewed the whiteboard."}],
        tz="UTC",
        photos=photos,
    )
    assert "Whiteboard with the Q2 numbers" in provider.invocations[0]
    assert "Photo Descriptions" in provider.invocations[0]


def test_provider_schema_violation_still_returns_empty_not_raises(provider, caplog):
    """A non-timeout provider error keeps the boundary's fail-soft contract."""

    def _broken(feature, *args, **kwargs):
        class _Bad:
            def with_structured_output(self, _schema):
                return self

            def invoke(self, _prompt):
                raise ValueError("model returned people as a string, not a list")

        return _Bad()

    original = llm_chat.get_llm
    llm_chat.get_llm = _broken
    import logging

    try:
        with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
            metadata = _transcript_call()
    finally:
        llm_chat.get_llm = original
    assert metadata == {"people": [], "topics": [], "entities": [], "dates": []}
    # The transcript-path boundary logs the typed, path-attributed line
    # (formerly the bare ``e {e}`` prod signature), not the message-path text.
    assert any("model returned people as a string" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# 8. Filter normalization on the surviving outputs
# ---------------------------------------------------------------------------


def test_filters_are_normalized_before_storage(provider):
    long_name = "Jean-Baptiste Emanuel Zorg"
    provider_result = llm_chat.retrieve_metadata_fields_from_transcript(
        uid="uid-meta-deadline",
        created_at=datetime(2026, 10, 20, 12, 0, 0),
        transcript_segment=[{"text": "Meeting note."}],
        tz="UTC",
    )
    assert isinstance(provider_result["people"], list)


def test_normalize_filter_drops_filler_and_standardizes_terms():
    assert llm_chat.normalize_filter("The Artificial Intelligence Lab") == "ai lab"
    assert llm_chat.normalize_filter("Machine Learning") == "ml"
    assert llm_chat.normalize_filter("of the and") == ""


def test_normalize_filter_caps_at_three_words_keeping_first_two_and_last():
    assert llm_chat.normalize_filter("one two three four five") == "one two five"
    assert llm_chat.normalize_filter("single") == "single"


def test_extracted_dates_are_bounded_relative_to_the_conversation(provider):
    """Dates the model emits are kept relative to the conversation's date, not
    dropped wholesale; the boundary re-formats what survived."""
    from utils.llm.temporal import normalize_extracted_dates

    reference = "2026-10-20"
    kept = normalize_extracted_dates(["2026-10-25", "2026-12-01", "not-a-date"], reference)
    assert kept == ["2026-10-25", "2026-12-01"]


def test_dates_far_beyond_the_lookahead_window_are_dropped(provider):
    """MAX_EXTRACTED_DATE_LOOKAHEAD_DAYS bounds hallucinated far-future dates."""
    from utils.llm.temporal import MAX_EXTRACTED_DATE_LOOKAHEAD_DAYS, normalize_extracted_dates
    from datetime import timedelta

    reference = "2026-10-20"
    inside = (datetime.strptime(reference, "%Y-%m-%d") + timedelta(days=MAX_EXTRACTED_DATE_LOOKAHEAD_DAYS)).strftime(
        "%Y-%m-%d"
    )
    outside = (
        datetime.strptime(reference, "%Y-%m-%d") + timedelta(days=MAX_EXTRACTED_DATE_LOOKAHEAD_DAYS + 1)
    ).strftime("%Y-%m-%d")
    kept = normalize_extracted_dates([inside, outside], reference)
    assert kept == [inside]


def test_unparseable_reference_keeps_parseable_dates():
    from utils.llm.temporal import normalize_extracted_dates

    assert normalize_extracted_dates(["2026-10-25"], "not-a-date") == ["2026-10-25"]
    assert normalize_extracted_dates(None, "2026-10-20") == []


# ---------------------------------------------------------------------------
# 9. Every other chat_extraction call site stays on the shared feature
# ---------------------------------------------------------------------------


def test_only_the_metadata_extractors_moved_off_chat_extraction():
    """Source pin: chat.py's remaining get_llm('chat_extraction') calls are the
    short interactive-chat prompts; the two whole-content extractors name the
    dedicated feature."""
    import re

    source = (BACKEND_DIR / "utils" / "llm" / "chat.py").read_text()
    calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
    assert calls.count("chat_metadata_extraction") == 2
    # The interactive prompts stay on the shared background-deadline lane.
    assert "chat_extraction" in calls
    # ExtractedInformation structured calls: only the two metadata extractors.
    structured_sites = re.findall(r"get_llm\('(\w+)'\)\.with_structured_output\(ExtractedInformation\)", source)
    assert sorted(structured_sites) == ["chat_metadata_extraction", "chat_metadata_extraction"]
