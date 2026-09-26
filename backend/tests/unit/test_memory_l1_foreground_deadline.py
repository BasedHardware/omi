"""Whole-transcript L1 memory extraction must not die on the background gateway deadline.

Live prod signature (pusher container, GCP, 2026-09-01..05, daily):

    ERROR:utils.llm.working_observations:Error extracting memory L1 archive items: invoke_failed:APITimeoutError

Root cause: ``extract_l1_memory_archive_items_from_text`` builds its client with
``get_llm('memory_l1')`` and no explicit deadline. The feature had no entry in
``_FOREGROUND_TIMEOUT_FEATURES``, so the client inherited the background gateway
transport deadline (15s to first byte). The L1 extractor reads the WHOLE
conversation transcript in one structured call — the same shape as
``conv_structure`` / ``conv_app_result`` / ``daily_summary``, which already
declare the foreground deadline after their own incidents — and conversation
finalization calls it with ``strict=True``, so the timeout raised, the strict
path converted it to ``WorkingObservationExtractionError``, and the run dropped
that conversation's entire memory batch (9-21 conversations/day losing every
memory, no retry).

This is the fifth instance of the class. The fix declares the deadline on the
feature route (``model_config._FOREGROUND_TIMEOUT_FEATURES``) — the deadline is a
property of the call, not of each call site.

Failure-Class: FC-foreground-call-inherits-background-deadline — a user-facing
call that cannot complete without a dependency answered inside the shared
client deadline sized for cheap background work. Fixed by declaring the
foreground deadline on the feature route and pinned by driving the real
production functions against a provider slower than the background deadline.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZw")
os.environ.setdefault("OPENAI_API_KEY", "***")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8787")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

import utils.llm.model_config as model_config  # noqa: E402
import utils.llm.working_observations as working_observations  # noqa: E402
from models.transcript_segment import TranscriptSegment  # noqa: E402
from utils.llm.memories import extract_canonical_l1_memory_candidates  # noqa: E402
from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS  # noqa: E402

# What the L1 extractor's provider really needs to answer a whole-transcript
# structured prompt. Longer than the 15s background first-byte deadline,
# comfortably inside the 60s foreground deadline.
PROVIDER_FIRST_BYTE_SECONDS = 25.0

_REQUEST = httpx.Request("POST", "https://gateway.invalid/v1/chat/completions")

_L1_BATCH_JSON = (
    '{"items": [{"text": "The user is preparing the launch deck for Friday.", '
    '"evidence_quotes": ["I am preparing the launch deck for Friday."], '
    '"speaker_label": "speaker_0", "about": "the user", "confidence": "high"}]}'
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
    """Record the deadline each get_llm('memory_l1') construction resolved to.

    Mirrors get_llm's own resolution: an explicit request_timeout wins, then the
    feature route, then the client default (the background transport deadline).
    """
    resolved: list[float] = []

    def _get_llm(feature, *args, **kwargs):
        request_timeout = kwargs.get("request_timeout")
        deadline = request_timeout if request_timeout is not None else model_config.feature_request_timeout(feature)
        if deadline is None:
            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        resolved.append(deadline)

        def _invoke(_messages):
            if deadline < PROVIDER_FIRST_BYTE_SECONDS:
                raise openai.APITimeoutError(request=_REQUEST)
            return AIMessage(content=_L1_BATCH_JSON)

        return RunnableLambda(_invoke)

    monkeypatch.setattr(working_observations, "get_llm", _get_llm)
    return resolved


def _extract_strict():
    return working_observations.extract_l1_memory_archive_items_from_text(
        uid="uid-l1-deadline",
        source_id="conversation-l1-deadline",
        source_type="voice_transcript",
        text="I am preparing the launch deck for Friday and I need the Q2 numbers.",
        user_name="David",
        strict=True,
        persist_route_outcomes=False,
    )


def _extract_graceful():
    return working_observations.extract_l1_memory_archive_items_from_text(
        uid="uid-l1-deadline",
        source_id="conversation-l1-deadline",
        source_type="voice_transcript",
        text="I am preparing the launch deck for Friday and I need the Q2 numbers.",
        user_name="David",
        strict=False,
        persist_route_outcomes=False,
    )


def _extract_via_wrapper():
    return extract_canonical_l1_memory_candidates(
        "uid-l1-deadline",
        "conversation-l1-deadline",
        SEGMENTS,
        user_name="David",
        language="en",
        strict=True,
    )


# ---------------------------------------------------------------------------
# 1. The feature route owns the deadline
# ---------------------------------------------------------------------------


def test_memory_l1_declares_the_foreground_deadline():
    """Against unmodified source this fails: memory_l1 inherited the client default."""
    assert model_config.feature_request_timeout("memory_l1") == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_foreground_deadline_exceeds_what_the_provider_needs():
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > PROVIDER_FIRST_BYTE_SECONDS
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_the_foreground_family_stays_closed_over_its_members():
    """The class guard: every whole-transcript lane that runs while a user waits."""
    assert model_config._FOREGROUND_TIMEOUT_FEATURES == frozenset(
        {"conv_structure", "conv_app_result", "daily_summary", "memory_l1"}
    )


def test_a_background_feature_keeps_the_default_deadline():
    assert model_config.feature_request_timeout("conv_folder") is None


def test_daily_summary_lane_is_part_of_the_foreground_family():
    """Sibling lane fixed in an earlier instance of the class; stays pinned."""
    for feature in ("conv_structure", "conv_app_result", "daily_summary"):
        assert model_config.feature_request_timeout(feature) == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# 2. get_llm hands every branch the feature deadline
# ---------------------------------------------------------------------------


def _capturing_gateway(monkeypatch, captured):
    import utils.llm.clients as clients

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, streaming=streaming, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)


def test_get_llm_gateway_mode_passes_memory_l1_the_foreground_deadline(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.llm.clients.maybe_wrap_dev_gateway_shadow", lambda **_k: _k["legacy_model"])

    import utils.llm.clients as clients

    clients.get_llm("memory_l1")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert captured["feature"] == "memory_l1"


def test_get_llm_direct_route_carries_the_foreground_deadline(monkeypatch):
    import utils.llm.clients as clients

    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: False)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    captured: dict = {}

    def fake_default_client(model, provider, streaming, options=None):
        captured.update(model=model, provider=provider, options=dict(options or {}))
        return object()

    monkeypatch.setattr(clients, "get_default_client", fake_default_client)
    monkeypatch.setattr(clients, "maybe_wrap_dev_gateway_shadow", lambda **_k: _k["legacy_model"])

    clients.get_llm("memory_l1")

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
    monkeypatch.setattr(clients, "maybe_wrap_dev_gateway_shadow", lambda **_k: _k["legacy_model"])

    clients.get_llm("memory_l1")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_get_llm_background_feature_stays_on_the_gateway_transport_deadline(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.llm.clients.maybe_wrap_dev_gateway_shadow", lambda **_k: _k["legacy_model"])

    import utils.llm.clients as clients

    clients.get_llm("conv_folder")

    assert "request_timeout" not in captured["options"]


def test_an_explicit_request_timeout_still_wins_over_the_route(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.llm.clients.maybe_wrap_dev_gateway_shadow", lambda **_k: _k["legacy_model"])

    import utils.llm.clients as clients

    clients.get_llm("memory_l1", request_timeout=42.0)

    assert captured["options"]["request_timeout"] == 42.0


# ---------------------------------------------------------------------------
# 3. The extractor itself, against a provider slower than the background deadline
# ---------------------------------------------------------------------------


def test_slow_provider_still_extracts_a_strict_batch(resolved_deadlines):
    """Against unmodified source this is the failure that shipped: APITimeoutError, zero items."""
    items = _extract_strict()
    assert items and items[0].text.startswith("The user is preparing")
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_slow_provider_still_extracts_a_graceful_batch(resolved_deadlines):
    items = _extract_graceful()
    assert items and items[0].text.startswith("The user is preparing")
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_slow_provider_still_extracts_through_the_canonical_wrapper(resolved_deadlines):
    candidates = _extract_via_wrapper()
    assert candidates and candidates[0].content.startswith("The user is preparing")
    assert resolved_deadlines == [model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS]


def test_background_deadline_is_what_lost_the_memories(resolved_deadlines, monkeypatch):
    """Control: put the background deadline back and the exact prod failure returns.

    Prod logged ``invoke_failed:APITimeoutError`` and the strict path dropped the
    conversation's memory batch; here the same timeout must surface as the
    extraction boundary's typed error chained to the provider timeout.
    """
    from models.memory_contracts import WorkingObservationExtractionError

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)

    with pytest.raises(WorkingObservationExtractionError) as raised:
        _extract_strict()
    assert raised.value.stage == "invoke"
    assert isinstance(raised.value.__cause__, openai.APITimeoutError)
    assert resolved_deadlines == [DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS]


def test_background_deadline_graceful_mode_returns_empty_not_raises(resolved_deadlines, monkeypatch):
    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)

    assert _extract_graceful() == []


def test_background_deadline_through_the_wrapper_strict_mode_raises(resolved_deadlines, monkeypatch):
    from models.memory_contracts import MemoryExtractionError

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)

    with pytest.raises(MemoryExtractionError):
        _extract_via_wrapper()


def test_strict_timeout_translates_to_the_extraction_error_not_the_provider_error(resolved_deadlines, monkeypatch):
    """The strict seam converts provider death to the boundary's own typed error."""
    from models.memory_contracts import WorkingObservationExtractionError

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)

    with pytest.raises(WorkingObservationExtractionError) as raised:
        _extract_strict()
    assert raised.value.stage == "invoke"


# ---------------------------------------------------------------------------
# 4. The invocation seam stays honest (the client is real, only the transport is slow)
# ---------------------------------------------------------------------------


def test_extractor_still_sends_the_whole_transcript_prompt(resolved_deadlines, monkeypatch):
    sent: list = []
    fixture_get_llm = working_observations.get_llm
    assert fixture_get_llm is not None, "resolved_deadlines fixture must install the provider stub"

    def _spy_get_llm(feature, *args, **kwargs):
        inner = fixture_get_llm(feature, *args, **kwargs)

        def _invoke(messages):
            sent.append(list(messages))
            return inner.invoke(messages)

        return RunnableLambda(_invoke)

    monkeypatch.setattr(working_observations, "get_llm", _spy_get_llm)

    _extract_strict()

    assert sent, "the extractor never invoked the client"
    assert any("launch deck" in str(message) for message in sent[0])


def test_extractor_bounding_and_ids_survive_the_slow_provider(resolved_deadlines):
    items = _extract_strict()
    assert items[0].archive_id.startswith("l1_")
    assert items[0].speaker_label == "speaker_0"
    assert items[0].confidence == "high"


def test_extractor_persists_no_archive_routes_for_wrapper_calls(resolved_deadlines, monkeypatch):
    """The canonical wrapper owns lifecycle writes; the extractor must not double-persist."""
    persisted: list = []

    def _spy_persist(**kwargs):
        persisted.append(kwargs)

    monkeypatch.setattr(working_observations, "_persist_l1_archive_route_outcomes", _spy_persist)

    _extract_via_wrapper()

    assert persisted == []
