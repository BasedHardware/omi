# LIFECYCLE: permanent
"""PL-487/482: retained recording debt has fenced exits and bounded retries.

Exercise the production drainer and requeue on the same simulator, legacy
Firestore and replacement Postgres matrix. Only audio admission and the drainer's
clock are injected; discovery, transactions and privacy checks remain real.
Complete qualification requires OMI_REQUIRE_STORE_BACKENDS=all.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest
from psycopg.errors import InvalidTextRepresentation

from config.batch_pipeline import RECORD_DEAD_LETTER_SECONDS
from config.record_audio import BARRIER_NOT_CLOSED
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_record_dead_letter import requeue_record
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import live

pytestmark = pytest.mark.integration
T0 = 1_800_000_000.0
SEGMENT = 'retained-record'
CAPTURE = 'capture'


class BooleanEnqueueClockUnsupported(AssertionError):
    """The exact replacement-store gap tracked in #24960."""


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    owner = store_backend.seed_user('o')
    store_backend.customer.add_conversation(owner, CAPTURE)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', 'on')
    monkeypatch.setenv('RECORD_SEAL_REPAIR_FRESH_ENABLED', 'true')
    monkeypatch.setenv('RECORD_DRAIN_LEASE_SECONDS', '900')
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '10')
    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    # Never freeze process-wide time: Firestore/gRPC still need real deadlines.
    clock = [T0]
    monkeypatch.setattr(live, 'time', SimpleNamespace(time=lambda: clock[0], monotonic=time.monotonic))
    store_backend.clock = clock

    async def barrier(*_args, **_kwargs):
        raise ValueError(BARRIER_NOT_CLOSED)

    monkeypatch.setattr(live, 'admit_recording', barrier)
    return store_backend


def read(h):
    return h.store.run(lambda tx: tx.get('jobs', SEGMENT))


def write(h, **fields):
    row = {
        'segment_id': SEGMENT,
        'owner_id': h.uid('o'),
        'conversation_id': CAPTURE,
        'state': 'record_pending',
        'available_at': T0 - 1,
        'enqueued_at': T0 - 3 * 86400,
        'merge_pending': False,
        'audio_uri': 'gs://synthetic-retained/record#17',
        'record_snapshot': {
            'record_audio_closed': False,
            'record_upload_sessions': {'synthetic-session': True},
            'recording_ids': ['synthetic-recording'],
        },
        'policy_id': 'pl487-policy',
        'policy_snapshot': {'storage_consent': True, 'finite_allowance': 17},
    }
    h.store.run(lambda tx: tx.put('jobs', SEGMENT, {**row, **fields}))
    return read(h)  # Includes the actual store-assigned privacy generation.


def retry_fields(claimed_at, delay):
    retry_at = claimed_at + delay
    return {'record_intake_claimed_at': claimed_at, 'record_intake_retry_at': retry_at, 'available_at': retry_at}


@pytest.mark.asyncio
async def test_pl487_first_refusal_grants_a_full_window_and_restarts_do_not_renew_it(h):
    before = write(h)
    metrics = Mock()
    await live.drain_recordings(h.store, metrics=metrics)
    first = read(h)
    deadline = T0 + RECORD_DEAD_LETTER_SECONDS
    assert first['record_dead_letter_deadline_at'] == deadline
    assert first['state'] == 'record_pending' and first['available_at'] == T0 + 3600
    assert first == {**before, **retry_fields(T0, 3600), 'record_dead_letter_deadline_at': deadline}
    # The production function has no persistent in-process coordinator. Advance
    # only its clock, then call anew to model a fresh worker reading durable debt.
    h.clock[0] = first['available_at']
    await live.drain_recordings(h.store, metrics=metrics)
    again = read(h)
    assert again['record_dead_letter_deadline_at'] == deadline
    assert again['state'] == 'record_pending'
    metrics.record_dead_letter.inc.assert_not_called()
    assert again == {**first, **retry_fields(h.clock[0], 3600)}


@pytest.mark.asyncio
async def test_pl487_deadline_boundary_requeues_once_without_releasing_custody(h):
    deadline = T0 + 3600
    before = write(h, record_dead_letter_deadline_at=deadline)
    metrics = Mock()
    await live.drain_recordings(h.store, metrics=metrics)
    assert read(h)['state'] == 'record_pending', 'not expired before the exact deadline'
    h.clock[0] = deadline
    await live.drain_recordings(h.store, metrics=metrics)
    dead = read(h)
    assert dead['state'] == 'dead' and dead['dead_letter_reason'] == 'record_barrier_aged'
    assert dead['record_dead_letter_at'] == deadline and dead['merge_pending'] is False
    assert dead == {
        **before,
        **retry_fields(deadline, 3600),
        'state': 'dead',
        'dead_letter_reason': 'record_barrier_aged',
        'record_dead_letter_at': deadline,
        'merge_pending': False,
    }
    metrics.record_dead_letter.inc.assert_called_once_with()
    assert SEGMENT not in h.store.due('record_pending', deadline + 86400, 10)
    # Requeue remains usable when expiry is disabled, and cannot be replayed.
    assert requeue_record(h.store, SEGMENT, deadline + 1)
    queued = read(h)
    assert queued['state'] == 'record_pending' and queued['available_at'] == deadline + 1
    assert queued == {
        **dead,
        'state': 'record_pending',
        'available_at': deadline + 1,
        'dead_letter_reason': None,
        'record_dead_letter_at': None,
        'record_dead_letter_deadline_at': None,
    }
    assert not requeue_record(h.store, SEGMENT, deadline + 2)
    assert read(h) == queued


@pytest.mark.asyncio
@pytest.mark.parametrize('deadline', [True, False, 'yesterday', {}, []])
async def test_pl487_malformed_deadlines_cannot_authorize_expiry(h, deadline):
    before = write(h, record_dead_letter_deadline_at=deadline)
    metrics = Mock()
    await live.drain_recordings(h.store, metrics=metrics)
    after = read(h)
    assert after == {**before, **retry_fields(T0, 3600)}
    metrics.record_dead_letter.inc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('deadline', [None, T0 - 1])
async def test_pl487_kill_switch_stops_stamps_and_expiry_but_not_requeue(h, monkeypatch, deadline):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    before = write(h, **({} if deadline is None else {'record_dead_letter_deadline_at': deadline}))
    await live.drain_recordings(h.store)
    assert read(h) == {**before, 'record_intake_claimed_at': T0, 'available_at': T0 + 3600}
    write(h, state='dead', dead_letter_reason='record_barrier_aged', record_dead_letter_deadline_at=T0 - 1)
    assert requeue_record(h.store, SEGMENT, T0 + 1)
    assert read(h)['state'] == 'record_pending'


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [ValueError('another refusal'), RuntimeError(BARRIER_NOT_CLOSED)])
async def test_pl487_other_failures_keep_their_own_retry_and_never_expire(h, monkeypatch, error):
    before = write(h, record_dead_letter_deadline_at=T0 - 1)

    async def refuse(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(live, 'admit_recording', refuse)
    await live.drain_recordings(h.store)
    assert read(h) == {**before, **retry_fields(T0, 60)}


@pytest.mark.asyncio
@pytest.mark.parametrize('race', ['successor-lease', 'admitted', 'privacy'])
async def test_pl487_stale_worker_cannot_expire_a_new_owner_or_cross_privacy(h, monkeypatch, race):
    before = write(h, record_dead_letter_deadline_at=T0 - 1)
    observed = []

    async def race_then_refuse(store, _row):
        if race == 'privacy':
            h.customer.block_privacy(h.uid('o'))
        else:

            def successor(tx):
                row = tx.get('jobs', SEGMENT)
                row.update(
                    available_at=T0 + 3600 if race == 'successor-lease' else T0,
                    state='record_pending' if race == 'successor-lease' else 'ready',
                )
                tx.put('jobs', SEGMENT, row)

            store.run(successor)
        observed.append(read(h))
        raise ValueError(BARRIER_NOT_CLOSED)

    monkeypatch.setattr(live, 'admit_recording', race_then_refuse)
    metrics = Mock()
    if race == 'privacy':
        with pytest.raises(BatchPrivacyBlocked):
            await live.drain_recordings(h.store, metrics=metrics)
    else:
        await live.drain_recordings(h.store, metrics=metrics)
    after = read(h)
    assert (
        after == observed[0]
    ), 'a stale refusal cannot overwrite the newer selection or cross the commit privacy fence'
    expected_available = {'successor-lease': T0 + 3600, 'admitted': T0, 'privacy': T0 + 900}
    assert after == {
        **before,
        'state': 'ready' if race == 'admitted' else 'record_pending',
        'available_at': expected_available[race],
        'record_intake_claimed_at': T0,
    }
    metrics.record_dead_letter.inc.assert_not_called()


@pytest.mark.parametrize('fence', ['account', 'conversation', 'generation'])
def test_pl487_requeue_rechecks_real_privacy_without_mutating_retained_debt(h, fence):
    before = write(h, state='dead', dead_letter_reason='record_barrier_aged', record_dead_letter_deadline_at=T0 - 1)
    if fence == 'account':
        h.customer.delete_account(h.uid('o'))
    elif fence == 'conversation':
        h.customer.delete_conversation(h.uid('o'), CAPTURE)
    else:
        h.customer.block_privacy(h.uid('o'))
    with pytest.raises(BatchPrivacyBlocked):
        requeue_record(h.store, SEGMENT, T0)
    assert read(h) == before


@pytest.mark.parametrize(
    'state,reason', [('dead', 'held_expired'), ('cancelled', 'record_barrier_aged'), ('dead', None)]
)
def test_pl487_requeue_is_a_reason_and_state_cas_and_cannot_recreate_erased_work(h, state, reason):
    before = write(h, state=state, dead_letter_reason=reason)
    assert not requeue_record(h.store, SEGMENT, T0)
    assert read(h) == before
    assert not requeue_record(h.store, 'erased-record', T0)
    assert h.store.run(lambda tx: tx.get('jobs', 'erased-record')) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('age,delay', [(599, 60), (600, 900), (86399, 900), (86400, 3600), (None, 60), (True, 60)])
async def test_pl482_barrier_retry_uses_durable_age_and_returns_at_the_bounded_deadline(
    h, monkeypatch, age, delay, request
):
    unsupported = h.name == 'postgres' and age is True
    if unsupported:
        request.node.add_marker(
            pytest.mark.xfail(
                strict=True,
                raises=BooleanEnqueueClockUnsupported,
                reason='https://github.com/BasedHardware/omi/issues/24960: Postgres rejects legacy boolean enqueue age',
            )
        )
    try:
        before = write(h, enqueued_at=None if age is None else True if age is True else T0 - age)
    except InvalidTextRepresentation as error:
        # Accept only this reproduced schema gap, never a different SQL/setup
        # failure. Once repaired, the full invariant must pass and strict XPASS
        # forces removal of the annotation.
        if not unsupported or str(error) != 'invalid input syntax for type double precision: "true"':
            raise
        raise BooleanEnqueueClockUnsupported(str(error)) from error
    await live.drain_recordings(h.store)
    waiting = read(h)
    assert waiting['available_at'] == T0 + delay
    assert waiting['record_dead_letter_deadline_at'] == T0 + RECORD_DEAD_LETTER_SECONDS
    assert waiting == {
        **before,
        **retry_fields(T0, delay),
        'record_dead_letter_deadline_at': T0 + RECORD_DEAD_LETTER_SECONDS,
    }
    assert SEGMENT not in h.store.due('record_pending', T0 + delay - 0.01, 10)
    assert SEGMENT in h.store.due('record_pending', T0 + delay, 10)
    admissions = []

    async def now_finalized(store, pending):
        admissions.append(pending['segment_id'])

        def admit(tx):
            row = tx.get('jobs', SEGMENT)
            tx.put('jobs', SEGMENT, {**row, 'state': 'ready', 'available_at': h.clock[0]})

        store.run(admit)

    monkeypatch.setattr(live, 'admit_recording', now_finalized)
    h.clock[0] = T0 + delay
    await live.drain_recordings(h.store)
    after = read(h)
    assert admissions == [SEGMENT] and after['state'] == 'ready'
    expected = {**waiting, 'record_intake_claimed_at': T0 + delay, 'available_at': T0 + delay, 'state': 'ready'}
    del expected['record_intake_retry_at']  # A fresh claim invalidates the previous retry marker.
    assert after == expected


@pytest.mark.asyncio
async def test_pl482_backoff_kill_switch_restores_flat_retry_without_erasing_debt(h, monkeypatch):
    monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', 'off')
    before = write(h)
    await live.drain_recordings(h.store)
    after = read(h)
    assert after['available_at'] == T0 + 60
    assert after['record_dead_letter_deadline_at'] == T0 + RECORD_DEAD_LETTER_SECONDS
    assert after == {
        **before,
        **retry_fields(T0, 60),
        'record_dead_letter_deadline_at': T0 + RECORD_DEAD_LETTER_SECONDS,
    }
