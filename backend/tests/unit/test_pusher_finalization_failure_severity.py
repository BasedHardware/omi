"""Pusher-side finalization failure severity follows terminality.

Production evidence (2026-09-06, prod-omi-backend): the pusher-container
lines ``pusher finalization failed … terminal=False`` and ``persisted
conversation finalization failed …`` fired at ERROR for retryable,
self-healing traffic — 5-7/30min bursts against ~210-255 healthy
processing/30min, with the same conversations later succeeding. That paged
operators via the log sentinel for in-flight work the system itself
scheduled for bounded retry.

The boundary mirrors the session-side reclassification
(listen_pusher_session, FC-request-input-rejection-escapes-as-server-fault):

- ``terminal=False`` (attempt budget remains; the job was marked retryable)
  is healthy in-flight work → WARNING.
- ``terminal=True`` (dead-lettered; retrying can never converge) is the
  genuine fault signal → stays ERROR.
- The persisted-finalizer per-attempt line is always WARNING: it fires on
  every failed attempt including ones whose conversation later succeeds;
  the authoritative terminality escalation lives in the pusher-side handler
  above it.
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import services.conversation_finalization as finalization_service
import utils.pusher_finalization as pusher_finalization
from utils.conversations.finalizer import ConversationFinalizationDisposition, ConversationFinalizationError
from database import conversation_finalization_jobs as jobs_db


class _PusherWebSocket:
    def __init__(self):
        self.sent = []

    async def send_bytes(self, payload):
        self.sent.append(payload)


@pytest.fixture
def inline_run_blocking(monkeypatch):
    async def _inline(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline)


def _claim(attempt_count):
    return MagicMock(return_value={'status': 'claimed', 'lease_epoch': 7, 'attempt_count': attempt_count})


@pytest.mark.anyio
async def test_owner_contention_stays_queued_without_completion_or_failure_budget(monkeypatch, inline_run_blocking):
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', _claim(attempt_count=4))
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(
            return_value=ConversationFinalizationDisposition.deferred,
        ),
    )
    retry, complete, dead_letter = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retry)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', complete)
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', dead_letter)
    websocket = _PusherWebSocket()
    await pusher_finalization.process_conversation_task(
        'uid-1',
        'conversation-1',
        'en',
        websocket,
        finalization_job_id='job-1',
        dispatch_generation=1,
    )
    retry.assert_not_called()
    complete.assert_not_called()
    dead_letter.assert_not_called()
    assert any(
        b'job_queued' in payload and b'"terminal":false' in payload.replace(b' ', b'') for payload in websocket.sent
    )


@pytest.mark.anyio
async def test_nonterminal_finalization_failure_logs_warning_not_error(monkeypatch, inline_run_blocking, caplog):
    # attempt_count=1 with retries remaining => mark_finalization_retryable,
    # terminal=False: the job stays armed for another attempt.
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', _claim(attempt_count=1))
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', MagicMock())
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    websocket = _PusherWebSocket()
    with caplog.at_level(logging.DEBUG, logger=pusher_finalization.logger.name):
        await pusher_finalization.process_conversation_task(
            'uid-1',
            'conversation-1',
            'en',
            websocket,
            finalization_job_id='job-1',
            dispatch_generation=1,
        )

    records = [r for r in caplog.records if 'pusher finalization failed' in r.getMessage()]
    assert records, 'expected a pusher finalization failure record'
    assert all(
        r.levelno == logging.WARNING for r in records
    ), 'terminal=False finalization failures are retryable in-flight work and must log at WARNING'
    assert all('terminal=False' in r.getMessage() for r in records)


@pytest.mark.anyio
async def test_terminal_finalization_failure_stays_error(monkeypatch, inline_run_blocking, caplog):
    # Exhausted attempt budget => dead-letter path, terminal=True.
    claim = _claim(attempt_count=1)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', claim)
    monkeypatch.setattr(
        pusher_finalization,
        'get_listen_finalization_tasks_max_attempts',
        MagicMock(return_value=1),
    )
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', MagicMock(return_value='dead_letter'))
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    websocket = _PusherWebSocket()
    with caplog.at_level(logging.DEBUG, logger=pusher_finalization.logger.name):
        await pusher_finalization.process_conversation_task(
            'uid-1',
            'conversation-1',
            'en',
            websocket,
            finalization_job_id='job-1',
            dispatch_generation=1,
        )

    records = [r for r in caplog.records if 'pusher finalization failed' in r.getMessage()]
    assert records, 'expected a pusher finalization failure record'
    assert all(
        r.levelno == logging.ERROR for r in records
    ), 'terminal=True dead-lettering is the fault signal and must stay at ERROR'
    assert all('terminal=True' in r.getMessage() for r in records)


@pytest.mark.anyio
async def test_first_exhaustion_requeue_queues_the_job_and_stays_warning(monkeypatch, inline_run_blocking, caplog):
    """First exhaustion grants the one delayed requeue: the session hears the
    existing job_queued shape (non-terminal) and the failure stays WARNING."""
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', _claim(attempt_count=0))
    monkeypatch.setattr(
        pusher_finalization,
        'get_listen_finalization_tasks_max_attempts',
        MagicMock(return_value=1),
    )
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', MagicMock(return_value='requeued'))
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    websocket = _PusherWebSocket()
    with caplog.at_level(logging.DEBUG, logger=pusher_finalization.logger.name):
        await pusher_finalization.process_conversation_task(
            'uid-1',
            'conversation-1',
            'en',
            websocket,
            finalization_job_id='job-1',
            dispatch_generation=1,
        )

    assert any(
        b'job_queued' in payload and b'"terminal":false' in payload.replace(b' ', b'') for payload in websocket.sent
    )
    records = [r for r in caplog.records if 'pusher finalization failed' in r.getMessage()]
    assert records, 'expected a pusher finalization failure record'
    assert all(r.levelno == logging.WARNING for r in records)
    assert all('terminal=False' in r.getMessage() for r in records)


@pytest.mark.anyio
async def test_byok_pusher_exhaustion_dead_letters_without_a_requeue(monkeypatch, inline_run_blocking, caplog):
    """BYOK jobs reach the hub via the pusher and are refused the requeue:
    first exhaustion dead-letters immediately, exactly as today."""
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', _claim(attempt_count=0))
    monkeypatch.setattr(
        pusher_finalization,
        'get_listen_finalization_tasks_max_attempts',
        MagicMock(return_value=1),
    )
    grant = MagicMock(return_value='conflict')
    monkeypatch.setattr(jobs_db, 'grant_finalization_budget_requeue', grant)
    monkeypatch.setattr(jobs_db, 'mark_finalization_dead_letter', MagicMock(return_value=True))
    monkeypatch.setattr(jobs_db, 'get_finalization_job', MagicMock(return_value={'budget_requeue_count': 0}))
    monkeypatch.setattr(
        finalization_service,
        'record_capture_finalization_terminal',
        MagicMock(),
    )
    monkeypatch.setattr(
        finalization_service,
        'record_conversation_finalization_client_terminal',
        MagicMock(),
    )
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    websocket = _PusherWebSocket()
    with caplog.at_level(logging.DEBUG, logger=pusher_finalization.logger.name):
        await pusher_finalization.process_conversation_task(
            'uid-1',
            'conversation-1',
            'en',
            websocket,
            byok_keys={'openai': 'sk-user'},
            finalization_job_id='job-1',
            dispatch_generation=1,
        )

    grant.assert_called_once_with('job-1', 1, 7, 'processing_failed')
    records = [r for r in caplog.records if 'pusher finalization failed' in r.getMessage()]
    assert records and all('terminal=True' in r.getMessage() for r in records)
    assert any(b'"terminal":true' in payload.replace(b' ', b'') for payload in websocket.sent)


@pytest.mark.anyio
async def test_terminal_byok_failure_keeps_the_warning_downclass(monkeypatch, inline_run_blocking, caplog):
    """The BYOK-aware severity downclass survives the requeue change: even at
    terminal=True, a BYOK provider failure stays WARNING, never ERROR."""
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', _claim(attempt_count=1))
    monkeypatch.setattr(
        pusher_finalization,
        'get_listen_finalization_tasks_max_attempts',
        MagicMock(return_value=1),
    )
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', MagicMock(return_value='dead_letter'))
    error = ConversationFinalizationError('processing_failed')
    error.__cause__ = HTTPException(503, detail={'code': 'byok_rate_limit'})
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=error),
    )

    websocket = _PusherWebSocket()
    with caplog.at_level(logging.DEBUG, logger=pusher_finalization.logger.name):
        await pusher_finalization.process_conversation_task(
            'uid-1',
            'conversation-1',
            'en',
            websocket,
            finalization_job_id='job-1',
            dispatch_generation=1,
        )

    records = [r for r in caplog.records if 'pusher finalization failed' in r.getMessage()]
    assert records, 'expected a pusher finalization failure record'
    assert all(r.levelno == logging.WARNING for r in records)
    assert all('terminal=True' in r.getMessage() for r in records)
