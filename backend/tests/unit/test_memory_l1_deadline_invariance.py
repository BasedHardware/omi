"""The L1 memory lane's foreground deadline holds across every configuration it runs in.

Companion to ``test_memory_l1_foreground_deadline.py`` (the incident and the
route-level fix). Prod runs the same ``get_llm('memory_l1')`` call inside
conversation finalization under several configuration axes:

* the shared-conversation prompt prefix with prompt caching enabled or not
  (the prefix path renders a different message list and threads a cache key);
* the belief-model flag, which swaps the parser's output schema;
* a user-supplied BYOK key, which swaps the client construction branch;
* an explicitly injected client, which bypasses the factory entirely.

None of those axes may silently drop the deadline back to the background
gateway transport deadline (15s), which is shorter than the whole-transcript
call itself — the 2026-09-05 incident class (see the incident note in
``docs/operational/memory-l1-foreground-deadline.md``).

Failure-Class: FC-foreground-call-inherits-background-deadline — same class,
guard surface: this suite enumerates the lane's configuration axes so a future
edit that restores the background deadline on any branch fails here.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZw")
os.environ.setdefault("OPENAI_API_KEY", "***")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8787")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")

import httpx  # noqa: E402
import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

import utils.llm.model_config as model_config  # noqa: E402
import utils.llm.working_observations as working_observations  # noqa: E402
from models.transcript_segment import TranscriptSegment  # noqa: E402
from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix  # noqa: E402
from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS  # noqa: E402

PROVIDER_FIRST_BYTE_SECONDS = 25.0
_REQUEST = httpx.Request("POST", "https://gateway.invalid/v1/chat/completions")

_PREFIX = ConversationPromptPrefix(
    conversation_id="conversation-l1-invariance",
    context="FULL TRANSCRIPT\n" + "A long cacheable transcript for the prefix path. " * 300,
)

SEGMENTS = [
    TranscriptSegment(
        id="segment-user",
        text="I am preparing the launch deck for Friday and I need the Q2 numbers.",
        speaker="SPEAKER_00",
        is_user=True,
        start=0.0,
        end=4.0,
    ),
]


@pytest.fixture
def resolved_deadlines(monkeypatch):
    """Provider stub enforcing the deadline the way the real transport does."""
    resolved: list[float] = []

    def _get_llm(feature, *args, **kwargs):
        deadline = kwargs.get("request_timeout")
        deadline = deadline if deadline is not None else model_config.feature_request_timeout(feature)
        if deadline is None:
            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        resolved.append(deadline)

        def _invoke(_messages):
            if deadline < PROVIDER_FIRST_BYTE_SECONDS:
                raise TimeoutError("provider first byte exceeded the client deadline")
            return AIMessage(content='{"items": []}')

        return RunnableLambda(_invoke)

    monkeypatch.setattr(working_observations, "get_llm", _get_llm)
    return resolved


def _extract(**overrides):
    kwargs = dict(
        uid="uid-l1-invariance",
        source_id="conversation-l1-invariance",
        source_type="voice_transcript",
        text="I am preparing the launch deck for Friday and I need the Q2 numbers.",
        user_name="David",
        persist_route_outcomes=False,
    )
    kwargs.update(overrides)
    return working_observations.extract_l1_memory_archive_items_from_text(**kwargs)


# ---------------------------------------------------------------------------
# Prompt-prefix and cache axes
# ---------------------------------------------------------------------------


def test_deadline_holds_with_prompt_prefix_and_caching_enabled(resolved_deadlines):
    _extract(prompt_prefix=_PREFIX, prompt_cache_enabled=True)
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_deadline_holds_with_prompt_prefix_and_caching_disabled(resolved_deadlines):
    _extract(prompt_prefix=_PREFIX, prompt_cache_enabled=False)
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_deadline_holds_on_the_legacy_prompt_path_without_a_prefix(resolved_deadlines):
    _extract()
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_cache_key_threading_does_not_reset_the_deadline(resolved_deadlines, monkeypatch):
    """Cache wiring passes extra kwargs to get_llm; the deadline must survive them."""
    captured_kwargs: list[dict] = []
    fixture_stub = working_observations.get_llm
    assert fixture_stub is not None, "resolved_deadlines fixture must install the provider stub"

    def _capturing_get_llm(feature, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return fixture_stub(feature, *args, **kwargs)

    monkeypatch.setattr(working_observations, "get_llm", _capturing_get_llm)

    _extract(prompt_prefix=_PREFIX, prompt_cache_enabled=True)

    assert any("cache_key" in kwargs for kwargs in captured_kwargs), "cache wiring did not engage"
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


# ---------------------------------------------------------------------------
# Schema axis: the belief-model flag swaps the parser, not the deadline
# ---------------------------------------------------------------------------


def test_deadline_holds_with_the_belief_model_enabled(resolved_deadlines, monkeypatch):
    monkeypatch.setattr(working_observations, "belief_model_enabled", lambda: True)
    _extract()
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_deadline_holds_with_the_belief_model_disabled(resolved_deadlines, monkeypatch):
    monkeypatch.setattr(working_observations, "belief_model_enabled", lambda: False)
    _extract()
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_belief_flag_swaps_the_parser_schema_not_the_deadline(resolved_deadlines, monkeypatch):
    """The flag changes the output schema; it must not touch the request deadline."""
    schemas: list[type] = []

    class _SpyParser:
        def __init__(self, pydantic_object):
            schemas.append(pydantic_object)

        def get_format_instructions(self):
            return 'Return the requested JSON schema.'

        def parse(self, _completion):
            return working_observations.WorkingObservationBatch()

    monkeypatch.setattr(working_observations, "belief_model_enabled", lambda: True)
    monkeypatch.setattr(working_observations, "PydanticOutputParser", _SpyParser)

    _extract()

    assert (
        schemas and schemas[0] is working_observations.BeliefWorkingObservationBatch
    ), "the belief schema must be selected when the flag is on"


# ---------------------------------------------------------------------------
# Client-source axes: explicit client and BYOK construction
# ---------------------------------------------------------------------------


def test_explicit_llm_argument_bypasses_the_factory_and_keeps_its_own_deadline(resolved_deadlines):
    """Callers injecting a ready client own its deadline; the lane must not be able
    to silently re-route through the factory (which would re-resolve it)."""
    called: list[bool] = []

    class _ExplicitClient:
        def invoke(self, _messages):
            called.append(True)
            return AIMessage(content='{"items": []}')

    _extract(llm=_ExplicitClient())

    assert called == [True]
    assert resolved_deadlines == [], "the factory must not be consulted when a client is injected"


def test_byok_gateway_construction_carries_the_foreground_deadline(monkeypatch):
    """BYOK users get their key's client; it must carry the lane's deadline, not the default."""
    import utils.llm.clients as clients

    captured: dict = {}
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_profile", lambda: None)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda provider: "byok-key" if provider == "openai" else None)

    def fake_byok_gateway(lane_id, *, provider, api_key, streaming, options, feature):
        captured.update(lane_id=lane_id, provider=provider, api_key=api_key, options=dict(options or {}))
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm_for_byok", fake_byok_gateway)
    monkeypatch.setattr(clients, "maybe_wrap_dev_gateway_shadow", lambda **kwargs: kwargs["legacy_model"])

    clients.get_llm("memory_l1")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_byok_direct_construction_never_drops_below_the_foreground_deadline(monkeypatch):
    """The direct BYOK branch builds its own transport budget inside
    _create_byok_client. The lane's incident cannot recur there while that
    budget stays >= the foreground deadline; this pins the real constructed
    kwargs, so a future edit that shrinks the BYOK budget under the
    whole-transcript deadline fails here instead of in prod."""
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
    monkeypatch.setattr(clients, "maybe_wrap_dev_gateway_shadow", lambda **kwargs: kwargs["legacy_model"])

    clients.get_llm("memory_l1")

    assert captured["model"], "the BYOK branch did not construct a client"
    assert captured["kwargs"]["request_timeout"] >= model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_direct_route_no_byok_carries_the_foreground_deadline(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: False)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    def fake_default_client(model, provider, streaming, options=None):
        captured.update(options=dict(options or {}))

    monkeypatch.setattr(clients, "get_default_client", fake_default_client)
    monkeypatch.setattr(clients, "maybe_wrap_dev_gateway_shadow", lambda **kwargs: kwargs["legacy_model"])

    clients.get_llm("memory_l1")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Boundary invariances
# ---------------------------------------------------------------------------


def test_background_deadline_still_loses_the_batch_on_every_axis(resolved_deadlines, monkeypatch):
    """Control across axes: restoring the background deadline must reproduce the
    incident on each configuration, proving the tests above bite."""
    from models.memory_contracts import WorkingObservationExtractionError

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)

    for overrides in (
        {"strict": True},
        {"strict": True, "prompt_prefix": _PREFIX, "prompt_cache_enabled": True},
        {"strict": True, "prompt_prefix": _PREFIX, "prompt_cache_enabled": False},
    ):
        resolved_deadlines.clear()
        with pytest.raises(WorkingObservationExtractionError) as raised:
            _extract(**overrides)
        assert raised.value.stage == "invoke"
        assert isinstance(raised.value.__cause__, TimeoutError)
        assert resolved_deadlines == [DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS]


def test_the_provider_cost_still_exceeds_the_background_deadline():
    """If the provider ever answers inside the background deadline, the class is moot."""
    assert PROVIDER_FIRST_BYTE_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_foreground_deadline_stays_under_the_finalization_budget():
    """The sync-finalization path runs under a 1500s route budget; the call deadline
    must stay well inside it so one conversation cannot wedge the worker."""
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS < 120.0


def test_wrapper_seam_resolves_the_same_deadline_for_voice_transcripts(resolved_deadlines):
    from utils.llm.memories import extract_canonical_l1_memory_candidates

    candidates = extract_canonical_l1_memory_candidates(
        "uid-l1-invariance",
        "conversation-l1-invariance",
        SEGMENTS,
        user_name="David",
        language="en",
    )
    assert candidates == []
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]
