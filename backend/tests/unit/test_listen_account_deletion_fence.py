import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import WebSocketException

from routers import transcribe
from routers.listen.contracts import ListenRequest


def test_active_listen_session_closes_and_cancels_when_deletion_is_admitted(monkeypatch):
    session_started = asyncio.Event()
    session_cancelled = asyncio.Event()

    class WebSocket:
        def __init__(self):
            self.closes = []

        async def close(self, *, code, reason):
            self.closes.append((code, reason))

    websocket = WebSocket()

    async def run_session(_request):
        session_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            session_cancelled.set()
            raise

    async def immediate_recheck():
        await session_started.wait()

    async def direct_run_blocking(_executor, function, *args):
        return function(*args)

    def deletion_blocked(_uid):
        raise WebSocketException(code=4005, reason='Account deletion in progress')

    monkeypatch.setattr(transcribe, 'run_listen_session', run_session)
    monkeypatch.setattr(transcribe, '_wait_for_account_deletion_recheck', immediate_recheck)
    monkeypatch.setattr(transcribe, 'run_blocking', direct_run_blocking)
    monkeypatch.setattr(transcribe.auth, 'enforce_account_deletion_ws_access', deletion_blocked)
    request = ListenRequest(uid='uid', websocket=websocket)

    asyncio.run(transcribe._run_listen_session_with_deletion_fence(request))

    assert websocket.closes == [(4005, 'Account deletion in progress')]
    assert session_cancelled.is_set()
    assert request.owner_persistence_blocked.is_set()


def test_stream_handler_keeps_legacy_positional_client_device_context(monkeypatch):
    captured = {}

    async def capture_request(request):
        captured['request'] = request

    monkeypatch.setattr(transcribe, '_run_listen_session_with_deletion_fence', capture_request)
    websocket = MagicMock()
    device_context = SimpleNamespace(client_device_id='macos_a1b2c3d4', platform='desktop')

    async def invoke():
        await transcribe._stream_handler(
            websocket,
            'uid',
            'en',
            8000,
            'pcm8',
            1,
            True,
            None,
            120,
            None,
            transcribe.CustomSttMode.disabled,
            False,
            False,
            True,
            None,
            None,
            None,
            device_context,
            conversation_role='meeting',
        )

    asyncio.run(invoke())

    assert captured['request'].client_device_context is device_context
    assert captured['request'].conversation_role == 'meeting'
