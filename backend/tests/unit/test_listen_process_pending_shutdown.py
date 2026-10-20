"""Regression: a listen session ending inside the 7s window must still finalize pending work.

LiveConversationController.process_pending defers finalization by 7 seconds, then finalizes the
timed-out conversation and re-dispatches anything still stuck in `processing`. The listen split
turned the original unconditional `await asyncio.sleep(7.0)` into `if await self.host.wait(7):
return`. host.wait is wait_for_event(shutdown_event, seconds), which returns True when woken
early by shutdown, and runtime sets shutdown_event immediately before draining background tasks
without cancelling them. So any session ending inside that window returned early and skipped both
the timed-out conversation's finalization and the processing re-dispatch.

The `if ...: return` form is the polling-loop idiom (lifecycle_loop correctly uses
`if await self.host.wait(5): break`). process_pending is a one-shot deferred action, so an early
wake must shorten the wait, not cancel the work.

Seam: the controller takes only a host, so this subclasses it to record the two finalization
calls and drives the real process_pending. No patching and no sys.modules mutation.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import conversations as conversations_db
from database.conversations import select_stale_in_progress
from routers.listen.conversations import STALE_IN_PROGRESS_RECOVERY_AGE_SECONDS, LiveConversationController


class _Host:
    """Minimal listen host. wait() returns True to mean 'woken early by shutdown'."""

    def __init__(
        self,
        *,
        woken_by_shutdown: bool,
        processing: list[dict[str, str]],
        stale_in_progress: list[dict[str, str]] | None = None,
        current_conversation_id: str | None = None,
    ) -> None:
        self.request = SimpleNamespace(uid='uid-1')
        self.state = SimpleNamespace(current_conversation_id=current_conversation_id)
        self._woken_by_shutdown = woken_by_shutdown
        self._results_by_function = {
            'get_processing_conversations': processing,
            'get_stale_in_progress_conversations': stale_in_progress or [],
        }
        self.waited: list[float] = []
        self.persistence = SimpleNamespace(call=self._call)
        self.speakers = SimpleNamespace(refresh_for_conversation=AsyncMock())

    async def wait(self, seconds: float) -> bool:
        self.waited.append(seconds)
        return self._woken_by_shutdown

    async def _call(self, fn, *_args, **_kwargs):
        return self._results_by_function[fn.__name__]


class _RecordingController(LiveConversationController):
    """Records the finalization calls instead of touching Firestore."""

    def __init__(self, host: _Host) -> None:
        super().__init__(host)
        self.processed: list[str] = []
        self.scheduled: list[str] = []

    async def process_conversation(self, conversation_id: str) -> bool:
        self.processed.append(conversation_id)
        return True

    async def schedule_finalization(self, conversation_id: str) -> bool:
        self.scheduled.append(conversation_id)
        return True


async def test_session_ending_inside_the_window_still_finalizes():
    host = _Host(woken_by_shutdown=True, processing=[{'id': 'conv-processing'}])
    controller = _RecordingController(host)

    await controller.process_pending('conv-timed-out')

    # An early shutdown wake must not drop the pending finalization work.
    assert controller.processed == ['conv-timed-out']
    assert controller.scheduled == ['conv-processing']
    assert host.waited == [7]


async def test_normal_session_finalizes_after_the_full_delay():
    host = _Host(woken_by_shutdown=False, processing=[{'id': 'conv-processing'}])
    controller = _RecordingController(host)

    await controller.process_pending('conv-timed-out')

    assert controller.processed == ['conv-timed-out']
    assert controller.scheduled == ['conv-processing']


async def test_no_timed_out_conversation_still_redispatches_processing():
    host = _Host(woken_by_shutdown=True, processing=[{'id': 'conv-a'}, {'id': 'conv-b'}])
    controller = _RecordingController(host)

    await controller.process_pending(None)

    assert controller.processed == []
    assert controller.scheduled == ['conv-a', 'conv-b']


# ── Stale in_progress recovery (#9809) ──────────────────────────────────────


async def test_process_pending_recovers_stale_in_progress_conversations():
    """Orphaned in_progress rows route through process_conversation, which already
    finalizes content and deletes empty rows — the same call a live timeout makes."""
    host = _Host(
        woken_by_shutdown=False,
        processing=[{'id': 'conv-processing'}],
        stale_in_progress=[{'id': 'conv-orphan-old'}, {'id': 'conv-orphan-newer'}],
    )
    controller = _RecordingController(host)

    await controller.process_pending(None)

    assert controller.scheduled == ['conv-processing']
    assert controller.processed == ['conv-orphan-old', 'conv-orphan-newer']


async def test_recovery_never_touches_the_sessions_current_conversation():
    host = _Host(
        woken_by_shutdown=False,
        processing=[],
        stale_in_progress=[{'id': 'conv-live'}, {'id': 'conv-orphan'}],
        current_conversation_id='conv-live',
    )
    controller = _RecordingController(host)

    await controller.process_pending(None)

    assert controller.processed == ['conv-orphan']


# ── A conversation whose finalization always fails must not end the session ──
#
# process_pending is a supervised finite task: an exception escaping it is a
# supervisor "crash" that tears the listen socket down. In prod a stale
# in_progress conversation at Firestore's 1 MiB document limit failed its
# finalization write every time, so every reconnect for that user died seconds
# after it started and the client reconnected in a loop.


class _OversizedDocument(Exception):
    """Stands in for the Firestore InvalidArgument an oversized document write raises."""


class _FailingController(_RecordingController):
    """Records every attempt and raises for the configured conversation ids."""

    def __init__(self, host: _Host, *, failing: set[str]) -> None:
        super().__init__(host)
        self.failing = failing

    async def process_conversation(self, conversation_id: str) -> bool:
        self.processed.append(conversation_id)
        if conversation_id in self.failing:
            raise _OversizedDocument('document exceeds the maximum allowed size')
        return True

    async def schedule_finalization(self, conversation_id: str) -> bool:
        self.scheduled.append(conversation_id)
        if conversation_id in self.failing:
            raise _OversizedDocument('document exceeds the maximum allowed size')
        return True


async def test_failing_stale_conversation_does_not_crash_the_sweep(caplog):
    host = _Host(
        woken_by_shutdown=False,
        processing=[],
        stale_in_progress=[{'id': 'conv-oversized'}, {'id': 'conv-orphan'}],
    )
    controller = _FailingController(host, failing={'conv-oversized'})

    with caplog.at_level('ERROR', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    # The sweep returned normally and still recovered the row behind the failing one.
    assert controller.processed == ['conv-oversized', 'conv-orphan']
    failures = [r.getMessage() for r in caplog.records if 'pending finalization failed' in r.getMessage()]
    assert failures == [
        'Listen pending finalization failed stage=stale_in_progress conversation=conv-oversized '
        'type=_OversizedDocument reason=other document=none'
    ]


async def test_failing_timed_out_and_processing_rows_do_not_skip_the_rest():
    host = _Host(
        woken_by_shutdown=False,
        processing=[{'id': 'conv-processing-bad'}, {'id': 'conv-processing-ok'}],
        stale_in_progress=[{'id': 'conv-orphan'}],
    )
    controller = _FailingController(host, failing={'conv-timed-out', 'conv-processing-bad'})

    await controller.process_pending('conv-timed-out')

    assert controller.processed == ['conv-timed-out', 'conv-orphan']
    assert controller.scheduled == ['conv-processing-bad', 'conv-processing-ok']


# ── A row at the 1 MiB ceiling is closed, not retried by every reconnect ────
#
# Prod (2026-09-30..10-04): five in_progress rows whose documents sat just under
# Firestore's 1 MiB ceiling failed their finalization binding on every session
# (stale_in_progress/InvalidArgument, up to 120 times per row). The isolation
# above kept the socket alive but the rows stayed invisible forever.

_SIZE_LIMIT_MESSAGE = (
    "Document 'projects/p/databases/(default)/documents/users/{uid}/conversations/{cid}' cannot be "
    "written because its size (1,048,684 bytes) exceeds the maximum allowed size of 1,048,576 bytes."
)

_EXPIRED_ERROR_TEXT = 'The referenced transaction has expired or is no longer valid.'


def _size_limit_error(cid: str, *, uid: str = 'uid-1', collection: str = 'conversations') -> InvalidArgument:
    message = _SIZE_LIMIT_MESSAGE.format(uid=uid, cid=cid)
    if collection != 'conversations':
        message = message.replace('/conversations/', f'/{collection}/')
    return InvalidArgument(message)


class _RaisingController(_RecordingController):
    """process_conversation raises the configured exception per conversation id."""

    def __init__(self, host: _Host, *, errors: dict[str, BaseException]) -> None:
        super().__init__(host)
        self.errors = errors
        self.completed_events: list[str] = []

    async def process_conversation(self, conversation_id: str) -> bool:
        self.processed.append(conversation_id)
        if conversation_id in self.errors:
            raise self.errors[conversation_id]
        return True

    def on_conversation_processed(self, conversation_id: str) -> None:
        self.completed_events.append(conversation_id)


class _RaisingScheduleController(_RaisingController):
    """schedule_finalization (the `processing` stage's seam) raises instead."""

    async def schedule_finalization(self, conversation_id: str) -> bool:
        self.scheduled.append(conversation_id)
        if conversation_id in self.errors:
            raise self.errors[conversation_id]
        return True


class _CloseHost(_Host):
    """Host whose persistence also answers the lifecycle oversize close."""

    def __init__(self, *, close_outcome: object = 'closed', **kwargs) -> None:
        super().__init__(woken_by_shutdown=False, processing=[], **kwargs)
        self.close_outcome = close_outcome
        self.close_calls: list[tuple] = []

    async def _call(self, fn, *args, **kwargs):
        if fn.__name__ == 'close_oversized_in_progress_conversation':
            self.close_calls.append((args, kwargs))
            if isinstance(self.close_outcome, BaseException):
                raise self.close_outcome
            return self.close_outcome
        return await super()._call(fn, *args, **kwargs)


def _messages(caplog) -> list[str]:
    # The boundary logs at ERROR and (for deferred transients) WARNING only;
    # filtering by level keeps DEBUG-level runs free of unrelated INFO noise.
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == 'routers.listen.conversations' and record.levelno >= logging.WARNING
    ]


async def test_stale_row_at_the_size_ceiling_is_closed_instead_of_retried(caplog):
    host = _CloseHost(stale_in_progress=[{'id': 'conv-oversized'}, {'id': 'conv-orphan'}])
    controller = _RaisingController(host, errors={'conv-oversized': _size_limit_error('conv-oversized')})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    # The lifecycle owner is asked to close exactly that row, fenced on an hour of quiet.
    assert host.close_calls == [
        (('uid-1', 'conv-oversized'), {'quiet_for': timedelta(seconds=STALE_IN_PROGRESS_RECOVERY_AGE_SECONDS)})
    ]
    assert controller.completed_events == ['conv-oversized']
    # The rest of the sweep still ran.
    assert controller.processed == ['conv-oversized', 'conv-orphan']
    messages = _messages(caplog)
    assert (
        'Listen pending finalization hit the document size limit stage=stale_in_progress '
        'conversation=conv-oversized close=closed'
    ) in messages
    assert not [m for m in messages if 'pending finalization failed' in m]
    # The Firestore message carries the uid-bearing document path; it is never logged.
    assert not [m for m in caplog.text.splitlines() if 'uid-1' in m]


async def test_refused_close_leaves_the_row_and_reports_the_fence(caplog):
    host = _CloseHost(close_outcome='recent_write', stale_in_progress=[{'id': 'conv-oversized'}])
    controller = _RaisingController(host, errors={'conv-oversized': _size_limit_error('conv-oversized')})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    assert len(host.close_calls) == 1
    assert controller.completed_events == []
    assert (
        'Listen pending finalization hit the document size limit stage=stale_in_progress '
        'conversation=conv-oversized close=recent_write'
    ) in _messages(caplog)


async def test_lifecycle_rollover_size_rejection_also_routes_to_the_close():
    host = _CloseHost()
    controller = _RaisingController(host, errors={'conv-live': _size_limit_error('conv-live')})

    await controller._finalize_isolated(controller.process_conversation, 'conv-live', stage='lifecycle_rollover')

    assert [args for args, _ in host.close_calls] == [('uid-1', 'conv-live')]
    assert controller.completed_events == ['conv-live']


async def test_size_rejection_naming_another_document_is_not_a_close(caplog):
    """Only a rejection of the row's own document proves the row itself is at the ceiling."""
    host = _CloseHost(stale_in_progress=[{'id': 'conv-a'}, {'id': 'conv-b'}])
    errors = {
        'conv-a': _size_limit_error('conv-other'),
        'conv-b': _size_limit_error('conv-b', collection='people'),
    }
    controller = _RaisingController(host, errors=errors)

    with caplog.at_level('ERROR', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    assert host.close_calls == []
    assert _messages(caplog) == [
        'Listen pending finalization failed stage=stale_in_progress conversation=conv-a '
        'type=InvalidArgument reason=document_size_limit document=conversation',
        'Listen pending finalization failed stage=stale_in_progress conversation=conv-b '
        'type=InvalidArgument reason=document_size_limit document=other',
    ]


@pytest.mark.parametrize(
    ('error', 'reason'),
    [
        (ValueError('Failed to commit transaction in 5 attempts.'), 'contention'),
        (Aborted('Too much contention on these documents. Please try again.'), 'contention'),
        (InvalidArgument('The referenced transaction has expired or is no longer valid.'), 'expired_transaction'),
        (Aborted('409 The referenced transaction has expired or is no longer valid.'), 'expired_transaction'),
        (ValueError('something else'), 'other'),
    ],
)
async def test_transient_failures_are_classified_and_left_for_the_next_sweep(caplog, error, reason):
    host = _CloseHost(stale_in_progress=[{'id': 'conv-a'}])
    controller = _RaisingController(host, errors={'conv-a': error})

    with caplog.at_level('DEBUG', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    assert host.close_calls == []
    assert controller.completed_events == []
    if reason == 'expired_transaction':
        # A rejected attempt that wrote nothing and whose id is already retired
        # is deferred at WARNING: the row's retention is the retry, and the
        # ERROR variant is the one that reached prod (2026-10-14).
        assert _messages(caplog) == [
            f'Listen pending finalization deferred stage=stale_in_progress conversation=conv-a '
            f'type={type(error).__name__} reason={reason} document=none'
        ]
    else:
        assert _messages(caplog) == [
            f'Listen pending finalization failed stage=stale_in_progress conversation=conv-a '
            f'type={type(error).__name__} reason={reason} document=none'
        ]


async def test_failing_close_does_not_crash_the_sweep(caplog):
    host = _CloseHost(
        close_outcome=Aborted('Too much contention on these documents. Please try again.'),
        stale_in_progress=[{'id': 'conv-oversized'}, {'id': 'conv-orphan'}],
    )
    controller = _RaisingController(host, errors={'conv-oversized': _size_limit_error('conv-oversized')})

    with caplog.at_level('ERROR', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    assert controller.processed == ['conv-oversized', 'conv-orphan']
    assert controller.completed_events == []
    assert _messages(caplog) == [
        'Listen oversized conversation close failed stage=stale_in_progress conversation=conv-oversized '
        'type=Aborted reason=contention'
    ]


async def test_cancellation_still_propagates_out_of_the_sweep():
    """Isolation is for ordinary failures only; drain must still be able to cancel the task."""

    class _CancelledController(_RecordingController):
        async def process_conversation(self, conversation_id: str) -> bool:
            raise asyncio.CancelledError

    host = _Host(woken_by_shutdown=False, processing=[{'id': 'conv-processing'}])
    controller = _CancelledController(host)

    with pytest.raises(asyncio.CancelledError):
        await controller.process_pending('conv-timed-out')
    assert controller.scheduled == []


# ── A transient rejection must not kill the supervised lifecycle task ───────
#
# Failure-Class: FC-listen-finalizer-transient-exhaustion-crashes-supervised-task
# (new class declared in this diff; the nearest existing classes own the
# adjacent halves — FC-retired-transaction-treated-as-fatal owns the
# transaction-id restart at the storage boundary, and
# FC-recording-session-open-aborted-as-failed-write owns the recording-session
# writers, whose missed fifth writer — the empty-generation delete — this diff
# also moves onto the shared contention budget. Neither owns the isolation
# boundary itself: when the bounded budget exhausts, the raise escapes into
# the listen session's supervised `lifecycle` task through
# `create_new_in_progress_conversation(rollover=True)` one line after the
# finalize and tears the socket down — `BG task ws:...:lifecycle crashed:
# InvalidArgument('The referenced transaction has expired...')`, ×32/30m —
# and the rollover stage logged the same rejection at ERROR loudness
# (`Listen pending finalization failed stage=lifecycle_rollover`, ×135/30m;
# prod backend-listen 2026-10-14). The boundary now defers an expired
# transaction at WARNING with the row retained: the rejected attempt wrote
# nothing, and the next sweep/poll replays it on a brand-new transaction for
# free. Cancellation is re-raised, not swallowed, so drain still owns
# teardown.)
#
# Prod (backend-listen 2026-10-14, x32/30m): the rollover finalize's expired-id
# rejection escaped `_finalize_isolated` into `create_new_in_progress_conversation(rollover=True)`
# — one line later in the same `lifecycle_loop` iteration — so the supervised
# `lifecycle` task crashed and the socket was torn down for a failure the next
# 5-second poll replays for free. The x135/30m
# `pending finalization failed stage=lifecycle_rollover` ERROR was the same
# rejection at ERROR loudness instead of a crash; expired transactions are now
# a deferred WARNING across every stage.


class _TransientHost(_CloseHost):
    """Host whose every persistence call raises the expired-id rejection."""

    async def _call(self, fn, *args, **kwargs):
        raise InvalidArgument(_EXPIRED_ERROR_TEXT)


class _LifecycleHost(_CloseHost):
    """Host for the real lifecycle_loop: one idle in_progress row, then shutdown."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state.active = True
        self.state.current_conversation_id = 'conv-live'
        self.conversation_creation_timeout = 120.0
        self.transcripts = SimpleNamespace(flush_speaker_assignments=AsyncMock())
        self.rows = {
            'conv-live': {
                'id': 'conv-live',
                'status': 'in_progress',
                'finished_at': datetime.now(timezone.utc) - timedelta(hours=2),
            }
        }
        self._wait_calls = 0

    async def wait(self, seconds: float) -> bool:
        self._wait_calls += 1
        # First iteration: poll runs. Second: end the loop like a shutdown wake.
        return self._wait_calls > 1

    async def _call(self, fn, *args, **kwargs):
        if fn.__name__ == 'get_conversation':
            return self.rows.get(args[1])
        return await super()._call(fn, *args, **kwargs)


class _LifecycleController(_RaisingController):
    """Drives the real lifecycle_loop with a failing rollover finalize."""

    def __init__(self, host: _LifecycleHost, *, errors: dict[str, BaseException]) -> None:
        super().__init__(host, errors=errors)
        self.created_rollover = False

    async def create_new_in_progress_conversation(self, *, rollover: bool = False) -> None:
        if rollover:
            self.created_rollover = True
        self.host.state.active = False

    async def flush_speaker_assignments(self, conversation_id) -> None:
        return None

    async def _continuity_row(self, row: dict[str, Any]) -> dict[str, Any]:
        # No calendar identity on these rows; skip the continuity transaction.
        return row


async def test_expired_transaction_does_not_crash_the_lifecycle_loop():
    """A transient rejection is retained by the rollover stage; the loop survives
    and proceeds to the new conversation instead of crashing the supervised task."""
    host = _LifecycleHost()
    controller = _LifecycleController(host, errors={'conv-live': InvalidArgument(_EXPIRED_ERROR_TEXT)})

    await controller.lifecycle_loop()

    assert controller.created_rollover is True
    assert controller.processed == ['conv-live']


async def test_size_limit_in_the_rollover_stage_still_routes_to_the_close_and_creates():
    """The permanent arm is unchanged by the transient arm: close, then rollover."""
    host = _LifecycleHost()
    controller = _LifecycleController(host, errors={'conv-live': _size_limit_error('conv-live')})

    await controller.lifecycle_loop()

    assert [args for args, _ in host.close_calls] == [('uid-1', 'conv-live')]
    assert controller.completed_events == ['conv-live']
    assert controller.created_rollover is True


async def test_error_escaping_the_rollover_stage_still_reaches_create_new():
    """A non-expired, non-size failure keeps its ERROR but never kills the loop:
    the pre-existing guarantee the crash fix must not quietly narrow."""
    host = _LifecycleHost()
    controller = _LifecycleController(host, errors={'conv-live': ValueError('something else')})

    await controller.lifecycle_loop()

    assert controller.created_rollover is True
    assert controller.processed == ['conv-live']


async def test_missing_conversation_row_rolls_over_without_finalizing():
    """The create_new arm of the same loop is untouched by the finalize arm."""
    host = _LifecycleHost()
    host.rows.clear()
    controller = _LifecycleController(host, errors={})

    await controller.lifecycle_loop()

    assert controller.created_rollover is True
    assert controller.processed == []


async def test_non_idle_conversation_continues_without_finalizing():
    """The continue_current arm: a refreshed row finishes the poll untouched."""
    host = _LifecycleHost()
    host.rows['conv-live']['finished_at'] = datetime.now(timezone.utc) - timedelta(seconds=10)
    controller = _LifecycleController(host, errors={})

    await controller.lifecycle_loop()

    assert controller.created_rollover is False
    assert controller.processed == []
    assert host.close_calls == []


async def test_processing_status_row_is_not_finalized_by_the_lifecycle_loop():
    """A row already in `processing` (dispatched) is left to its durable job."""
    host = _LifecycleHost()
    host.rows['conv-live']['status'] = 'processing'
    controller = _LifecycleController(host, errors={})

    await controller.lifecycle_loop()

    assert controller.created_rollover is True
    assert controller.processed == []
    assert host.close_calls == []


class _FinalizeHost(_LifecycleHost):
    """Host that answers the three persistence calls `process_conversation` makes."""

    def __init__(self, *, delete_result: bool, reread: dict[str, Any] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.recording_session_ids_by_conversation = {'conv-live': 'session-1'}
        self._delete_result = delete_result
        self._reread = reread
        self.is_multi_channel = False
        self.state.first_audio_byte_timestamp = 1.0
        self.delete_calls: list[tuple] = []

    async def _call(self, fn, *args, **kwargs):
        if fn.__name__ == 'delete_empty_recording_conversation':
            self.delete_calls.append(args)
            return self._delete_result
        if fn.__name__ == 'get_conversation':
            # process_conversation reads twice: the pre-delete read must see an
            # empty row (or the schedule arm runs), the post-delete reread
            # answers with the configured snapshot.
            if kwargs.get('read_site') is not None and 'post_delete_reread' in str(kwargs['read_site']).lower():
                return self._reread
            return {'id': 'conv-live', 'status': 'in_progress'}
        return await super()._call(fn, *args, **kwargs)


class _PlainController(LiveConversationController):
    """Real process_conversation/schedule_finalization; only the dispatch seam recorded."""

    def __init__(self, host: Any) -> None:
        super().__init__(host)
        self.scheduled: list[str] = []

    async def schedule_finalization(self, conversation_id: str) -> bool:
        self.scheduled.append(conversation_id)
        return True


async def test_process_conversation_empty_delete_wins_and_skips_dispatch():
    host = _FinalizeHost(delete_result=True)
    controller = _PlainController(host)

    assert await controller.process_conversation('conv-live') is True
    assert controller.scheduled == []
    assert [args[:3] for args in host.delete_calls] == [('uid-1', 'conv-live', 'session-1')]


async def test_process_conversation_delete_refused_with_late_content_dispatches():
    """Late content arriving before the delete keeps the row and dispatches it."""
    host = _FinalizeHost(
        delete_result=False,
        reread={'id': 'conv-live', 'transcript_segments': [{'id': 'late'}]},
    )
    controller = _PlainController(host)

    assert await controller.process_conversation('conv-live') is True
    assert controller.scheduled == ['conv-live']


async def test_process_conversation_delete_refused_still_empty_is_a_no_op():
    host = _FinalizeHost(delete_result=False, reread={'id': 'conv-live'})
    controller = _PlainController(host)

    assert await controller.process_conversation('conv-live') is False
    assert controller.scheduled == []


async def test_expired_on_the_first_sweep_row_does_not_skip_the_rest(caplog):
    """The sweep-level isolation composes with the transient arm."""
    host = _CloseHost(stale_in_progress=[{'id': 'conv-expired'}, {'id': 'conv-fine'}])
    errors = {'conv-expired': InvalidArgument(_EXPIRED_ERROR_TEXT)}
    controller = _RaisingController(host, errors=errors)

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    assert controller.processed == ['conv-expired', 'conv-fine']
    assert [m for m in _messages(caplog) if 'deferred' in m] != []
    assert [m for m in _messages(caplog) if 'pending finalization failed' in m] == []


def test_contention_is_not_transient():
    """An Aborted burst that exhausts the budget is contention, not a deferral:
    it is a real operational event and keeps its ERROR."""
    from utils.conversations.finalization_failure import classify_finalization_failure

    failure = classify_finalization_failure(Aborted('Too much contention on these documents.'), 'conv-a')

    assert failure.reason == 'contention'
    assert failure.transient is False


def test_size_limit_naming_another_row_is_not_transient():
    from utils.conversations.finalization_failure import classify_finalization_failure

    failure = classify_finalization_failure(_size_limit_error('conv-other'), 'conv-a')

    assert failure.reason == 'document_size_limit'
    assert failure.conversation_at_size_limit is False
    assert failure.transient is False


async def test_emit_lifecycle_event_without_durable_binding_is_suppressed(caplog):
    """The completed-event emitter keeps its no-binding guard on the same path."""
    host = _LifecycleHost()
    host.recording_session_ids_by_conversation = {}
    controller = _LifecycleController(host, errors={})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.emit_recording_lifecycle_event('conv-live', 'completed')

    assert [m for m in _messages(caplog) if 'Suppressing lifecycle event' in m] != []


async def test_expired_at_the_timed_out_stage_defers_and_still_redispatches_processing(caplog):
    host = _Host(woken_by_shutdown=False, processing=[{'id': 'conv-processing'}])
    controller = _RaisingController(host, errors={'conv-timed-out': InvalidArgument(_EXPIRED_ERROR_TEXT)})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.process_pending('conv-timed-out')

    assert controller.processed == ['conv-timed-out']
    assert controller.scheduled == ['conv-processing']
    assert [m for m in _messages(caplog) if 'deferred stage=timed_out' in m] != []


async def test_expired_at_the_processing_stage_defers_and_keeps_the_stale_recovery(caplog):
    host = _Host(
        woken_by_shutdown=False,
        processing=[{'id': 'conv-processing-bad'}],
        stale_in_progress=[{'id': 'conv-orphan'}],
    )
    controller = _RaisingScheduleController(host, errors={'conv-processing-bad': InvalidArgument(_EXPIRED_ERROR_TEXT)})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.process_pending(None)

    assert controller.processed == ['conv-orphan']
    assert controller.scheduled == ['conv-processing-bad']
    assert [m for m in _messages(caplog) if 'deferred stage=processing' in m] != []


async def test_the_expired_error_names_no_document_kind_of_its_own(caplog):
    """document=none for a rejection that names no uid-bearing path at all."""
    host = _CloseHost()
    controller = _RaisingController(host, errors={'conv-live': InvalidArgument(_EXPIRED_ERROR_TEXT)})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller._finalize_isolated(controller.process_conversation, 'conv-live', stage='lifecycle_rollover')

    assert [m for m in _messages(caplog) if 'document=none' in m] != []


async def test_the_lifecycle_loop_polls_a_fresh_row_after_a_deferred_rollover(caplog):
    """After the deferral the loop created the new generation: the deferred row's
    content is now finalized by the NEXT session's sweep, not this loop."""
    host = _LifecycleHost()
    controller = _LifecycleController(host, errors={'conv-live': InvalidArgument(_EXPIRED_ERROR_TEXT)})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.lifecycle_loop()

    assert controller.created_rollover is True
    assert [m for m in _messages(caplog) if 'deferred stage=lifecycle_rollover' in m] != []


async def test_shutdown_wake_before_the_first_poll_ends_the_loop_quietly(caplog):
    """The wait-owns-the-loop guarantee is unchanged: a woken loop never polls."""
    host = _LifecycleHost()
    host._wait_calls = 0

    async def wake_immediately(seconds: float) -> bool:
        return True

    host.wait = wake_immediately
    controller = _LifecycleController(host, errors={})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.lifecycle_loop()

    assert controller.created_rollover is False
    assert controller.processed == []


async def test_composed_expired_rows_across_stages_in_one_sweep(caplog):
    """timed-out and stale rows can both defer in one sweep; both still run."""
    host = _Host(
        woken_by_shutdown=False,
        processing=[],
        stale_in_progress=[{'id': 'conv-stale-expired'}],
    )
    errors = {
        'conv-timed-out': InvalidArgument(_EXPIRED_ERROR_TEXT),
        'conv-stale-expired': InvalidArgument(_EXPIRED_ERROR_TEXT),
    }
    controller = _RaisingController(host, errors=errors)

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller.process_pending('conv-timed-out')

    assert controller.processed == ['conv-timed-out', 'conv-stale-expired']
    deferred = [m for m in _messages(caplog) if 'deferred' in m]
    assert len(deferred) == 2


async def test_expired_transaction_is_deferred_not_error_logged(caplog):
    host = _TransientHost()
    controller = _RaisingController(host, errors={'conv-live': InvalidArgument(_EXPIRED_ERROR_TEXT)})

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        await controller._finalize_isolated(controller.process_conversation, 'conv-live', stage='lifecycle_rollover')

    messages = [record.getMessage() for record in caplog.records if record.name == 'routers.listen.conversations']
    assert messages == [
        'Listen pending finalization deferred stage=lifecycle_rollover conversation=conv-live '
        'type=InvalidArgument reason=expired_transaction document=none'
    ]
    # The uid-bearing Firestore message never reaches the log.
    assert not [line for line in caplog.text.splitlines() if 'conv-live' in line and 'expired or is no longer' in line]


@pytest.mark.parametrize('stage', ['lifecycle_rollover', 'timed_out', 'processing', 'stale_in_progress'])
async def test_expired_transaction_defers_at_every_stage(caplog, stage):
    host = _CloseHost(stale_in_progress=[{'id': 'conv-a'}] if stage == 'stale_in_progress' else [])
    errors = {'conv-live': InvalidArgument(_EXPIRED_ERROR_TEXT)}
    if stage == 'stale_in_progress':
        errors = {'conv-a': InvalidArgument(_EXPIRED_ERROR_TEXT)}
    controller = _RaisingController(host, errors=errors)

    with caplog.at_level('WARNING', logger='routers.listen.conversations'):
        if stage == 'stale_in_progress':
            await controller.process_pending(None)
        else:
            await controller._finalize_isolated(controller.process_conversation, 'conv-live', stage=stage)

    deferred = [m for m in _messages(caplog) if 'deferred' in m]
    assert deferred, 'expired transaction must be deferred, not ERROR-logged'
    assert not [m for m in _messages(caplog) if 'pending finalization failed' in m]


async def test_permanent_and_unknown_failures_keep_the_error(caplog):
    """Loudness regression guard: only expired transactions are deferred."""
    host = _CloseHost(stale_in_progress=[{'id': 'conv-a'}])
    controller = _RaisingController(
        host,
        errors={
            'conv-live': ValueError('something else'),
            'conv-a': Aborted('Too much contention on these documents. Please try again.'),
        },
    )

    with caplog.at_level('ERROR', logger='routers.listen.conversations'):
        await controller._finalize_isolated(controller.process_conversation, 'conv-live', stage='lifecycle_rollover')
        await controller.process_pending(None)

    failed = [m for m in _messages(caplog) if 'pending finalization failed' in m]
    assert failed == [
        'Listen pending finalization failed stage=lifecycle_rollover conversation=conv-live '
        'type=ValueError reason=other document=none',
        'Listen pending finalization failed stage=stale_in_progress conversation=conv-a '
        'type=Aborted reason=contention document=none',
    ]


def test_size_limit_failure_is_never_transient():
    from utils.conversations.finalization_failure import classify_finalization_failure

    failure = classify_finalization_failure(_size_limit_error('conv-own'), 'conv-own')

    assert failure.conversation_at_size_limit is True
    assert failure.transient is False


@pytest.mark.parametrize(
    'error',
    [
        InvalidArgument(_EXPIRED_ERROR_TEXT),
        Aborted(f'409 {_EXPIRED_ERROR_TEXT}'),
        InvalidArgument(f"Document 'projects/p/d' cannot be written: {_EXPIRED_ERROR_TEXT}"),
    ],
)
def test_expired_transaction_is_transient_across_envelopes(error):
    from utils.conversations.finalization_failure import classify_finalization_failure

    failure = classify_finalization_failure(error, 'conv-a')

    assert failure.reason == 'expired_transaction'
    assert failure.transient is True
    # The boundary must never log this error's message directly: it names the
    # rejected document by its uid-bearing path.
    assert 'uid-1' not in str(failure)


def test_select_stale_in_progress_filters_sorts_and_bounds():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)
    conversations = [
        {'id': 'fresh', 'finished_at': now - timedelta(minutes=5)},
        {'id': 'oldest', 'finished_at': now - timedelta(days=120)},
        {'id': 'old', 'finished_at': now - timedelta(days=2)},
        # No trustworthy idle clock — cannot be proven orphaned.
        {'id': 'no-clock'},
        {'id': 'bad-clock', 'finished_at': 'not-a-datetime'},
    ]

    selected = select_stale_in_progress(conversations, cutoff, limit=10)
    assert [c['id'] for c in selected] == ['oldest', 'old']

    bounded = select_stale_in_progress(conversations, cutoff, limit=1)
    assert [c['id'] for c in bounded] == ['oldest']


class _QueryDocument:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self):
        return self._data


class _StaleRecoveryQuery:
    def __init__(self, documents: list[_QueryDocument]):
        self.documents = documents
        self.ordering = None
        self.limit_value = None

    def where(self, **_kwargs):
        return self

    def order_by(self, field_path, direction):
        self.ordering = (field_path, direction)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def stream(self):
        return iter(self.documents)


class _StaleRecoveryClient:
    def __init__(self, query: _StaleRecoveryQuery):
        self.query = query

    def collection(self, _name):
        return _StaleRecoveryUserRef(self.query)


class _StaleRecoveryUserRef:
    def __init__(self, query: _StaleRecoveryQuery):
        self.query = query

    def document(self, _uid):
        return self

    def collection(self, _name):
        return self.query


def test_stale_recovery_queries_oldest_rows_before_bounding_the_read():
    now = datetime.now(timezone.utc)
    query = _StaleRecoveryQuery(
        [
            _QueryDocument({'id': 'oldest', 'finished_at': now - timedelta(days=2)}),
            _QueryDocument({'id': 'old', 'finished_at': now - timedelta(hours=2)}),
        ]
    )
    client = _StaleRecoveryClient(query)

    selected = conversations_db.get_stale_in_progress_conversations(
        'uid-1',
        older_than_seconds=3600,
        limit=1,
        firestore_client=client,
    )

    assert [conversation['id'] for conversation in selected] == ['oldest']
    assert query.ordering[0] == 'finished_at'
    assert query.limit_value == 1


# ── Custom-STT marker on session resume (#7690) ─────────────────────────────


def _resumable_in_progress(*, uses_custom_stt: bool = False) -> dict:
    """A same-device in-window in_progress row: the resume path now requires the
    shared continuity predicate, which production conversations already satisfy.
    """
    return {
        'id': 'conv-1',
        'status': 'in_progress',
        'discarded': False,
        'uses_custom_stt': uses_custom_stt,
        'source': 'omi',
        'client_device_id': 'dev-1',
        'finished_at': datetime.now(timezone.utc),
    }


class _ResumeHost:
    """Minimal host for create_new_in_progress_conversation's resume branch."""

    def __init__(self, *, existing_conversation: dict | None, use_custom_stt: bool) -> None:
        self.request = SimpleNamespace(uid='uid-1', source='omi')
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='desktop')
        self.language = 'en'
        self.use_custom_stt = use_custom_stt
        self.client_conversation_id = None
        self.recording_session_id = 'session-1'
        self.is_multi_channel = False
        self.conversation_creation_timeout = 120
        self.state = SimpleNamespace(current_conversation_id=None)
        self.recording_session_ids_by_conversation = {}
        self.persistence = SimpleNamespace(call=self._call)
        self.speakers = SimpleNamespace(refresh_for_conversation=AsyncMock())
        self.calls: list[tuple] = []
        self._existing = existing_conversation

    async def _call(self, fn, *_args, **_kwargs):
        self.calls.append((fn.__name__, _args, _kwargs))
        if fn.__name__ == 'open_live_recording_session':
            return {'requires_rollover': False, 'conversation_id': 'conv-1'}
        if fn.__name__ == 'get_conversation':
            return self._existing
        if fn.__name__ == 'set_in_progress_conversation_id':
            return None
        if fn.__name__ == 'update_conversation':
            return None
        return None


class _ResumeController(LiveConversationController):
    def __init__(self, host: _ResumeHost) -> None:
        super().__init__(host)
        self.session_events: list[str] = []

    def send_conversation_session(self, *args, **kwargs) -> None:
        self.session_events.append('sent')


async def test_resume_persists_custom_stt_marker_when_session_uses_custom_stt():
    """A conversation that started under normal STT but resumes under custom STT
    must get the durable uses_custom_stt marker, or its custom-STT provenance is
    lost for metering and the fair-use lane (#7690)."""
    host = _ResumeHost(
        existing_conversation=_resumable_in_progress(uses_custom_stt=False),
        use_custom_stt=True,
    )
    controller = _ResumeController(host)

    await controller.create_new_in_progress_conversation()

    updates = [c for c in host.calls if c[0] == 'update_conversation']
    assert len(updates) == 1, f'expected one update_conversation call, got {host.calls}'
    assert updates[0][1][2] == {'uses_custom_stt': True}, f'wrong update payload: {updates[0]}'


async def test_resume_does_not_rewrite_marker_for_normal_stt_session():
    """A normal-STT resume of a normal-STT conversation must not write anything."""
    host = _ResumeHost(
        existing_conversation=_resumable_in_progress(uses_custom_stt=False),
        use_custom_stt=False,
    )
    controller = _ResumeController(host)

    await controller.create_new_in_progress_conversation()

    updates = [c for c in host.calls if c[0] == 'update_conversation']
    assert updates == [], f'unexpected update_conversation call: {host.calls}'


# ── Skip the guaranteed-miss existence read for server-generated ids ────────
#
# `users/{uid}/conversations/{id}` is the single largest slice of prod
# single-document reads (38.3%), and a fresh server-generated id can never
# already have a document under it. See conversation-existence-read.


class _CreateConversationHost:
    """Host for create_new_in_progress_conversation covering the existence-read
    skip (a server-generated id can't already have a document) and the
    lifecycle-snapshot reuse (open_live_recording_session already read the
    document once while resolving the binding)."""

    def __init__(
        self,
        *,
        client_conversation_id: str | None = None,
        existing_conversation: dict | None = None,
        conversation_snapshot: dict | None = None,
        conversation_snapshot_known: bool = False,
        binding_conversation_id: str | None = None,
    ) -> None:
        self.request = SimpleNamespace(
            uid='uid-1', source='omi', call_id=None, conversation_role=None, geolocation=None
        )
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='desktop')
        self.language = 'en'
        self.use_custom_stt = False
        self.private_cloud_sync_enabled = False
        self.client_conversation_id = client_conversation_id
        self.recording_session_id = 'session-1'
        self.is_multi_channel = False
        self.conversation_creation_timeout = 120
        self.state = SimpleNamespace(current_conversation_id=None)
        self.recording_session_ids_by_conversation = {}
        self.persistence = SimpleNamespace(call=self._call)
        self.speakers = SimpleNamespace(refresh_for_conversation=AsyncMock())
        self.calls: list[tuple] = []
        self._existing = existing_conversation
        self._conversation_snapshot = conversation_snapshot
        self._conversation_snapshot_known = conversation_snapshot_known
        self._binding_conversation_id_override = binding_conversation_id

    async def _call(self, fn, *args, **kwargs):
        self.calls.append((fn.__name__, args, kwargs))
        if fn.__name__ == 'open_live_recording_session':
            proposed_id = args[2]
            conversation_id = self._binding_conversation_id_override or proposed_id
            binding = {'requires_rollover': False, 'conversation_id': conversation_id}
            if self._conversation_snapshot_known:
                binding['conversation_snapshot'] = self._conversation_snapshot
                binding['conversation_snapshot_known'] = True
            return binding
        if fn.__name__ == 'get_conversation':
            return self._existing
        if fn.__name__ == 'resolve_live_continuation':
            return None
        if fn.__name__ in ('set_in_progress_conversation_id', 'update_conversation', 'create_in_progress_conversation'):
            return None
        return None


class _CreateConversationController(LiveConversationController):
    def __init__(self, host: _CreateConversationHost) -> None:
        super().__init__(host)
        self.session_events: list[str] = []

    def send_conversation_session(self, *args, **kwargs) -> None:
        self.session_events.append('sent')


async def test_fresh_server_generated_id_skips_the_existence_read():
    """No client_conversation_id: proposed_id is a freshly minted uuid4 and the
    binding adopts it verbatim, so get_conversation for that id is a guaranteed
    NOT_FOUND and must not be called."""
    host = _CreateConversationHost(client_conversation_id=None)
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation()

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert get_conversation_calls == [], f'unexpected get_conversation call(s): {get_conversation_calls}'
    create_calls = [c for c in host.calls if c[0] == 'create_in_progress_conversation']
    assert len(create_calls) == 1, f'expected the new-conversation path to run, got {host.calls}'
    assert host.state.current_conversation_id is not None
    host.speakers.refresh_for_conversation.assert_awaited_once_with(
        host.state.current_conversation_id, owner_carry_scope=None, owner_carry_donor=None
    )


async def test_rollover_generation_skips_the_existence_read():
    """rollover=True first resolves a durable continuation, then mints a fresh
    server-generated id even when a client_conversation_id is present
    (silence/status rollovers must not reuse or mutate the prior binding). The
    minted id is a guaranteed miss, so the existence read must still be skipped.
    """
    host = _CreateConversationHost(client_conversation_id='client-supplied-id')
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation(rollover=True)

    continuation_calls = [c for c in host.calls if c[0] == 'resolve_live_continuation']
    assert continuation_calls, f'rollover must resolve a durable continuation first, got {host.calls}'
    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert get_conversation_calls == [], f'unexpected get_conversation call(s): {get_conversation_calls}'
    open_calls = [c for c in host.calls if c[0] == 'open_live_recording_session']
    assert len(open_calls) == 1
    proposed_id = open_calls[0][1][2]
    assert proposed_id != 'client-supplied-id', 'rollover must not reuse the client-supplied id as proposed_id'


async def test_resume_with_client_id_naming_existing_conversation_still_reads_it():
    """A client-supplied id can legitimately name an existing conversation
    (resume/idempotency), so the existence read is load-bearing here and must
    not be skipped; the same reconnect action must still be taken."""
    host = _CreateConversationHost(
        client_conversation_id='conv-1',
        existing_conversation=_resumable_in_progress(),
    )
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation()

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert len(get_conversation_calls) == 1, f'expected one get_conversation call, got {host.calls}'
    assert get_conversation_calls[0][1][1] == 'conv-1'
    assert host.state.current_conversation_id == 'conv-1'
    assert controller.session_events == ['sent']
    create_calls = [c for c in host.calls if c[0] == 'create_in_progress_conversation']
    assert create_calls == [], 'a resumed conversation must not be recreated'


async def test_resume_with_client_id_naming_missing_conversation_behaves_as_before():
    """A client-supplied id naming no existing conversation must still be
    looked up (it is not server-generated) and then fall through to the normal
    new-conversation creation path, exactly as before this change."""
    host = _CreateConversationHost(client_conversation_id='conv-missing', existing_conversation=None)
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation()

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert len(get_conversation_calls) == 1, f'expected one get_conversation call, got {host.calls}'
    assert get_conversation_calls[0][1][1] == 'conv-missing'
    create_calls = [c for c in host.calls if c[0] == 'create_in_progress_conversation']
    assert len(create_calls) == 1
    assert create_calls[0][2].get('idempotent') is True
    assert host.state.current_conversation_id == 'conv-missing'
