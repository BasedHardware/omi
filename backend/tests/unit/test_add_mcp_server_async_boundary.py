"""add_mcp_server must not resolve a user-supplied hostname on the event loop.

`assert_public_http_url()` calls blocking `socket.getaddrinfo()`. Called
directly from this async route, one caller pointing at a hostname with a slow
resolver stalls every other request on the same worker until the resolver
times out. The route has to offload it, like the MCP request paths do.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from routers import apps as apps_mod
from utils.http_client import UnsafeWebhookURLError

BLOCKING_SECONDS = 0.2
TICK_SECONDS = 0.01


class _Request:
    def __init__(self, url):
        self.mcp_server_url = url
        self.name = 'Test MCP'
        self.description = 'desc'


async def _drive(url, validator):
    """Run add_mcp_server while a heartbeat coroutine tries to make progress."""
    ticks = 0
    stop = False

    async def heartbeat():
        nonlocal ticks
        while not stop:
            await asyncio.sleep(TICK_SECONDS)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    try:
        with (
            patch.object(apps_mod, 'assert_public_http_url', validator),
            patch.object(apps_mod, 'fetch_brandfetch_logo', MagicMock(side_effect=_never_called)),
        ):
            with pytest.raises(Exception) as exc_info:
                await apps_mod.add_mcp_server(data=_Request(url), uid='uid1')
    finally:
        stop = True
        beat.cancel()
    return ticks, exc_info.value


async def _never_called(*_args, **_kwargs):
    raise AssertionError('the route should not get past URL validation in this test')


def test_slow_dns_validation_does_not_block_the_event_loop():
    def _slow_then_reject(url):
        time.sleep(BLOCKING_SECONDS)
        raise UnsafeWebhookURLError('private')

    ticks, error = asyncio.run(_drive('https://slow.example.com/mcp', _slow_then_reject))

    assert getattr(error, 'status_code', None) == 400
    # If validation ran inline on the loop, the heartbeat gets zero ticks.
    assert ticks >= 2, f'event loop was blocked during DNS validation (ticks={ticks})'


def test_non_public_mcp_server_url_is_rejected_with_400():
    def _reject(url):
        raise UnsafeWebhookURLError('private')

    _, error = asyncio.run(_drive('http://127.0.0.1/mcp', _reject))
    assert getattr(error, 'status_code', None) == 400
    assert 'public' in error.detail.lower()
