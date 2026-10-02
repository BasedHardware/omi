"""The desktop declares, per meeting, that it runs a pre-notes screen-evidence pass.

Released desktop builds never run that pass, so the finalizer only waits for
evidence when the conversation carries the declaration. It arrives as the listen
query parameter ``screen_evidence=enabled`` and is persisted at conversation
creation as ``external_data.screen_evidence_pass``.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from routers import transcribe
from routers.listen.conversations import LiveConversationController
from utils.conversations import lifecycle as lifecycle_service


def _handler_request(monkeypatch, **params):
    captured = {}

    async def capture(request):
        captured['request'] = request

    async def accept():
        return None

    monkeypatch.setattr(transcribe, '_run_listen_session_with_deletion_fence', capture)
    websocket = MagicMock()
    websocket.accept = accept
    websocket.headers = {}
    asyncio.run(transcribe.listen_handler(websocket, uid='uid', **params))
    return captured['request']


def test_a_meeting_socket_declaring_the_pass_carries_it(monkeypatch):
    request = _handler_request(monkeypatch, conversation_role='meeting', screen_evidence='enabled')
    assert request.screen_evidence_pass is True


@pytest.mark.parametrize(
    'params',
    [
        {'conversation_role': 'meeting'},  # every released desktop build
        {'conversation_role': 'ambient', 'screen_evidence': 'enabled'},  # only meetings wait
        {'conversation_role': 'meeting', 'screen_evidence': 'yes'},
    ],
)
def test_anything_else_does_not(monkeypatch, params):
    assert _handler_request(monkeypatch, **params).screen_evidence_pass is False


class _Stop(Exception):
    pass


def _created_external_data(screen_evidence_pass: bool) -> dict:
    created = {}

    async def call(function, *args, **kwargs):
        if function is lifecycle_service.open_live_recording_session:
            return {'requires_rollover': False, 'conversation_id': args[2]}
        if function is lifecycle_service.create_in_progress_conversation:
            created.update(args[1])
            raise _Stop()
        return None

    controller = LiveConversationController.__new__(LiveConversationController)
    controller.clock = lambda: datetime(2026, 9, 30, tzinfo=timezone.utc)
    controller.host = SimpleNamespace(
        request=SimpleNamespace(
            uid='uid',
            source='desktop',
            conversation_role='meeting',
            call_id=None,
            geolocation=None,
            onboarding_mode=False,
            screen_evidence_pass=screen_evidence_pass,
        ),
        client_conversation_id=None,
        recording_session_id=None,
        recording_session_ids_by_conversation={},
        persistence=SimpleNamespace(call=call),
        client_device_context=SimpleNamespace(client_device_id='macos_a1b2c3d4', platform='macos'),
        language='en',
        private_cloud_sync_enabled=False,
        use_custom_stt=False,
        is_multi_channel=False,
        onboarding_admitted=False,
    )
    with pytest.raises(_Stop):
        asyncio.run(controller.create_new_in_progress_conversation())
    return created['external_data']


def test_creation_persists_the_declaration():
    assert _created_external_data(True)['screen_evidence_pass'] is True


def test_creation_without_it_stays_as_before():
    external_data = _created_external_data(False)
    assert 'screen_evidence_pass' not in external_data
    assert external_data['conversation_role'] == 'meeting'
