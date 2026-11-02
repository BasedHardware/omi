"""Shutdown must preserve cleanup grace when durable settlement is blocked."""

import asyncio
import signal
from threading import Event

import pytest

from database.pinecone_mutation_lifecycle import MutationRegistry, drain_on_shutdown, install_shutdown_drain


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


async def test_sigterm_settles_before_lifespan_and_chains_server_handler():
    original = signal.getsignal(signal.SIGTERM)
    server_signals = []
    settled = Event()
    registry = MutationRegistry()
    identity = ('synthetic',)
    registry.reserve(identity)

    def settle():
        registry.discard(identity)
        settled.set()

    registry.activate(identity, settle)

    def server_handler(signum, frame):
        server_signals.append(signum)

    signal.signal(signal.SIGTERM, server_handler)
    restore = lambda: None
    try:
        restore = install_shutdown_drain(registry.drain)
        # No lifespan shutdown call occurs: the active request may still run.
        signal.raise_signal(signal.SIGTERM)
        assert await asyncio.to_thread(settled.wait, 2)
        assert server_signals == [signal.SIGTERM]
        with pytest.raises(RuntimeError, match='draining'):
            registry.reserve(('new',))
        restore()
        assert signal.getsignal(signal.SIGTERM) is server_handler
    finally:
        restore()
        signal.signal(signal.SIGTERM, original)


async def test_default_signal_for_standalone_job_is_not_replaced():
    original = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        restore = install_shutdown_drain(lambda: pytest.fail('standalone job drain was installed'))
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
        restore()
    finally:
        signal.signal(signal.SIGTERM, original)
