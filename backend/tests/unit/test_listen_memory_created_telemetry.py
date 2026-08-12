from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from routers.listen import conversations as conversations_module
from routers.listen.conversations import LiveConversationController


class _Host:
    def __init__(self, *, platform: str, envelope: dict | None) -> None:
        self.request = SimpleNamespace(uid='uid-1')
        self.client_device_context = SimpleNamespace(platform=platform, app_version='1.2.3')
        self.recording_session_ids_by_conversation = {'conv-1': 'session-1'}
        self.persistence = SimpleNamespace(call=self._call)
        self.envelope = envelope
        self.sent = []

    async def _call(self, fn, *_args, **_kwargs):
        del _args, _kwargs
        if fn.__name__ == 'get_conversation':
            started_at = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
            return {'started_at': started_at, 'finished_at': started_at + timedelta(seconds=91)}
        if fn.__name__ == 'record_recording_session_event':
            return self.envelope
        raise AssertionError(f'unexpected persistence call: {fn.__name__}')

    def send_event(self, event) -> None:
        self.sent.append(event)


def _envelope(*, accepted: bool | None) -> dict:
    return {
        'recording_session_id': 'session-1',
        'conversation_id': 'conv-1',
        'lifecycle_version': 1 if accepted else None,
        'lifecycle_phase': 'completed' if accepted else None,
        'lifecycle_sequence': 2 if accepted else None,
        **({'accepted': accepted} if accepted is not None else {}),
    }


async def test_windows_completion_emits_memory_created_once_from_the_accepted_durable_transition(monkeypatch):
    captured = []
    monkeypatch.setattr(conversations_module, 'emit_posthog_event', lambda *args: captured.append(args))
    monkeypatch.setattr(conversations_module, 'deserialize_conversation', lambda data: data)
    monkeypatch.setattr(conversations_module, 'ConversationEvent', lambda **kwargs: kwargs)
    host = _Host(platform='windows', envelope=_envelope(accepted=True))

    await LiveConversationController(host).emit_recording_lifecycle_event('conv-1', 'completed')

    assert captured == [
        (
            'uid-1',
            'Memory Created',
            {
                'source': 'desktop',
                'platform': 'windows',
                'duration_seconds': 91,
                'app_version': '1.2.3',
            },
        )
    ]
    assert len(host.sent) == 1


async def test_replayed_or_non_windows_completion_does_not_duplicate_windows_telemetry(monkeypatch):
    captured = []
    monkeypatch.setattr(conversations_module, 'emit_posthog_event', lambda *args: captured.append(args))
    monkeypatch.setattr(conversations_module, 'deserialize_conversation', lambda data: data)
    monkeypatch.setattr(conversations_module, 'ConversationEvent', lambda **kwargs: kwargs)

    replayed = _Host(platform='windows', envelope=_envelope(accepted=None))
    await LiveConversationController(replayed).emit_recording_lifecycle_event('conv-1', 'completed')
    macos = _Host(platform='macos', envelope=_envelope(accepted=True))
    await LiveConversationController(macos).emit_recording_lifecycle_event('conv-1', 'completed')

    assert captured == []
