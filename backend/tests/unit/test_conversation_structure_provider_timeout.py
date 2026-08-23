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

import utils.llm.conversation_processing as processing  # noqa: E402
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
    """Stand in for the provider client, enforcing whatever deadline the caller asked for.

    Returns the list of request timeouts the production code requested, so a test can also state
    which deadline was in play when the call succeeded or failed.
    """

    requested: list[float | None] = []

    def _get_llm(feature, *args, request_timeout=None, **kwargs):
        requested.append(request_timeout)
        deadline = request_timeout if request_timeout is not None else DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

        def _invoke(_payload):
            if deadline < PROVIDER_FIRST_BYTE_SECONDS:
                raise openai.APITimeoutError(request=_REQUEST)
            return AIMessage(content=_RESPONSE_JSON)

        return RunnableLambda(_invoke)

    monkeypatch.setattr(processing, "get_llm", _get_llm)
    # The shadow comparison hands the same prompt to a second client on a background executor; it is
    # not part of the deadline contract under test.
    monkeypatch.setattr(processing, "_should_run_conversation_structure_shadow", lambda *a, **k: False)
    return requested


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


STRUCTURING_CALLS = [
    pytest.param(_structure, id='get_transcript_structure'),
    pytest.param(_reprocess_structure, id='get_reprocess_transcript_structure'),
    pytest.param(_conversation_notes, id='get_conversation_notes'),
]


@pytest.mark.parametrize('call', STRUCTURING_CALLS)
def test_slow_provider_still_produces_a_summary(call, slow_provider):
    """Against unmodified source this is the failure that shipped: APITimeoutError, no summary."""
    structured = call()

    assert structured.title == 'Budget Review'
    assert structured.overview.startswith('The team agreed')
    assert slow_provider[0] == processing.CONVERSATION_STRUCTURE_TIMEOUT_SECONDS


@pytest.mark.parametrize('call', STRUCTURING_CALLS)
def test_background_deadline_is_what_lost_the_conversation(call, slow_provider, monkeypatch):
    """Control: put the background deadline back and the exact prod exception returns."""
    monkeypatch.setattr(
        processing, 'CONVERSATION_STRUCTURE_TIMEOUT_SECONDS', DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
    )

    with pytest.raises(openai.APITimeoutError):
        call()


def test_foreground_deadline_exceeds_the_background_one():
    assert processing.CONVERSATION_STRUCTURE_TIMEOUT_SECONDS > DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
