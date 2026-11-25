"""/reprocess of a discarded batch row: visibility waits for the restore obligation.

The real router, real processor and real restore run against the strict store. Only
the external model and app boundaries are controlled.
"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException, Response
from openai import APITimeoutError, AuthenticationError, RateLimitError

import routers.conversations as conv_router
from database import apps as apps_db
from database import notifications as notification_db
from database import conversations as conversations_db
from database import dream_dirty
from database import processing_attention as attention_db
from models.structured import Structured
from tests.unit.test_restore_recording_obligation import CID, JOB_PATH, ROW_PATH, UID, restore_store  # noqa: F401
from utils import apps as utils_apps
from utils.batch_pipeline import live
from utils.conversations import process_conversation as processor
from utils.llm import conversation_processing as llm_processing
from utils.llm.clients import _LLMErrorCallback
from utils.llm.gateway_error_contract import GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL

APP_ID = 'summary-app'


@pytest.fixture
def reprocess(restore_store, monkeypatch):
    row = restore_store.rows[ROW_PATH]
    row.update(
        {
            'status': 'completed',
            'source': 'omi',
            'language': 'en',
            'created_at': row.get('created_at', '2026-11-01T00:00:00+00:00'),
            'started_at': '2026-11-01T00:00:00+00:00',
            'finished_at': '2026-11-01T00:10:00+00:00',
            'structured': {},
            'transcript_segments': [],
            'photos': [],
        }
    )
    monkeypatch.setattr(
        conv_router, '_get_valid_conversation_by_id', lambda uid, cid: deepcopy(restore_store.rows[ROW_PATH])
    )
    monkeypatch.setattr(conv_router, 'schedule_reprocessed_learning', lambda uid, processed, *a, **k: processed)
    monkeypatch.setattr(
        processor,
        '_get_structured',
        lambda *a, **k: (Structured(title='Synthetic title', overview='Synthetic overview'), False),
    )
    monkeypatch.setattr(processor, 'extract_memories', MagicMock(), raising=False)
    monkeypatch.setattr(processor, 'save_structured_vector', MagicMock(), raising=False)
    # The selected app is validated against the app store and the user's enablement; the
    # app model call returns the summary. The processor's real explicit-selection check runs on it.
    app = SimpleNamespace(
        id=APP_ID,
        name='Synthetic app',
        description='Synthetic description',
        memory_prompt='Summarize this',
        disabled=False,
        enabled=True,
        works_with_memories=lambda: True,
    )
    monkeypatch.setattr(apps_db, 'get_app_by_id_db', lambda app_id: {'id': app_id})
    monkeypatch.setattr(utils_apps, 'get_available_app_model_by_id', lambda *a, **k: app)
    monkeypatch.setattr(utils_apps, 'is_user_app_enabled', lambda *a, **k: True)
    monkeypatch.setattr(processor, 'get_available_apps', lambda uid: [app])
    # The app prompt reads the user's timezone from Firestore; without it the app call fails
    # before the model boundary, which would look like an empty summary.
    monkeypatch.setattr(notification_db, 'get_user_time_zone', lambda uid: '')
    monkeypatch.setattr(processor, 'get_app_result', lambda *a, **k: 'Synthetic app summary.')
    monkeypatch.setattr(processor, 'record_app_usage', MagicMock())
    # Dream dirty marking is out of scope; its marker needs a document update StrictFirestore omits.
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'off')
    # The app-output write goes through update(), which StrictFirestore omits; merge into the row instead.
    monkeypatch.setattr(
        conversations_db,
        'update_conversation',
        lambda uid, cid, data, **kwargs: restore_store.rows[ROW_PATH].update(deepcopy(data)) or True,
    )
    monkeypatch.setattr(attention_db, 'claim', lambda *a, **k: ({'id': 'operation'}, True))
    monkeypatch.setattr(attention_db, 'owns_live_claim', lambda uid, operation: True)
    monkeypatch.setattr(attention_db, 'finish', lambda *a, **k: None)
    return restore_store


def _call():
    return conv_router.reprocess_conversation(
        conversation_id=CID, app_id=APP_ID, uid=UID, response=Response(), background_tasks=BackgroundTasks()
    )


def _count_restore_registrations(monkeypatch):
    registrations = []
    original = live.register_recording

    def counting(uid, conversation, **kwargs):
        registrations.append(kwargs.get('restoring'))
        return original(uid, conversation, **kwargs)

    monkeypatch.setattr(live, 'register_recording', counting)
    return registrations


def test_successful_reprocess_restores_with_exactly_one_obligation(reprocess, monkeypatch):
    registrations = _count_restore_registrations(monkeypatch)

    processed = _call()

    assert registrations == [True]
    assert reprocess.rows[ROW_PATH]['discarded'] is False
    assert processed.discarded is False
    assert reprocess.rows[JOB_PATH]['state'] == 'record_pending'


@pytest.mark.parametrize(
    ('outcome', 'status', 'code', 'logged_class'),
    [
        ('quota', 429, 'byok_quota', 'byok_quota'),
        ('rate_limit', 429, 'byok_rate_limit', 'byok_rate_limit'),
        ('rejected_key', 429, 'byok_invalid_key', 'byok_invalid_key'),
        ('timeout', 503, 'conversation_processing_retryable', 'timeout'),
        ('timeout_switch_off', 500, None, 'APITimeoutError'),
        ('empty_model_output', 502, 'app_result_failed', 'empty_model_output'),
        ('empty_context', 502, 'app_result_failed', 'empty_context'),
        ('bug', 500, None, 'RuntimeError'),
    ],
)
def test_reprocess_app_result_failure_keeps_the_row_hidden(
    reprocess, monkeypatch, caplog, outcome, status, code, logged_class
):
    registrations = _count_restore_registrations(monkeypatch)
    monkeypatch.setattr(processor, 'get_app_result', llm_processing.get_app_result)
    transcript = '' if outcome == 'empty_context' else 'Synthetic transcript.'
    monkeypatch.setattr(processor, 'conversation_transcript_for_llm', lambda *a, **k: transcript)
    monkeypatch.setenv(
        'CONVERSATION_PROCESSING_RETRYABLE_PROVIDER_FAILURE_ENABLED', '0' if outcome.endswith('_off') else '1'
    )
    request = httpx.Request('POST', 'https://example.invalid')
    private_message = 'raw provider message'
    provider_classes = {'quota': 'byok_quota', 'rate_limit': 'byok_rate_limit', 'rejected_key': 'byok_auth'}
    original = None
    if outcome in provider_classes:
        sdk_status = 401 if outcome == 'rejected_key' else 429
        error_type = AuthenticationError if sdk_status == 401 else RateLimitError
        original = error_type(
            private_message,
            response=httpx.Response(sdk_status, request=request),
            body={'error': {'code': 'credential_failure', 'failure_class': provider_classes[outcome]}},
        )
    elif outcome.startswith('timeout'):
        original = APITimeoutError(request=request)
    elif outcome == 'bug':
        original = RuntimeError(private_message)

    def invoke(_messages):
        if original is not None:
            _LLMErrorCallback('openai', feature='conv_app_result').on_llm_error(original)
            raise original
        return SimpleNamespace(content=' ``` ``` ')

    model = MagicMock()
    model.invoke.side_effect = invoke
    monkeypatch.setattr(llm_processing, 'get_llm', lambda *a, **k: model)

    with pytest.raises(HTTPException) as error:
        _call()

    assert error.value.status_code == status
    if code:
        assert error.value.detail['code'] == code
    else:
        assert error.value.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert (error.value.headers or {}).get('Retry-After') == ('2' if status == 503 else None)
    assert isinstance(error.value.__cause__, processor.ExplicitAppSelectionFailedError)
    assert error.value.__cause__.__cause__ is original
    assert model.invoke.call_count == (0 if outcome == 'empty_context' else 1)
    gateway_logs = [record.getMessage() for record in caplog.records if record.name.endswith('gateway_error_contract')]
    assert len(gateway_logs) == 1
    assert logged_class in gateway_logs[0]
    if code:
        assert 'route=conversation_processing/app_result' in gateway_logs[0]
    assert private_message not in caplog.text
    assert private_message not in str(error.value.detail)
    assert registrations == []
    assert reprocess.rows[ROW_PATH]['discarded'] is True
    assert JOB_PATH not in reprocess.rows
