"""add_mcp_server must not resolve a user-supplied hostname on the event loop.

`assert_public_http_url()` calls blocking `socket.getaddrinfo()`. Called
directly from this async route, one caller pointing at a hostname with a slow
resolver stalls every other request on the same worker until the resolver
times out. The route has to offload it, like the MCP request paths do.

The offload proof is coordination-based, not wall-clock: the validator signals
when it is running inside the executor and then blocks on a threading.Event.
If it were running inline on the event loop, the loop would be frozen while
blocked and the heartbeat could not tick; the test waits for a heartbeat tick
while the validator is still blocked, then releases it.
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from routers import apps as apps_mod
from utils.http_client import UnsafeWebhookURLError

TICK_SECONDS = 0.001


class _Request:
    def __init__(self, url):
        self.mcp_server_url = url
        self.name = 'Test MCP'
        self.description = 'desc'


def test_slow_dns_validation_does_not_block_the_event_loop():
    entered = asyncio.Event()
    release = threading.Event()
    loop = None

    def _block_then_reject(url):
        # Runs on an executor thread. Prove to the loop we are inside the
        # offloaded call, then hold the worker until the test has observed
        # that the loop kept ticking.
        loop.call_soon_threadsafe(entered.set)
        release.wait(timeout=10)
        raise UnsafeWebhookURLError('private')

    async def drive():
        nonlocal loop
        loop = asyncio.get_running_loop()
        ticks = 0
        stop = False
        ticked = asyncio.Event()

        async def heartbeat():
            nonlocal ticks
            while not stop:
                await asyncio.sleep(TICK_SECONDS)
                ticks += 1
                ticked.set()

        beat = asyncio.create_task(heartbeat())
        try:
            with (
                patch.object(apps_mod, 'assert_public_http_url', _block_then_reject),
                patch.object(apps_mod, 'fetch_brandfetch_logo', MagicMock(side_effect=_never_called)),
            ):
                task = asyncio.create_task(
                    apps_mod.add_mcp_server(data=_Request('https://slow.example.com/mcp'), uid='uid1')
                )
                # Validator must enter the executor; if it ran inline, this wait
                # would time out because the loop would be stuck in getaddrinfo.
                await asyncio.wait_for(entered.wait(), timeout=5)
                # The validator is now blocked in a worker thread. The loop must
                # still be making progress: heartbeat must tick while it waits.
                ticked.clear()
                await asyncio.wait_for(ticked.wait(), timeout=5)
                release.set()
                with pytest.raises(Exception) as exc_info:
                    await task
        finally:
            stop = True
            beat.cancel()
        return ticks, exc_info.value

    ticks, error = asyncio.run(drive())

    assert getattr(error, 'status_code', None) == 400
    # Ticking at all while the validator was blocked proves it ran off-loop;
    # a deterministic coordination test must not depend on how many ticks a
    # loaded runner managed to fit into a sleep window.
    assert ticks >= 1, f'event loop was blocked during DNS validation (ticks={ticks})'


def test_non_public_mcp_server_url_is_rejected_with_400():
    def _reject(url):
        raise UnsafeWebhookURLError('private')

    async def drive():
        with (
            patch.object(apps_mod, 'assert_public_http_url', _reject),
            patch.object(apps_mod, 'fetch_brandfetch_logo', MagicMock(side_effect=_never_called)),
        ):
            with pytest.raises(Exception) as exc_info:
                await apps_mod.add_mcp_server(data=_Request('http://127.0.0.1/mcp'), uid='uid1')
        return exc_info.value

    error = asyncio.run(drive())
    assert getattr(error, 'status_code', None) == 400
    assert 'public' in error.detail.lower()


async def _never_called(*_args, **_kwargs):
    raise AssertionError('the route should not get past URL validation in this test')
