"""Shared fixtures for the control steady-write skip fleet.

One source of truth for the fleet files: the ledger store, the stream runner,
the kill-switch stream, the document comparators and the snapshot probe grid.
Every fleet test file imports these helpers instead of restating them.
"""

import os
from copy import deepcopy
from contextlib import contextmanager

from config.batch_pipeline import scheduler_control_key
from tests.unit.test_control_steady_write_skip_ledger import (  # noqa: F401
    CONTROL,
    FRESH_QUEUE,
    KEY,
    LedgerStore,
    MemoryStore,
    OWNER,
    QUEUE,
    Scheduler,
    control_row,
    item,
    kill_switch,
    owner_key,
    queue_row,
    seed_array_queue,
    warm_owner,
)
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.control import activation_surface

ENV = 'BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED'


@contextmanager
def _force_legacy():
    """Run a block under the kill switch (the unconditional control write)."""
    before = os.environ.get(ENV)
    os.environ[ENV] = 'false'
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = before


def run_stream(store, segments, owner=OWNER, priority=None, base=0.0):
    scheduler = Scheduler(store)
    for index, segment in enumerate(segments):
        assert scheduler.enqueue(
            item(segment, owner=owner, priority=priority if priority is not None else Priority.DEEP),
            base + index * 70.0,
        )
    return scheduler


def legacy_stream(segments, owner=OWNER, base=0.0):
    with _force_legacy():
        store = LedgerStore()
        run_stream(store, segments, owner=owner, base=base)
    return store


def assert_count(store, expected, key=None):
    assert store.control_writes(key) == expected


def assert_pair(store, killed, segments, owners=(KEY,)):
    for owner in owners:
        left = store.rows.get(('control', scheduler_control_key(owner))) or {}
        right = killed.rows.get(('control', scheduler_control_key(owner))) or {}
        assert left == right
    assert store.rows.get(('queues', QUEUE)) == killed.rows.get(('queues', QUEUE))
    assert (store.rows.get(('owners', KEY)) or {}) == (killed.rows.get(('owners', KEY)) or {})
    for segment in segments:
        assert store.rows.get(('jobs', segment)) == killed.rows.get(('jobs', segment))


def assert_last_ledger_shape(store, shape):
    assert store.ledgers[-1] == list(shape)


def control_doc(store, owner=KEY):
    return store.rows.get(('control', scheduler_control_key(owner))) or {}


def light_control_doc(store):
    return control_doc(store, owner_key('light'))


def queue_doc(store, owner=KEY):
    return store.rows.get(('queues', f'{int(Priority.DEEP)}_{owner}')) or {}


def fresh_queue_doc(store, owner=KEY):
    return store.rows.get(('queues', f'{int(Priority.FRESH)}_{owner}')) or {}


def owner_doc(store, owner=KEY):
    return store.rows.get(('owners', owner)) or {}


def probe(doc, priority, queue):
    return activation_surface(doc, priority, queue)


def cell(doc, priority, queue, member, length, active, service, batch, live):
    got = probe(doc, priority, queue)
    assert got == (
        ('ring', priority, member, length),
        ('active', priority, active),
        ('service', priority, service),
        ('batch_available_at', priority, batch),
        ('live_available_at', priority, live),
    )
    return got


def sample_control(*, rings='empty', priority=2, active=False, service=0.0, batch=0.0, live=0.0):
    """A control document in one of the shapes the append path produces."""
    table = {
        'empty': {'0': [], '1': [], '2': []},
        'member': {'0': [], '1': [], '2': [QUEUE]},
        'three': {'0': [], '1': [], '2': ['x', 'y', QUEUE]},
        'fresh': {'0': [FRESH_QUEUE], '1': [], '2': []},
        'gone': None,
    }[rings]
    doc = {} if table is None else {'rings': table}
    if table is not None:
        for p in (0, 2):
            on = p == priority
            doc['p%d_active' % p] = active if on else False
            doc['p%d_service' % p] = service if on else 0.0
            doc['p%d_batch_available_at' % p] = batch if on else 0.0
            doc['p%d_live_available_at' % p] = live if on else 0.0
    return doc


def warm_store(segments=('base',)):
    store = LedgerStore()
    run_stream(store, segments)
    return store


def pull_grant(store, now, limit=1):
    scheduler = Scheduler(store)
    leases = scheduler.pull(now, limit)
    return leases


def grant_control_count(store):
    return sum(1 for puts in store.ledgers if ('control', CONTROL) in puts)
