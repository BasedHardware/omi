"""A failing lifecycle-rollover finalization must not crash the live session's lifetime task.

`process_pending`'s sweep isolates each finalization (#19905), but the `process_and_create_new`
branch that keeps a live recording alive still called `process_conversation` directly. A
conversation at Firestore's 1 MiB write limit fails every finalization write, so that branch
raised out of `lifecycle_loop`, which runs as a lifetime task — `supervise_tasks` turns the
escape into a socket teardown, ending the recording mid-session instead of rolling over.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from routers.listen.conversations import LiveConversationController


class _OversizedDocument(Exception):
    pass


class _Host:
    """Minimal listen host for the lifecycle loop."""

    def __init__(self, *, conversation: dict, timeout: int) -> None:
        self.request = SimpleNamespace(uid='uid-1')
        self.state = SimpleNamespace(current_conversation_id=conversation['id'], active=True)
        self.conversation_creation_timeout = timeout
        self._conversation = conversation
        self.transcripts = SimpleNamespace(flush_speaker_assignments=AsyncMock())
        self.persistence = SimpleNamespace(call=self._call)
        self.waits: list[float] = []

    async def _call(self, _fn, *_args, **_kwargs):
        return self._conversation

    async def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        # One loop iteration, then the session ends.
        self.state.active = False
        return False


class _RolloverController(LiveConversationController):
    """Finalization that fails like an over-limit document, plus a rollover spy."""

    def __init__(self, host: _Host) -> None:
        super().__init__(host)
        self.rolled_over = False

    async def process_conversation(self, conversation_id: str) -> bool:
        raise _OversizedDocument('document exceeds the maximum allowed size')

    async def create_new_in_progress_conversation(self, *, rollover: bool = False) -> None:
        self.rolled_over = True


async def test_failing_rollover_finalization_does_not_crash_the_lifecycle_loop():
    finished_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    host = _Host(
        conversation={'id': 'conv-oversized', 'status': 'in_progress', 'finished_at': finished_at},
        timeout=1,
    )
    controller = _RolloverController(host)

    # Before the fix, _OversizedDocument escaped lifecycle_loop and killed the lifetime task.
    await controller.lifecycle_loop()

    assert host.waits == [5]
    assert controller.rolled_over is True, 'a failed finalization must not skip the rollover'
