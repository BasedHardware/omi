"""A v3 write refused after a long notes wait answers the retryable contract.

Live prod signature (SCA-5449, served build ``543aa7fb2a39``, 2026-11-28):
``POST /v1/conversations/:id/reprocess`` answered a bare 500 after 8-298 s,
every failure ending at ``utils/conversations/v3/processing.py`` with
``RuntimeError: v3_processing_not_completed``. The conversation was unchanged:
the write was refused (a newer transcript revision, a lost lease, another
writer) or the run returned without a completed status. That is retryable, so
the route answers the same typed 503 + Retry-After contract a transient
provider fault uses, and one line names the stage and notes lane that spent
the wait.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, Response

import routers.conversations as conv_router
from database.conversations_v3_fence import PersistenceDecline, ProcessingPersistenceFenced
from utils.conversations.processing_retry import ProcessingNotCompleted
from utils.conversations.v3 import processing
from utils.llm.gateway_error_contract import (
    GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL,
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE,
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL,
    RETRYABLE_PROVIDER_FAILURE_SWITCH,
)


def _conversation():
    return SimpleNamespace(
        id='c',
        is_locked=False,
        finished_at=None,
        tile_state=None,
        summary_retryable=None,
        model_dump=lambda: {'id': 'c', 'sync_content_revision': 1},
    )


def _run_external(monkeypatch, fn):
    monkeypatch.setattr(processing.leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(processing.leases, 'keepalive', lambda *a: nullcontext())
    monkeypatch.setattr(processing.leases, 'release', lambda *a: None)
    monkeypatch.setattr(processing.fence, 'writer', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(processing.models, 'notes_mode', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(processing.policy, 'explicit_retry', lambda *a, **kw: False)
    monkeypatch.setattr(processing.writers, 'begin_processing', lambda *a, **kw: True)
    monkeypatch.setattr(processing.writers, 'fail_processing', lambda *a, **kw: None)
    monkeypatch.setattr(processing.writers, 'settle_processing', lambda *a, **kw: True)
    monkeypatch.setattr(processing, 'enqueue', lambda *a, **kw: None)
    return processing.run_external(fn, 'u', 'en', _conversation())


def test_a_refused_write_names_the_persistence_stage(monkeypatch, caplog):
    monkeypatch.setattr(
        processing.fence,
        'persistence_declined',
        lambda: PersistenceDecline('source_changed', None, transient=True),
    )
    monkeypatch.setattr(processing, 'notes_stage', lambda: 'one_shot_notes')

    def fn(uid, language, conversation, *, persistence_observer, **kwargs):
        persistence_observer(False)
        return SimpleNamespace(status='completed')

    with caplog.at_level('WARNING'):
        with pytest.raises(ProcessingNotCompleted) as raised:
            _run_external(monkeypatch, fn)

    assert raised.value.stage == 'source_changed'
    assert raised.value.notes_stage == 'one_shot_notes'
    assert raised.value.elapsed_seconds >= 0.0
    assert 'event=v3_processing_not_completed stage=source_changed notes_stage=one_shot_notes' in caplog.text


def test_a_run_without_a_completed_status_names_the_completion_condition(monkeypatch):
    monkeypatch.setattr(processing.fence, 'persistence_declined', lambda: None)

    def fn(uid, language, conversation, *, persistence_observer, **kwargs):
        persistence_observer(True)
        return SimpleNamespace(status='processing')

    with pytest.raises(ProcessingNotCompleted) as raised:
        _run_external(monkeypatch, fn)

    assert raised.value.stage == 'status_not_completed'


@pytest.fixture
def reprocess_refusal(monkeypatch):
    """The real router up to execute_reprocess; the v3 writer is the only seam."""

    row = {'id': 'c', 'source': 'omi', 'language': 'en', 'status': 'completed'}
    monkeypatch.setattr(conv_router, '_get_valid_conversation_by_id', lambda *a, **kw: dict(row))
    monkeypatch.setattr(conv_router.conversations_db, 'is_soft_deleted', lambda conversation: False)
    monkeypatch.setattr(conv_router, 'python_owns_finalization', lambda conversation: True)
    monkeypatch.setattr(conv_router.transcribing_hold, 'retry_pending', lambda conversation: False)
    monkeypatch.setattr(conv_router.historical_projection, 'admit_reprocess', lambda *a, **kw: [])
    monkeypatch.setattr(conv_router.historical_projection, 'release', lambda *a, **kw: None)
    monkeypatch.setattr(conv_router, 'deserialize_conversation', lambda conversation: SimpleNamespace(language='en'))
    from database import processing_attention as attention_db

    monkeypatch.setattr(attention_db, 'generation', lambda conversation: 0)
    monkeypatch.setattr(attention_db, 'claim', lambda *a, **kw: ({'id': 'operation'}, True))
    monkeypatch.setattr(attention_db, 'owns_live_claim', lambda *a, **kw: True)
    finished = []
    monkeypatch.setattr(attention_db, 'finish', lambda uid, operation, outcome: finished.append(outcome))
    return finished


def _call_reprocess():
    return conv_router.reprocess_conversation(
        conversation_id='c', uid='u', response=Response(), background_tasks=BackgroundTasks()
    )


def test_reprocess_answers_the_typed_retryable_contract(reprocess_refusal, monkeypatch):
    monkeypatch.delenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, raising=False)
    monkeypatch.setattr(
        conv_router,
        'execute_reprocess',
        lambda *a, **kw: (_ for _ in ()).throw(
            ProcessingNotCompleted('source_changed', elapsed_seconds=118.4, notes_stage='one_shot_notes')
        ),
    )

    with pytest.raises(HTTPException) as raised:
        _call_reprocess()

    assert raised.value.status_code == 503
    assert raised.value.detail == RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert raised.value.detail['code'] == RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE
    assert raised.value.headers['Retry-After'] == '2'
    assert reprocess_refusal == ['failed']


def test_a_persistence_fence_is_the_same_retryable_refusal(reprocess_refusal, monkeypatch):
    monkeypatch.delenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, raising=False)
    monkeypatch.setattr(
        conv_router,
        'execute_reprocess',
        lambda *a, **kw: (_ for _ in ()).throw(ProcessingPersistenceFenced('v3_processing_not_completed')),
    )

    with pytest.raises(HTTPException) as raised:
        _call_reprocess()

    assert raised.value.status_code == 503
    assert raised.value.detail == RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL


def test_the_kill_switch_restores_the_generic_500(reprocess_refusal, monkeypatch):
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, 'off')
    monkeypatch.setattr(
        conv_router,
        'execute_reprocess',
        lambda *a, **kw: (_ for _ in ()).throw(ProcessingNotCompleted('source_changed')),
    )

    with pytest.raises(HTTPException) as raised:
        _call_reprocess()

    assert raised.value.status_code == 500
    assert raised.value.detail == GENERIC_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert reprocess_refusal == ['failed']
