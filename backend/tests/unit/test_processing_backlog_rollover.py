"""A paid owner's own tap continues across the month when recovery spends no finite allowance.

Unlimited plans: an earlier month's manual choice (including one parked by the October to
November rollover) rolls into the new month with a new token, period and cutoff. Plus keeps
the monthly tap. Nothing here creates a choice for an owner who never made one. Synthetic only.
"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from database import processing_backlog as store
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import funded_processing as funded, processing_backlog as backlog, processing_backlog_worker as worker

UID = 'synthetic-owner'
SUMMARY = ('users', UID, 'processing_backlog', 'current')
NOW = 1_793_500_000.0  # 2026-11-01T...Z, synthetic


def october(**changes):
    return {
        'state': 'processing',
        'period': '2026-10',
        'token': 'october',
        'lease': 'old-worker',
        'lease_until': 0,
        'cutoff': NOW - 86400 * 10,
        'remaining': None,
        'automatic': False,
        'reserved': {},
        'pending_upgrade': {},
        'scope_skipped': True,
        'cursor_audio': {'at': 5, 'id': 'older'},
        'cursor_text': None,
        **changes,
    }


@pytest.fixture
def summary(monkeypatch):
    monkeypatch.setattr(store.time, 'time', lambda: NOW)
    monkeypatch.setattr(store, '_request_memo', lambda: SimpleNamespace(forget_request_reads=lambda uid: None))

    def build(row):
        client = StrictFirestore({SUMMARY: row} if row is not None else {})
        monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
        return client

    return build


def test_a_manual_october_choice_rolls_with_a_new_fence(summary):
    reserved = {'kind': 'audio', 'id': 'in-flight', 'units': 3, 'at': 9}
    client = summary(october(reserved=reserved))
    rolled = store.roll(UID, period='2026-11', cutoff=NOW)
    row = client.rows[SUMMARY]
    assert rolled == row
    assert row['state'] == 'processing' and row['period'] == '2026-11' and row['rolled_from'] == '2026-10'
    assert row['token'] not in ('october', None) and row['cutoff'] == NOW and row['lease_until'] == 0
    assert row['cursor_audio'] is None and row['scope_skipped'] is False and row['remaining'] is None
    # The in-flight attempt keeps its identity; its source's claim and receipts keep the debit idempotent.
    assert row['reserved'] == reserved


@pytest.mark.parametrize(
    'row',
    [
        None,  # no choice: nothing is created
        {},
        october(state='waiting_choice'),
        october(automatic=True),  # a trial grant or legacy upgrade intent was not a tap
        october(period='2026-11'),
        october(period=None),
        october(lease_until=NOW + 60),  # a live worker still holds the old month
    ],
)
def test_only_an_unleased_earlier_manual_choice_rolls(summary, row):
    client = summary(deepcopy(row) if row is not None else None)
    before = deepcopy(client.rows)
    assert store.roll(UID, period='2026-11', cutoff=NOW) is None
    assert client.rows == before


def test_the_old_months_worker_loses_its_fence_after_a_roll(summary):
    client = summary(october())
    store.roll(UID, period='2026-11', cutoff=NOW)
    client.rows[SUMMARY].update(lease='old-worker', lease_until=NOW + 60)
    assert store.checkpoint(UID, 'october', 'old-worker', {'remaining': 0}) is False
    assert client.rows[SUMMARY]['remaining'] is None


@pytest.mark.parametrize(
    'remaining,row,rolls',
    [
        (None, october(), True),
        (100.0, october(), False),  # Plus: recovery spends its 25 h, so it keeps the monthly tap
        (0.0, october(), False),
        (None, october(automatic=True), False),
        (None, october(state='waiting_choice'), False),
        (None, october(period='2026-11'), False),
    ],
)
def test_rolls_only_for_an_unlimited_owners_own_earlier_tap(monkeypatch, remaining, row, rolls):
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    assert backlog.rolls(row, remaining) is rolls


@pytest.mark.parametrize('remaining,state', [(None, 'processing'), (100.0, 'waiting_choice')])
def test_snapshot_shows_a_rolling_choice_as_processing_and_plus_as_waiting(monkeypatch, remaining, state):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    monkeypatch.setattr(funded, 'capacity', lambda allowance: (remaining, None if remaining is None else 1000.0))
    result = backlog.snapshot(
        UID,
        allowance=SimpleNamespace(managed=True),
        audio={'count': 4, 'seconds': 240},
        summary=october(),
        paid=True,
    )
    assert result.state == state


@pytest.fixture
def visit(monkeypatch):
    """One worker visit in November over a parked October choice."""
    job = october()
    calls = []
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    monkeypatch.setattr(funded, 'allowance', lambda uid: SimpleNamespace(managed=True))
    monkeypatch.setattr(worker, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.store, 'read', lambda uid: deepcopy(job))

    def roll(uid, *, period, cutoff):
        calls.append(('roll', period))
        job.update(period=period, token='november', cutoff=cutoff, rolled_from='2026-10')
        return deepcopy(job)

    def claim(uid, token, period):
        calls.append(('claim', token, period))
        return None  # stop after the fence is taken; the run itself is covered elsewhere

    monkeypatch.setattr(worker.store, 'roll', roll)
    monkeypatch.setattr(worker.store, 'claim', claim)

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    return SimpleNamespace(job=job, calls=calls)


async def test_unlimited_october_choice_resumes_in_november_without_a_tap(visit, monkeypatch):
    monkeypatch.setattr(funded, 'capacity', lambda allowance: (None, None))
    await worker.run(UID)
    assert visit.calls == [('roll', '2026-11'), ('claim', 'november', '2026-11')]


@pytest.mark.parametrize('capacity', [(100.0, 1000.0), (0.0, 1000.0)])
async def test_plus_october_choice_stays_parked_for_a_new_tap(visit, monkeypatch, capacity):
    monkeypatch.setattr(funded, 'capacity', lambda allowance: capacity)
    monkeypatch.setattr(worker.store, 'roll', Mock(side_effect=AssertionError('rolled a finite plan')))
    assert await worker.run(UID) is None
    assert visit.calls == [] and visit.job['period'] == '2026-10'


async def test_an_unmanaged_or_unpaid_owner_never_rolls(visit, monkeypatch):
    monkeypatch.setattr(funded, 'capacity', lambda allowance: (None, None))
    monkeypatch.setattr(funded, 'allowance', lambda uid: SimpleNamespace(managed=False))
    assert await worker.run(UID) is None
    monkeypatch.setattr(funded, 'allowance', lambda uid: SimpleNamespace(managed=True))
    monkeypatch.setattr(funded, 'paid_owner', lambda uid: False)
    assert await worker.run(UID) is None
    assert visit.calls == []


async def test_a_rolled_choice_spends_under_the_new_months_consent(visit, monkeypatch):
    monkeypatch.setattr(funded, 'capacity', lambda allowance: (None, None))
    monkeypatch.setattr(worker.store, 'claim', lambda uid, token, period: 'lease')
    monkeypatch.setattr(worker.store, 'checkpoint', lambda *a: True)
    monkeypatch.setattr(worker.store, 'finish', lambda *a: False)
    monkeypatch.setattr(worker, '_selected', AsyncMock(return_value=True))
    hold = SimpleNamespace(id='held', to_dict=lambda: {'listed_at': 9, 'created_at': NOW - 3600, 'state': 'held'})
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [('audio', hold)] if kind == 'audio' else [])
    monkeypatch.setattr(worker.cap_hold, 'remaining_seconds', lambda row: 60)
    grants = []

    async def process(uid, item):
        grants.append(funded._backlog_grant.get())
        return worker.AttemptOutcome.COMPLETE

    monkeypatch.setattr(worker, '_process', process)
    await worker.run(UID)
    # The new cutoff admits a hold queued after October's; consent is November's, not October's.
    assert grants == [(UID, '2026-11')]
