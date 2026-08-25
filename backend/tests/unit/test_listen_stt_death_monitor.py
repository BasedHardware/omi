"""Regression (#10028): the listen receiver proactively terminates a session when
the provider STT socket dies, without waiting for another client audio frame.

``_flush_stt_buffer`` only observes provider death while flushing a client audio
buffer, so a clean upstream close with no further audio could hold the mobile
socket "Listening" until the 300s ``ws_receive_timeout``. ``_monitor_stt_death``
polls the death latch independently and drives the idempotent terminal path.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from routers.listen import receiver as receiver_mod
from routers.listen.receiver import ListenReceiver


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _monitor_self(*, dead: bool):
    """Duck-typed receiver exposing only what `_monitor_stt_death` touches."""
    state = SimpleNamespace(active=True, stt_terminal_failure=False)

    async def wait(_seconds):
        # Return True so the shutdown-aware sleep ends the loop after one pass;
        # the assertion then reflects a single poll, not an infinite spin.
        return True

    host = SimpleNamespace(
        state=state,
        request=SimpleNamespace(websocket=object()),
        client_device_context=SimpleNamespace(platform='ios'),
        wait=wait,
    )
    return SimpleNamespace(host=host, stt_socket=SimpleNamespace(is_connection_dead=dead))


@pytest.mark.anyio
async def test_monitor_terminates_when_provider_socket_dead():
    monitor_self = _monitor_self(dead=True)
    with patch.object(receiver_mod, 'terminate_live_stt_session', new=AsyncMock()) as terminate:
        await ListenReceiver._monitor_stt_death(monitor_self, provider='parakeet')
    terminate.assert_awaited_once()
    assert terminate.await_args.kwargs['reason'] == 'connection_lost'


@pytest.mark.anyio
async def test_monitor_does_not_terminate_a_live_socket():
    monitor_self = _monitor_self(dead=False)
    with patch.object(receiver_mod, 'terminate_live_stt_session', new=AsyncMock()) as terminate:
        await ListenReceiver._monitor_stt_death(monitor_self, provider='parakeet')
    terminate.assert_not_awaited()


@pytest.mark.anyio
async def test_monitor_exits_without_terminating_once_already_terminal():
    monitor_self = _monitor_self(dead=True)
    monitor_self.host.state.stt_terminal_failure = True  # another path already terminalized
    with patch.object(receiver_mod, 'terminate_live_stt_session', new=AsyncMock()) as terminate:
        await ListenReceiver._monitor_stt_death(monitor_self, provider='parakeet')
    terminate.assert_not_awaited()
