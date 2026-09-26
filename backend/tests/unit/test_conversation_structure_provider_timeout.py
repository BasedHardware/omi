"""Whole-transcript conversation structuring must not die on the background gateway deadline.

Live prod signature (backend image 920fc55, api.omi.me, 2026-08-19/20):

    File "/app/utils/conversations/process_conversation.py", line 473, in _get_structured
      raise conversation_processing_http_exception(e) from e
    fastapi.exceptions.HTTPException: 500: Error processing conversation, please try again later
    [chained from]
    File "/app/utils/llm/conversation_processing.py", line 1408, in get_reprocess_transcript_structure
      chain.invoke(
    openai.APITimeoutError: Request timed out.

Every affected request ended at the 15s gateway first-byte deadline -- 15.42s / 15.53s / 15.55s /
15.83s on POST /v1/conversations, POST /v1/conversations/from-segments and
POST /v1/conversations/{id}/reprocess -- and the conversation was finalized with no title, summary
or action items at all. Successful requests on those same routes already run to ~55s (p50 9.2s,
p90 41.0s, p99 51.8s), so 15s to first byte is simply too short for the call that summarizes a
whole transcript; it is sized for background feature calls.

The same class recurred on 2026-09-04 in the app/template summary, which was never given a
foreground deadline:

    File "/app/utils/conversations/process_conversation.py", line 784, in execute_app
      result = get_app_result(
    File "/app/utils/llm/conversation_processing.py", line 1588, in get_app_result
    httpcore.ReadTimeout: timed out
    [surfaced as] ERROR:utils.conversations.process_conversation:Error executing app: Request timed out.
    [then] Explicit app selection failed: Selected app <id> produced no summary content

128 of 412 app-selected POST /v1/conversations/{id}/reprocess calls returned 500 that way over
two days (31%), which is what users report as "my custom app does not work". The deadline is
therefore declared on the feature route now (model_config._FOREGROUND_TIMEOUT_FEATURES) rather than
at each call site, and this module covers every conversation summary that runs while a user waits.

The seam here is the provider client: it enforces the deadline the production function asked for,
exactly as httpx does, against a provider that needs longer than the background deadline to answer.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from datetime import datetime, timezone  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from models.app import App  # noqa: E402
import utils.llm.conversation_processing as processing  # noqa: E402
import utils.llm.model_config as model_config  # noqa: E402
from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix  # noqa: E402
from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS  # noqa: E402

# What the provider actually needs to answer a whole-transcript structuring prompt. Longer than the
# background first-byte deadline, comfortably inside the route's 120s TimeoutMiddleware budget.
PROVIDER_FIRST_BYTE_SECONDS = 25.0

_REQUEST = httpx.Request("POST", "https://gateway.invalid/v1/chat/completions")
_RESPONSE_JSON = (
    '{"title": "Budget Review", "overview": "The team agreed on the Q2 budget.", '
    '"emoji": "\\ud83e\\udde0", "category": "business", "sections": [], "action_items": [], "events": []}'
)
STARTED_AT = datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc)
TRANSCRIPT = "Speaker 0: we should lock the Q2 budget today. Speaker 1: agreed, sending the sheet."


@pytest.fixture
def slow_provider(monkeypatch):
    """Stand in for the provider client, enforcing whatever deadline the call would really get.

    Deadline resolution mirrors get_llm: an explicit request_timeout wins, otherwise the feature
    route supplies one, otherwise the client keeps the background gateway transport deadline. That
    resolution is itself covered at the get_llm seam in test_llm_gateway_client_config.py.

    Returns the resolved deadlines, so a test can also state which deadline was in play when the
    call succeeded or failed.
    """

    resolved: list[float] = []

    def _get_llm(feature, *args, request_timeout=None, **kwargs):
        deadline = request_timeout
        if deadline is None:
            deadline = model_config.feature_request_timeout(feature)
        if deadline is None:
            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        resolved.append(deadline)

        def _invoke(_payload):
            if deadline < PROVIDER_FIRST_BYTE_SECONDS:
                raise openai.APITimeoutError(request=_REQUEST)
            return AIMessage(content=_RESPONSE_JSON)

        return RunnableLambda(_invoke)

    monkeypatch.setattr(processing, "get_llm", _get_llm)
    # The shadow comparison hands the same prompt to a second client on a background executor; it is
    # not part of the deadline contract under test.
    monkeypatch.setattr(processing, "_should_run_conversation_structure_shadow", lambda *a, **k: False)
    return resolved


def _structure():
    return processing.get_transcript_structure(
        TRANSCRIPT,
        STARTED_AT,
        'en',
        'UTC',
        'test-uid',
    )


def _reprocess_structure():
    return processing.get_reprocess_transcript_structure(TRANSCRIPT, STARTED_AT, 'en', 'UTC')


def _conversation_notes():
    prefix = build_conversation_prompt_prefix(
        conversation_id='277d188e-9563-4fd1-bf1b-8a6bbcbe4b94',
        transcript=TRANSCRIPT,
        started_at=STARTED_AT,
        timezone_name='UTC',
        language_code='en',
    )
    return processing.get_conversation_notes(
        prefix,
        started_at=STARTED_AT,
        language_code='en',
        output_language_code=None,
        tz='UTC',
        task_intelligence_capture=False,
    )


# A user-authored template, exactly as the create-template sheet stores one.
TEMPLATE_APP = App(
    id='01KV5RBYY8H50HD9MBKY1ZPBSY',
    name='Meeting Recap',
    category='conversation-analysis',
    author='tester',
    description='Recaps a meeting.',
    image='/omi.png',
    capabilities={'memories'},
    memory_prompt='Summarize the decisions and who owns them.',
    private=True,
)


def _app_result_with_notes_prefix():
    """POST /reprocess?app_id= with CONVERSATION_NOTES_V2_ENABLED, which is how prod runs."""
    prefix = build_conversation_prompt_prefix(
        conversation_id='277d188e-9563-4fd1-bf1b-8a6bbcbe4b94',
        transcript=TRANSCRIPT,
        started_at=STARTED_AT,
        timezone_name='UTC',
        language_code='en',
    )
    return processing.get_app_result(TRANSCRIPT, [], TEMPLATE_APP, prompt_prefix=prefix)


def _app_result_legacy_prompt():
    return processing.get_app_result(TRANSCRIPT, [], TEMPLATE_APP)


def _summarizes(structured) -> None:
    assert structured.title == 'Budget Review'
    assert structured.overview.startswith('The team agreed')


def _returns_app_content(result) -> None:
    assert result.strip(), 'the selected app produced no summary content'
    assert 'Budget Review' in result


SUMMARY_CALLS = [
    pytest.param(_structure, _summarizes, id='get_transcript_structure'),
    pytest.param(_reprocess_structure, _summarizes, id='get_reprocess_transcript_structure'),
    pytest.param(_conversation_notes, _summarizes, id='get_conversation_notes'),
    pytest.param(_app_result_with_notes_prefix, _returns_app_content, id='get_app_result_notes_prefix'),
    pytest.param(_app_result_legacy_prompt, _returns_app_content, id='get_app_result_legacy_prompt'),
]


@pytest.mark.parametrize('call, expect', SUMMARY_CALLS)
def test_slow_provider_still_produces_a_summary(call, expect, slow_provider):
    """Against unmodified source this is the failure that shipped: APITimeoutError, no summary."""
    expect(call())

    assert slow_provider[0] == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize('call, expect', SUMMARY_CALLS)
def test_background_deadline_is_what_lost_the_conversation(call, expect, slow_provider, monkeypatch):
    """Control: put the background deadline back and the exact prod exception returns."""
    monkeypatch.setattr(
        processing, 'CONVERSATION_STRUCTURE_TIMEOUT_SECONDS', DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
    )
    monkeypatch.setattr(model_config, 'FOREGROUND_REQUEST_TIMEOUT_SECONDS', DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)

    with pytest.raises(openai.APITimeoutError):
        call()


def test_foreground_deadline_exceeds_the_background_one():
    assert model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
    assert processing.CONVERSATION_STRUCTURE_TIMEOUT_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS


def test_every_user_waiting_conversation_summary_feature_declares_the_deadline():
    """The three call-site fixes shared one cause; the route now owns the deadline for all of them."""
    for feature in ('conv_structure', 'conv_app_result', 'daily_summary'):
        assert model_config.feature_request_timeout(feature) == model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS

    # A background feature keeps the bounded transport deadline it was sized for.
    assert model_config.feature_request_timeout('conv_folder') is None
