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

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from database.conversations import select_stale_in_progress
from routers.listen.conversations import LiveConversationController


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
