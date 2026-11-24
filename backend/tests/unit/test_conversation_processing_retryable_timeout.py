"""A provider timeout must not become a user-visible conversation processing 500.

Live prod signature (ro-prod, 2026-11-16, group ``CNjqnsKjnOK17wE``, 771 events/24h):

    File "/app/utils/conversations/process_conversation.py", line 723, in _get_structured
      raise conversation_processing_http_exception(e) from e
    fastapi.exceptions.HTTPException: 500: Error processing conversation, please try again later
    [chained from]
    anthropic.APITimeoutError: Request timed out or interrupted.

The timeout is a transient provider fault, not an Omi-side processing bug and not
a terminal answer. The composition boundary answers the explicit retryable
contract (503 + ``Retry-After`` + a typed detail code) instead of the generic 500.
The mobile caller honors that contract with one delayed replay of the identical
in-progress request. The durable finalization lane keeps its own bounded retry
and dead-letter terminal.

This module covers backend classification, rollback and safe mapping. Mobile
tests cover retry success and bounded exhaustion; the existing conversation row
is re-admitted after a failed attempt.
"""

import asyncio
import logging
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import anthropic  # noqa: E402
import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from google.api_core.exceptions import ServiceUnavailable  # noqa: E402

from database import conversation_finalization_jobs as jobs_db  # noqa: E402
from utils.conversations import lifecycle as lifecycle_service  # noqa: E402
from utils.conversations.processing_metrics import RETRYABLE_PROCESSING_RESPONSES_TOTAL  # noqa: E402
from utils.conversations.processing_retry import (  # noqa: E402
    DETERMINISTIC_PROCESSING_FAILURE,
    TRANSIENT_PROCESSING_FAILURE,
    processing_failure_code,
)
from utils.llm.gateway_error_contract import (  # noqa: E402
    GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL,
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE,
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL,
    RETRYABLE_PROVIDER_FAILURE_SWITCH,
    conversation_processing_http_exception,
    is_retryable_processing_http_exception,
    is_retryable_provider_failure,
    retryable_provider_failure_answer_enabled,
)
from utils.observability.finalization import (  # noqa: E402
    FinalizationFailureReason,
    classify_finalization_failure,
)

_REQUEST = httpx.Request('POST', 'https://provider.invalid/v1/messages')


def anthropic_timeout() -> anthropic.APITimeoutError:
    """The exact class and message prod logged for the timeout cluster."""
    return anthropic.APITimeoutError(request=_REQUEST)


def openai_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=_REQUEST)


def provider_status(status: int) -> anthropic.APIStatusError:
    response = httpx.Response(status, request=_REQUEST)
    return anthropic.APIStatusError('synthetic provider failure', response=response, body=None)


# ---------------------------------------------------------------------------
# The mapping: transient provider faults answer retryable, everything else keeps
# its existing contract.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'failure',
    [
        pytest.param(anthropic_timeout(), id='anthropic_timeout'),
        pytest.param(openai_timeout(), id='openai_timeout'),
        pytest.param(httpx.ReadTimeout('synthetic', request=_REQUEST), id='httpx_read_timeout'),
        pytest.param(TimeoutError('notes loop deadline'), id='loop_deadline_timeout'),
        pytest.param(provider_status(503), id='provider_503'),
        pytest.param(provider_status(429), id='provider_429'),
    ],
)
def test_transient_provider_failure_answers_the_retryable_contract(failure):
    """The timeout class must never surface as the generic processing 500."""
    mapped = conversation_processing_http_exception(failure)

    assert mapped.status_code == 503
    assert mapped.detail == RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert mapped.detail['code'] == RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE
    assert mapped.headers['Retry-After'] == '2'
    # The generic 500 detail is what the prod error group counts; it must be gone.
    assert mapped.detail != GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert is_retryable_processing_http_exception(mapped)


def test_retryable_provider_answer_increments_the_bounded_response_metric():
    metric = RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(failure_class='timeout', route='conversation_processing')
    before = metric._value.get()

    mapped = conversation_processing_http_exception(anthropic_timeout())

    assert mapped.status_code == 503
    assert metric._value.get() == before + 1


def test_interrupted_request_is_the_same_retryable_class():
    """``APITimeoutError`` covers a dropped connection and a cancelled request too.

    The SDK raises the same class for all three, so the boundary must not try to
    tell them apart by message text.
    """
    interrupted = anthropic_timeout()
    assert 'interrupted' in str(interrupted)

    mapped = conversation_processing_http_exception(interrupted)

    assert mapped.status_code == 503
    assert is_retryable_processing_http_exception(mapped)


@pytest.mark.parametrize(
    'failure',
    [
        pytest.param(AttributeError('synthetic programming bug'), id='programming_error'),
        pytest.param(ValueError('notes parse failed'), id='parser_failure'),
        pytest.param(HTTPException(500, 'safe processing wrapper'), id='generic_processing_500'),
    ],
)
def test_non_provider_failures_keep_the_generic_500(failure):
    """A real processing fault is still a server fault and still a 500."""
    mapped = conversation_processing_http_exception(failure)

    assert mapped.status_code == 500
    assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert not is_retryable_processing_http_exception(mapped)


def test_byok_account_state_keeps_its_typed_429():
    """The user's own spent/limited key is account state, not a transient fault."""
    from utils.byok import set_byok_uid, set_validated_byok_keys

    body = {
        'type': 'error',
        'error': {
            'type': 'invalid_request_error',
            'message': 'Your credit balance is too low to access the Anthropic API.',
        },
    }
    set_validated_byok_keys({'anthropic': 'sk-ant-byok-unit'}, 'uid_byok_retryable')
    try:
        response = httpx.Response(400, request=_REQUEST, json=body)
        error = anthropic.BadRequestError(f'Error code: 400 - {body}', response=response, body=body)
        mapped = conversation_processing_http_exception(error)
    finally:
        set_validated_byok_keys({}, 'uid_byok_retryable')
        set_byok_uid(None)

    assert mapped.status_code == 429
    assert mapped.detail['code'] == 'byok_quota'
    assert not is_retryable_processing_http_exception(mapped)


@pytest.mark.parametrize('raw', [None, '', 'true', 'TRUE', 'on', '1', 'yes', 'unknown'])
def test_kill_switch_defaults_on(monkeypatch, raw):
    """Unset, blank and unknown values keep the reviewed retryable answer."""
    if raw is None:
        monkeypatch.delenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, raising=False)
    else:
        monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, raw)

    assert retryable_provider_failure_answer_enabled()
    assert conversation_processing_http_exception(anthropic_timeout()).status_code == 503


@pytest.mark.parametrize('raw', ['0', 'false', 'FALSE', 'no', 'off'])
def test_kill_switch_restores_the_previous_500(monkeypatch, raw):
    """Off restores the exact pre-fix answer; the conversation stays recoverable."""
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, raw)

    assert not retryable_provider_failure_answer_enabled()
    mapped = conversation_processing_http_exception(anthropic_timeout())
    assert mapped.status_code == 500
    assert mapped.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL


def test_sync_boundary_retries_provider_failures_but_not_local_database_faults():
    """The durable lane may retry local faults; the synchronous provider contract may not."""
    assert is_retryable_provider_failure(anthropic_timeout())
    assert processing_failure_code(anthropic_timeout()) == TRANSIENT_PROCESSING_FAILURE
    assert not is_retryable_provider_failure(ServiceUnavailable('synthetic database outage'))
    assert processing_failure_code(ServiceUnavailable('synthetic database outage')) == TRANSIENT_PROCESSING_FAILURE
    assert not is_retryable_provider_failure(ConnectionError('synthetic local connection failure'))
    assert processing_failure_code(AttributeError('synthetic')) == DETERMINISTIC_PROCESSING_FAILURE


def test_retryable_answer_does_not_change_durable_failure_classification():
    """The durable lane unwraps the typed response to its provider cause.

    ``finalizer`` classifies the source error, not the safe wrapper, so the new
    503 must still read as a provider failure there — otherwise the retryable
    timeout would be miscounted as an Omi-side processing bug.
    """
    timeout = anthropic_timeout()
    try:
        raise conversation_processing_http_exception(timeout) from timeout
    except HTTPException as wrapper:
        assert is_retryable_processing_http_exception(wrapper)
        assert classify_finalization_failure(wrapper.__cause__) == FinalizationFailureReason.provider
        # And the durable retry policy still sees a transient failure through the
        # wrapper, exactly as it did through the old 500.
        assert processing_failure_code(wrapper) == TRANSIENT_PROCESSING_FAILURE


# ---------------------------------------------------------------------------
# The admission guard: a retryable halt rolls the row back and logs bounded.
# ---------------------------------------------------------------------------


def _quiet_heartbeat(monkeypatch) -> None:
    monkeypatch.setattr(jobs_db, 'renew_processing_lease', lambda *_args: True)
    monkeypatch.setattr(lifecycle_service, '_processing_lease_renewal_interval', lambda: 60.0)


def _guard_failure_records(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == lifecycle_service.logger.name
        and 'synchronous conversation processing failed' in record.getMessage()
    ]


def test_guard_rolls_back_a_retryable_timeout_and_logs_without_a_traceback(monkeypatch, caplog):
    """The conversation returns to ``in_progress`` so the client's retry can re-admit it."""
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)
    rolled_back: list[tuple[str, str]] = []

    def fake_rollback(uid, conversation_id):
        rolled_back.append((uid, conversation_id))
        return True

    monkeypatch.setattr(lifecycle_service, 'rollback_processing_admission', fake_rollback)

    with pytest.raises(HTTPException) as raised:
        with lifecycle_service.processing_admission_guard('uid', 'conversation'):
            timeout = anthropic_timeout()
            raise conversation_processing_http_exception(timeout) from timeout

    assert raised.value.status_code == 503
    assert rolled_back == [('uid', 'conversation')]
    (record,) = _guard_failure_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert 'rolled_back=True' in record.getMessage()
    assert 'Traceback' not in caplog.text
    # Only the bounded class name is logged, never the provider message.
    assert 'Request timed out or interrupted' not in caplog.text


def test_guard_keeps_the_traceback_for_a_generic_processing_500(monkeypatch, caplog):
    """Control: a real processing fault is still an ERROR with its traceback."""
    _quiet_heartbeat(monkeypatch)
    caplog.set_level(logging.WARNING)

    with pytest.raises(HTTPException) as raised:
        with lifecycle_service.processing_admission_guard('uid', 'conversation', rollback_on_failure=False):
            try:
                raise ValueError('notes parse failed')
            except ValueError as error:
                raise conversation_processing_http_exception(error) from error

    assert raised.value.status_code == 500
    (record,) = _guard_failure_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None


# ---------------------------------------------------------------------------
# One structuring request: a typed timeout remains recoverable for the caller.
# ---------------------------------------------------------------------------


@pytest.fixture
def structuring_seam(monkeypatch):
    """Drive ``_get_structured`` to the notes call with everything else stubbed.

    Returns a callable that runs one structuring request and the notes-call
    counter, so these backend tests do not pretend to exercise the caller's
    separate bounded HTTP retry.
    """
    from datetime import datetime, timezone

    from models.conversation import Conversation
    from models.structured import Structured
    from utils.conversations import process_conversation as processing

    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'false')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', 'false')
    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'false')

    now = datetime(2026, 11, 16, 11, 2, tzinfo=timezone.utc)
    conversation = Conversation(
        id='conv-timeout',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(),
        status='processing',
        source='omi',
        transcript_segments=[dict(text='A tiny recording', speaker='SPEAKER_00', is_user=True, start=0, end=2)],
    )

    monkeypatch.setattr(processing.notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(processing.users_db, 'get_user_language_preference', lambda *_: 'en')
    monkeypatch.setattr(processing.redis_db, 'get_user_preferred_app', lambda *_: None)
    monkeypatch.setattr(
        processing, 'conversation_transcripts_for_llm', lambda *a: ('A tiny recording', 'A tiny recording', {})
    )
    monkeypatch.setattr(processing, 'should_discard_conversation', lambda *a, **kw: False)
    monkeypatch.setattr(processing, 'adjacent_conversation', lambda *a: None)
    monkeypatch.setattr(processing, 'calendar_overlap_retains_conversation', lambda *a: False)
    monkeypatch.setattr(processing, 'rich_notes_inputs', lambda *a, **kw: (None, None, None, None, 0))
    monkeypatch.setattr(processing, 'conversation_known_spellings', lambda *_: [])
    monkeypatch.setattr(processing, 'before_notes', lambda *a, **kw: None)
    monkeypatch.setattr(processing, '_fetch_dedup_candidates_for_query', lambda *a: [])
    monkeypatch.setattr(processing, 'notes_agent_inputs', lambda *a: {})

    attempts: list[int] = []

    def run(notes):
        """One structuring attempt; ``notes`` is the stubbed notes seam."""
        monkeypatch.setattr(processing, 'get_conversation_notes', notes)
        return processing._get_structured('uid-timeout', 'en', conversation)

    return run, attempts, conversation


def test_structuring_timeout_returns_a_typed_retryable_answer_without_persisting(structuring_seam):
    """The failed request leaves the existing row intact for the mobile retry."""
    run, attempts, conversation = structuring_seam
    before = conversation.model_dump()

    def notes(*args, **kwargs):
        attempts.append(1)
        raise anthropic_timeout()

    with pytest.raises(HTTPException) as raised:
        run(notes)

    assert raised.value.status_code == 503
    assert is_retryable_processing_http_exception(raised.value)
    assert len(attempts) == 1
    assert conversation.model_dump() == before
    assert conversation.status == 'processing'


def test_cancellation_propagates_from_the_structuring_call(structuring_seam):
    """A cancelled request is not remapped to an HTTP processing response."""
    run, attempts, conversation = structuring_seam
    before = conversation.model_dump()

    def notes(*args, **kwargs):
        attempts.append(1)
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        run(notes)

    assert len(attempts) == 1
    assert conversation.model_dump() == before


@pytest.mark.parametrize('path', ['/v1/conversations', '/v1/conversations/{conversation_id}/reprocess'])
def test_processing_routes_openapi_declare_the_typed_retryable_response(path):
    from routers.conversations import router

    route = next(route for route in router.routes if getattr(route, 'path', None) == path)
    responses = route.responses
    retryable_detail = responses[503]['content']['application/json']['schema']['properties']['detail']

    assert 500 in responses
    assert retryable_detail['properties']['code']['enum'] == ['conversation_processing_retryable']
