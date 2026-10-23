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


async def test_failing_prepare_rollover_finalization_still_creates_new_conversation():
    finished_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    existing = {
        'id': 'conv-prepare-stale',
        'status': 'in_progress',
        'source': 'omi',
        'client_device_id': 'device-1',
        'finished_at': finished_at,
        'transcript_segments': [],
        'photos': [],
        'has_content': False,
    }
    host = _Host(conversation=existing, timeout=1)
    host.is_multi_channel = False
    host.client_conversation_id = None
    host.onboarding_admitted = False
    host.request = SimpleNamespace(uid='uid-1', source='omi', onboarding_mode=False)
    host.client_device_context = SimpleNamespace(client_device_id='device-1', platform='ios')
    controller = _RolloverController(host)

    timed_out_id = await controller.prepare()

    assert timed_out_id == 'conv-prepare-stale'
    assert (
        controller.rolled_over is True
    ), 'a failed pre-create cleanup in prepare() must not abort new conversation creation'


async def test_failing_reconnect_client_id_cleanup_still_rolls_over():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    finished_at = now - timedelta(seconds=300)
    existing = {
        'id': 'conv-client-stale',
        'status': 'in_progress',
        'source': 'omi',
        'client_device_id': 'device-1',
        'finished_at': finished_at,
        'transcript_segments': [],
        'photos': [],
        'has_content': False,
        'is_locked': False,
        'discarded': False,
        'deleted': False,
    }

    async def _call(fn, *args, **_kwargs):
        name = fn.__name__
        if name == 'arm':
            assert args[0] == 'uid-1' and isinstance(args[1], str)
            assert _kwargs == {'requires_byok': False}
            return None
        if name == 'open_live_recording_session':
            _uid, _sid, proposed = args
            return {
                'conversation_id': proposed,
                'requires_rollover': False,
                'conversation_snapshot': existing if proposed == 'conv-client-stale' else None,
                'conversation_snapshot_known': proposed == 'conv-client-stale',
                'lifecycle_version': 1,
                'lifecycle_phase': 'in_progress',
                'lifecycle_sequence': 0,
            }
        if name == 'resolve_live_continuation':
            return None
        if name == 'get_meetings_in_time_range':
            return []
        if name == 'create_in_progress_conversation':
            return True
        if name == 'set_in_progress_conversation_id':
            return None
        raise AssertionError(f'unexpected persistence call: {name}')

    host = SimpleNamespace(
        request=SimpleNamespace(
            uid='uid-1',
            source='omi',
            conversation_role='ambient',
            geolocation=None,
            call_id=None,
            onboarding_mode=False,
        ),
        client_device_context=SimpleNamespace(client_device_id='device-1', platform='ios'),
        client_conversation_id='conv-client-stale',
        recording_session_id='conv-client-stale',
        recording_session_ids_by_conversation={},
        is_multi_channel=False,
        use_custom_stt=False,
        private_cloud_sync_enabled=False,
        language='en',
        onboarding_admitted=False,
        conversation_creation_timeout=120,
        state=SimpleNamespace(current_conversation_id=None, active=True),
        persistence=SimpleNamespace(call=_call),
        send_event=lambda _event: None,
        transcripts=SimpleNamespace(flush_speaker_assignments=AsyncMock()),
        speakers=SimpleNamespace(refresh_for_conversation=AsyncMock()),
    )

    class _ClientRolloverController(LiveConversationController):
        def __init__(self, host_obj) -> None:
            super().__init__(host_obj, clock=lambda: now)
            self.process_calls: list[str] = []

        async def process_conversation(self, conversation_id: str) -> bool:
            self.process_calls.append(conversation_id)
            raise _OversizedDocument('document exceeds the maximum allowed size')

    controller = _ClientRolloverController(host)
    await controller.create_new_in_progress_conversation()

    assert controller.process_calls == ['conv-client-stale']
    assert host.state.current_conversation_id is not None
    assert host.state.current_conversation_id != 'conv-client-stale'
