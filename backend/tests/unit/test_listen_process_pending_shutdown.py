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

from types import SimpleNamespace

from routers.listen.conversations import LiveConversationController


class _Host:
    """Minimal listen host. wait() returns True to mean 'woken early by shutdown'."""

    def __init__(self, *, woken_by_shutdown: bool, processing: list[dict[str, str]]) -> None:
        self.request = SimpleNamespace(uid='uid-1')
        self._woken_by_shutdown = woken_by_shutdown
        self._processing = processing
        self.waited: list[float] = []
        self.persistence = SimpleNamespace(call=self._call)

    async def wait(self, seconds: float) -> bool:
        self.waited.append(seconds)
        return self._woken_by_shutdown

    async def _call(self, _fn, *_args):
        return self._processing


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
