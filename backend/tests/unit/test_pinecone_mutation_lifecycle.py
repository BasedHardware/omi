"""Shutdown must preserve cleanup grace when durable settlement is blocked."""

import asyncio
import signal
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest

from database.pinecone_mutation_lifecycle import MutationRegistry, drain_on_shutdown, install_shutdown_drain
from database import pinecone_mutation_lifecycle as lifecycle


def test_repeated_drain_does_not_restart_shutdown_grace(monkeypatch):
    clock = [0.0]
    waits = []
    registry = MutationRegistry()
    registry.reserve(('synthetic',))

    def fail_write():
        raise RuntimeError('synthetic Firestore unavailable')

    def wait(timeout):
        waits.append(timeout)
        clock[0] += timeout

    monkeypatch.setattr(lifecycle, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(registry._lock, 'wait', wait)
    registry.activate(('synthetic',), fail_write)
    assert registry.drain() == 0
    assert registry.drain() == 0
    assert waits == [3.0]
    registry.discard(('synthetic',))
    registry.start()


async def test_shutdown_deadline_leaves_unsettled_ticket_visible_until_write_returns():
    entered, release, completed = Event(), Event(), Event()
    registry = MutationRegistry(grace_seconds=0)
    identity = ('synthetic',)
    registry.reserve(identity)

    def blocked_write():
        entered.set()
        assert release.wait(5)
        registry.discard(identity)
        completed.set()

    registry.activate(identity, blocked_write)
    task = asyncio.create_task(drain_on_shutdown(registry.drain, timeout=0.5))
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
    registry = MutationRegistry(grace_seconds=0)
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


async def test_default_executor_saturation_cannot_starve_shutdown_settlement():
    loop = asyncio.get_running_loop()
    release, occupied, settled = Event(), Event(), Event()
    default_pool = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(default_pool)

    def occupy_default():
        occupied.set()
        assert release.wait(5)

    blocker = loop.run_in_executor(None, occupy_default)
    try:
        # Yield until the single default worker is occupied; no other default
        # worker can be borrowed to wait on the event itself.
        async with asyncio.timeout(2):
            while not occupied.is_set():
                await asyncio.sleep(0.001)
        await drain_on_shutdown(settled.set, timeout=1)
        assert settled.is_set()
    finally:
        release.set()
        await blocker
        default_pool.shutdown(wait=True)


async def test_queued_retry_survives_shutdown_wait_timeout():
    from utils.executors import get_pinecone_shutdown_executor

    release, occupied, settled = Event(), Event(), Event()
    loop = asyncio.get_running_loop()

    def occupy_drain_worker():
        occupied.set()
        assert release.wait(5)

    blocker = loop.run_in_executor(get_pinecone_shutdown_executor(), occupy_drain_worker)
    try:
        assert await asyncio.to_thread(occupied.wait, 2)
        await drain_on_shutdown(settled.set, timeout=0.5)
        assert not settled.is_set()
        release.set()
        await blocker
        assert await asyncio.to_thread(settled.wait, 2)
    finally:
        release.set()
        await blocker
