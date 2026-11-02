"""Shutdown must preserve cleanup grace when durable settlement is blocked."""

import asyncio
from threading import Event

import pytest

from database.pinecone_mutation_lifecycle import MutationRegistry, drain_on_shutdown


async def test_shutdown_deadline_leaves_unsettled_ticket_visible_until_write_returns():
    entered, release, completed = Event(), Event(), Event()
    registry = MutationRegistry()
    identity = ('synthetic',)
    registry.reserve(identity)

    def blocked_write():
        entered.set()
        assert release.wait(5)
        registry.discard(identity)
        completed.set()

    registry.activate(identity, blocked_write)
    task = asyncio.create_task(drain_on_shutdown(registry.drain, timeout=0.02))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.wait_for(task, timeout=2)
        assert not completed.is_set()
        with pytest.raises(RuntimeError, match='draining'):
            registry.reserve(('new',))
        with pytest.raises(RuntimeError, match='unresolved'):
            registry.start()
    finally:
        release.set()
        assert await asyncio.to_thread(completed.wait, 2)
        await task
    registry.start()
    registry.reserve(('new',))
    registry.discard(('new',))
