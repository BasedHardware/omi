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

import utils.pusher_finalization as pusher_finalization
from utils.conversations.finalizer import ConversationFinalizationError
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
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', MagicMock(return_value=True))
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
