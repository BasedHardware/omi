"""Whole-external-text conversation structuring must not die on the background gateway deadline.

Live prod signature (pusher container, GCP, 2026-10-20/21, x16/30m):

    ERROR:utils.llm.gateway_error_contract:Conversation processing failed: TimeoutError
    [surfaced as] HTTPException: 500: Error processing conversation, please try again later

Root cause: external-integration and developer create-from-text conversations
finalize through ``_get_structured``, whose ``message``/``other`` source arms
call ``get_message_structure`` / ``summarize_experience_text``. Those build
``get_llm('external_structure')`` with no explicit deadline and feed the WHOLE
external text — the full imported message or document — into one structured
call. The feature had no entry in ``model_config._FOREGROUND_TIMEOUT_FEATURES``,
so the client inherited the background gateway transport deadline (15s to first
byte). The provider timeout raised, the ``_get_structured`` boundary mapped it
through ``conversation_processing_http_exception``, and the caller lost the
whole capture: no conversation row, no title, no summary, no action items.

Seventh instance of the class (see
``docs/operational/external-structure-foreground-deadline.md``). The fix
declares the deadline on the ``external_structure`` feature route itself —
unlike its siblings, that feature serves ONLY these two whole-content calls, so
no dedicated key is needed — and raises the generated lane's server-side budget
to cover the client deadline.

Failure-Class: FC-foreground-call-inherits-background-deadline — a
finalization call that cannot complete without a dependency answered inside
the shared client deadline sized for cheap background work. Fixed by
declaring the foreground deadline on the feature route and pinned by driving
the real production structurers against a provider slower than the background
deadline.

Failure-Class: FC-foreground-call-inherits-background-deadline — guard
surface: the family pins here and in the sibling deadline suites enumerate the
set so a future edit that restores the background deadline on any member fails
there.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-hermetic-tests")

import json  # noqa: E402
import re  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

import utils.llm.external_integrations as external_integrations  # noqa: E402
import utils.llm.model_config as model_config  # noqa: E402
from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# What the structuring provider really needs to answer a whole-external-text
# structured prompt. Longer than the 15s background first-byte deadline,
# comfortably inside the 60s foreground deadline.
PROVIDER_FIRST_BYTE_SECONDS = 25.0

# The payload shape a whole-text structured answer has (trimmed): title +
# overview, one action item, one event with an over-cap duration that the real
# post-processing must clamp.
_MODEL_ANSWER: dict = {
    "title": "Budget Lock-In",
    "overview": "Agreed over message to lock the Q2 budget and send the sheet.",
    "emoji": "🧠",
    "category": "business",
    "sections": [],
    "action_items": [{"description": "Send the landing page copy"}],
    "events": [
        {
            "title": "Budget review",
            "description": "Walk through the final scope",
            "start": "2026-10-27T15:00:00+00:00",
            "duration": 240,
        }
    ],
}


class _DeadlineTrackingProvider:
    """Provider seam enforcing the resolved deadline the way the real transport does.

    Deadlines resolve exactly like ``get_llm``: an explicit ``request_timeout``
    wins, then the feature route, then the background gateway transport
    deadline. Any invoke below ``PROVIDER_FIRST_BYTE_SECONDS`` raises the
    timeout the provider would raise — the exact prod failure shape.
    """

    def __init__(self):
        self.resolved: list = []
        self.invocations: list = []

    def __call__(self, feature, *args, **kwargs):
        deadline = kwargs.get("request_timeout")
        if deadline is None:
            deadline = model_config.feature_request_timeout(feature)
        if deadline is None:
            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        self.resolved.append((feature, deadline))
        provider = self
        current_deadline = deadline

        def _run(_prompt):
            payload = provider.invoke(current_deadline, _prompt)
            return AIMessage(content=json.dumps(payload))

        model = RunnableLambda(_run)

        def _structured(schema):
            return RunnableLambda(lambda _prompt: schema.model_validate(provider.invoke(current_deadline, _prompt)))

        model.with_structured_output = _structured
        return model

    def invoke(self, deadline, prompt):
        self.invocations.append(str(prompt))
        if deadline < PROVIDER_FIRST_BYTE_SECONDS:
            raise TimeoutError("Request timed out.")
        return _MODEL_ANSWER


@pytest.fixture
def provider(monkeypatch):
    """Install the deadline-tracking provider as the module's get_llm."""
    tracker = _DeadlineTrackingProvider()
    monkeypatch.setattr(external_integrations, "get_llm", tracker)
    return tracker


# ---------------------------------------------------------------------------
# Call-site drivers (the real production functions)
# ---------------------------------------------------------------------------


def _message_call():
    return external_integrations.get_message_structure(
        "Message from David about the Q2 budget: we should lock it today and send the sheet.",
        datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        "en",
        "UTC",
        "slack",
        output_language_code="en",
    )


def _experience_call():
    return external_integrations.summarize_experience_text(
        "Today I ran 10k along the river and finally booked the dentist for next friday.",
        "journal",
        tz="UTC",
    )


# ---------------------------------------------------------------------------
# 1. The feature route owns the deadline
# ---------------------------------------------------------------------------


def test_external_structure_declares_the_foreground_deadline():
    """Against unmodified source this fails: the feature inherited the client default."""
    assert model_config.feature_request_timeout("external_structure") == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_foreground_deadline_exceeds_what_the_provider_needs():
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > PROVIDER_FIRST_BYTE_SECONDS
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_the_foreground_family_stays_closed_over_its_members():
    """The class guard: every whole-content lane that runs while a user waits."""
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


def test_a_background_feature_keeps_the_default_deadline():
    assert model_config.feature_request_timeout("conv_folder") is None


def test_the_short_call_siblings_keep_their_own_routes():
    """The daily-summary lanes inside the same module are distinct features;
    this fix moves neither."""
    assert model_config.feature_request_timeout("daily_summary") == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert model_config.feature_request_timeout("daily_summary_simple") is None


# ---------------------------------------------------------------------------
# 2. get_llm hands every construction branch the feature deadline
# ---------------------------------------------------------------------------


def _capturing_gateway(monkeypatch, captured):
    import utils.llm.clients as clients

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, streaming=streaming, options=dict(options or {}), feature=feature)
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)


def test_get_llm_gateway_mode_passes_external_structure_the_foreground_deadline(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    import utils.llm.clients as clients

    clients.get_llm("external_structure")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert captured["feature"] == "external_structure"


def test_get_llm_managed_route_carries_the_foreground_deadline_even_when_optional_gateway_is_off(monkeypatch):
    captured: dict = {}
    _capturing_gateway(monkeypatch, captured)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: False)
    monkeypatch.setattr("utils.llm.clients.should_route_company_paid_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    import utils.llm.clients as clients

    clients.get_llm("external_structure")

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

    clients.get_llm("external_structure")

    assert captured["options"]["request_timeout"] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS
    assert captured["feature"] == "external_structure"


def test_byok_direct_construction_never_drops_below_the_foreground_deadline(monkeypatch):
    """The direct BYOK branch defaults to a 120s budget inside its client
    factory; pin the real constructed kwargs so a future edit that shrinks the
    BYOK budget under the whole-content deadline fails here instead of in prod."""
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

    clients.get_llm("external_structure")

    assert captured["model"], "the BYOK branch did not construct a client"
    assert captured["kwargs"]["request_timeout"] >= model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


def test_an_explicit_request_timeout_still_wins_over_the_route(monkeypatch):
    import utils.llm.clients as clients

    captured: dict = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(options=dict(options or {}))
        return object()

    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)
    monkeypatch.setattr("utils.llm.clients.should_route_features_through_gateway", lambda: True)
    monkeypatch.setattr("utils.llm.clients.get_byok_key", lambda *_a, **_k: None)

    clients.get_llm("external_structure", request_timeout=42.0)

    assert captured["options"]["request_timeout"] == 42.0


# ---------------------------------------------------------------------------
# 3. The structurers themselves, against a provider slower than the background deadline
# ---------------------------------------------------------------------------


def test_slow_provider_still_structures_a_message(provider):
    """Against unmodified source this is the failure that shipped: timeout, whole capture lost."""
    structured = _message_call()
    assert structured.title == "Budget Lock-In"
    assert structured.overview.startswith("Agreed over message to lock the Q2 budget")
    assert provider.resolved == [("external_structure", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_slow_provider_still_summarizes_an_experience(provider):
    structured = _experience_call()
    assert structured.title == "Budget Lock-In"
    assert provider.resolved == [("external_structure", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_the_structurer_sends_whole_external_content(provider):
    """The prompt carries the full external text — the call shape that needs 60s."""
    _message_call()
    assert provider.invocations, "the structurer never invoked the client"
    assert "Q2 budget" in provider.invocations[0]
    assert "slack" in provider.invocations[0]


def test_message_structurer_grounds_dates_in_the_conversation_started_at(provider):
    """The prompt template carries the started-at date and timezone grounding
    the extractor resolves relative dates against."""
    _message_call()
    prompt = provider.invocations[0]
    assert "2026-10-20" in prompt
    assert "UTC" in prompt


def test_extracted_events_keep_created_false_and_the_duration_cap(provider):
    """The structurer post-processes events: created stays False for sync-time
    refresh and the documented 180-minute cap clamps an over-cap event."""
    structured = _message_call()
    assert [(event.title, event.duration, event.created) for event in structured.events] == [
        ("Budget review", 180, False)
    ]


def test_extracted_action_items_get_a_created_at(provider):
    structured = _experience_call()
    assert [item.description for item in structured.action_items] == ["Send the landing page copy"]
    assert all(item.created_at is not None for item in structured.action_items)


def test_the_structurer_grounds_the_message_in_its_own_source_spec(provider):
    """A source spec names the sink in the prompt; the absent default is the
    generic Messaging App label the template documents."""
    external_integrations.get_message_structure(
        "Plain text without a spec.",
        datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        "en",
        "UTC",
        None,
        output_language_code="en",
    )
    assert "Messaging App" in provider.invocations[0]


def test_experience_structurer_keeps_the_day_grounding_in_the_prompt(provider):
    """summarize_experience_text grounds relative dates against today in the
    user's timezone — the grounding a background-deadline timeout discarded."""
    _experience_call()
    prompt = provider.invocations[0]
    assert "2026-10-20" in prompt or "2026-10-21" in prompt
    assert "UTC" in prompt
    assert "journal" in prompt


def test_each_structurer_resolves_the_deadline_exactly_once(provider):
    """One structured request per call — the deadline is inherited, not
    re-resolved per retry, and the fix adds no extra provider round-trip."""
    _message_call()
    _experience_call()
    assert provider.resolved == [
        ("external_structure", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS),
        ("external_structure", model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS),
    ]


# ---------------------------------------------------------------------------
# 4. Control: the background deadline is what lost the capture
# ---------------------------------------------------------------------------


def test_background_deadline_is_what_returned_the_500(provider, monkeypatch):
    """Put the background deadline back and the exact prod failure returns: the
    provider timeout raises out of the real structurer, and the boundary the
    caller runs maps it to the generic 500."""
    from fastapi import HTTPException

    from utils.llm.gateway_error_contract import (
        GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL,
        conversation_processing_http_exception,
    )

    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    with pytest.raises(TimeoutError):
        _message_call()

    try:
        _message_call()
    except TimeoutError as error:
        http_exc = conversation_processing_http_exception(error)
    assert isinstance(http_exc, HTTPException)
    assert http_exc.status_code == 500
    assert http_exc.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert provider.resolved == [
        ("external_structure", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS),
        ("external_structure", DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS),
    ]


def test_background_deadline_experience_path_also_raises(provider, monkeypatch):
    monkeypatch.setattr(model_config, "FOREGROUND_REQUEST_TIMEOUT_SECONDS", 15.0)
    with pytest.raises(TimeoutError):
        _experience_call()


def test_a_provider_slower_than_the_new_deadline_is_still_reported_fail_soft(provider, monkeypatch):
    """A timeout ABOVE the foreground deadline is a genuine provider-capacity
    signal: it keeps raising (and maps to the caller's 500) instead of being
    swallowed — the fix widens the window, it does not hide failures."""
    monkeypatch.setattr(provider, "invoke", lambda deadline, prompt: (_ for _ in ()).throw(TimeoutError("slow")))
    with pytest.raises(TimeoutError):
        _experience_call()


# ---------------------------------------------------------------------------
# 5. The gateway lane's server-side budget covers the client deadline
# ---------------------------------------------------------------------------


def test_generated_lane_exists_and_its_budget_covers_the_client_deadline():
    """The generated lane omi:auto:external-structure must exist and allow the
    60s foreground call: a lane budget shorter than the client deadline would
    abort the request server-side and reintroduce the prod failure with the
    deadline technically 'declared'."""
    import yaml

    from llm_gateway.gateway.config_loader import load_gateway_config
    from utils.llm.gateway_client import feature_auto_lane_id

    config = load_gateway_config(prod_mode=True)
    lane_id = feature_auto_lane_id("external_structure")
    assert lane_id == "omi:auto:external-structure"
    assert lane_id in config.lanes
    route = config.route_artifacts["route.external_structure.model_config.001"]
    assert route.timeouts.request_ms >= model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS * 1000

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())
    override = next(item for item in overrides["generated_route_overrides"] if item["feature"] == "external_structure")
    assert override["request_timeout_ms"] == 90000


def test_lane_primary_model_and_effort_are_unchanged_by_the_budget_raise():
    import yaml

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    by_feature = {item["feature"]: item for item in overrides}
    assert by_feature["external_structure"]["primary"] == {"provider": "openai", "model": "gpt-6-luna"}
    assert by_feature["external_structure"]["provider_options"] == {"reasoning_effort": "low"}


def test_no_other_lane_budget_was_changed_by_this_fix():
    """Only the external_structure override carries a request_timeout_ms — the
    budget raise must not leak onto any neighbouring lane."""
    import yaml

    overrides = yaml.safe_load((BACKEND_DIR / "llm_gateway" / "config" / "generated_route_overrides.yaml").read_text())[
        "generated_route_overrides"
    ]
    with_budgets = {item["feature"] for item in overrides if "request_timeout_ms" in item}
    assert with_budgets == {
        "chat_metadata_extraction",
        "external_structure",
        "memory_conflict_flex",
        "memory_l2_flex",
        "x_memory_extraction_flex",
    }


# ---------------------------------------------------------------------------
# 6. Route surface: same Luna route, BYOK unchanged
# ---------------------------------------------------------------------------


def test_route_resolution_matches_the_managed_luna_lane():
    assert model_config.get_model("external_structure") == model_config.get_model("conv_structure")
    assert model_config.get_provider("external_structure") == model_config.get_provider("conv_structure")


def test_byok_route_is_unchanged_by_the_deadline_declaration():
    byok_profile = model_config.MODEL_QOS_PROFILES["byok"]
    assert byok_profile["external_structure"] == byok_profile["conv_structure"]
    assert model_config.get_byok_provider("external_structure") == "openai"


def test_the_feature_appears_in_get_qos_info():
    import utils.llm.clients as clients

    info = clients.get_qos_info()
    assert info["external_structure"] == {
        "model": model_config.get_model("external_structure"),
        "profile": model_config.get_active_profile_name(),
        "provider": "openai",
    }


def test_structured_output_membership_stays_declared():
    """The feature rides the structured-output registry; the deadline change
    must not silently move it off the structured shapes."""
    from utils.llm.model_config import STRUCTURED_OUTPUT_FEATURES

    assert "external_structure" in STRUCTURED_OUTPUT_FEATURES


# ---------------------------------------------------------------------------
# 7. Only the two whole-content structurers use the feature
# ---------------------------------------------------------------------------


def test_external_structure_is_only_used_by_the_two_whole_content_structurers():
    """Source pin: nothing else may silently join a lane whose client deadline
    is now 60s; a new caller that wants the background deadline must pick a
    different feature."""
    source = (BACKEND_DIR / "utils" / "llm" / "external_integrations.py").read_text()
    calls = re.findall(r"get_llm\(\s*'(external_structure)'", source)
    assert len(calls) == 2

    other_files = [
        path
        for path in (BACKEND_DIR / "utils").rglob("*.py")
        if path.name not in ("external_integrations.py", "model_config.py")
    ]
    offenders = [
        str(path.relative_to(BACKEND_DIR))
        for path in other_files
        if re.search(r"get_llm\(\s*['\"]external_structure['\"]", path.read_text())
    ]
    assert offenders == []
