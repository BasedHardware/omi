"""Cap-hold units handed to batch are charged against the funded budget without a stale window (lane 6).

Subscription ruling 10-19 on #22467: (A) consecutive backlog candidates must not see stale capacity while
batch has not yet projected; (B) usage is attributed to the funded period of the owner's choice across a
month rollover; (C) cap-hold admissions are never ``native_record`` (which would skip the usage write).
Synthetic owners only; Firestore is the in-memory StrictFirestore.
"""

import ast
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from database import llm_usage
from database import processing_backlog as backlog_store
from database.batch_pipeline_projection import ProjectionStore, usage_stamp
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import processing_backlog_worker as worker
from utils.batch_pipeline import cap_hold_admission as adapter
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.sync import cap_hold, cap_hold_recovery
from utils.sync import cap_hold_reservations as reservations
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

UID = 'synthetic-owner'
PERIOD = '2026-10'
RATE = 3600.0  # recording units per hour in these tests: 1 unit per second


@pytest.fixture
def reservation_db(monkeypatch):
    db = StrictFirestore()
    monkeypatch.setattr(reservations, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(reservations, 'external_write_fence', lambda uid, firestore_client=None: nullcontext())
    return db


def entries(db):
    return (db.rows.get(('users', UID, reservations.COLLECTION, reservations.DOCUMENT)) or {}).get('entries', {})


# --- A: the worker never over-admits while batch has not projected -------------------------------------


@pytest.fixture
def harness(monkeypatch, reservation_db):
    """A backlog job with remaining=None, a 60-unit allowance that projection has not yet debited, and
    three 40-unit held candidates. Processing a candidate is the batch hand-off: it reserves the units."""
    job = {
        'state': 'processing',
        'period': PERIOD,
        'token': 'choice',
        'lease': 'lease',
        'lease_until': 1,
        'cutoff': 10_000,
        'remaining': None,
        'reserved': {},
    }
    processed = []
    statuses = {}
    monkeypatch.setattr(worker.funded_processing, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(worker.funded_processing, 'period_id', lambda: PERIOD)
    monkeypatch.setattr(worker.funded_processing, 'allowance', lambda uid: SimpleNamespace(managed=True))
    # Projection has not run: the budget read never moves during the page.
    monkeypatch.setattr(worker.funded_processing, 'capacity', lambda current: (60.0, 60.0))
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.cap_hold, 'remaining_seconds', lambda row: row.get('seconds', 0))
    monkeypatch.setattr(worker, 'recording_units_per_hour', lambda kind: RATE)
    monkeypatch.setattr(worker.store, 'read', lambda uid: deepcopy(job))

    async def in_scope(uid, item):
        return True  # main #22494 owner/lane scope is covered by its own tests; every hold here is selected

    monkeypatch.setattr(worker, '_selected', in_scope)

    def claim(uid, token, period):
        if job['lease_until'] > time.time():
            return None
        job['lease_until'] = time.time() + 1800
        return 'lease'

    def checkpoint(uid, token, lease, updates):
        if job['lease_until'] <= time.time():
            return False
        job.update(deepcopy(updates))
        return True

    def finish(uid, token, lease, period):
        job.update(state='waiting_choice', lease_until=0)
        return False

    async def run_blocking(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    async def process(uid, item):
        # The batch branch of recover_selected: admit, then reserve the candidate's units.
        processed.append(item['id'])
        reservations.reserve(uid, item['id'], units=item['units'], period=PERIOD, batch_job_id='bp_' + item['id'])
        return worker.AttemptOutcome.COMPLETE

    rows = [
        SimpleNamespace(
            id=f'hold-{i}',
            to_dict=lambda i=i: {'state': 'held', 'seconds': 40, 'listed_at': 100 + i, 'created_at': 1},
        )
        for i in range(3)
    ]
    monkeypatch.setattr(
        worker,
        '_page',
        lambda uid, kind, cursor: [(kind, row) for row in rows] if kind == 'audio' and not cursor else [],
    )
    monkeypatch.setattr(worker.store, 'claim', claim)
    monkeypatch.setattr(worker.store, 'checkpoint', checkpoint)
    monkeypatch.setattr(worker.store, 'finish', finish)
    monkeypatch.setattr(worker, 'run_blocking', run_blocking)
    monkeypatch.setattr(worker, '_process', process)
    monkeypatch.setattr(reservations, 'batch_status', lambda uid, job_id: statuses.get(job_id, 'pending'))
    return SimpleNamespace(job=job, processed=processed, statuses=statuses)


@pytest.mark.asyncio
async def test_stale_capacity_admits_one_of_three_40_unit_holds_against_60(harness):
    await worker.run(UID, continuation=True)
    assert harness.processed == ['hold-2']  # newest first; 60 - 40 = 20 < 40 for the other two


@pytest.mark.asyncio
async def test_without_reservations_the_same_page_overshoots(harness, monkeypatch):
    # Documents the defect the reservation closes: a whole page past a 60-unit allowance.
    monkeypatch.setattr(reservations, 'open_units', lambda *a, **k: 0.0)
    await worker.run(UID, continuation=True)
    assert len(harness.processed) == 3


@pytest.mark.asyncio
async def test_a_second_run_sees_the_first_runs_reservation_until_projection(harness, reservation_db):
    await worker.run(UID, continuation=True)
    harness.job.update(state='processing', lease_until=0, cursor_audio=None, cursor_text=None)
    await worker.run(UID, continuation=True)
    assert harness.processed == ['hold-2']  # still reserved: nothing more fits
    harness.statuses['bp_hold-2'] = 'projected'  # projection committed the real debit
    harness.job.update(state='processing', lease_until=0, cursor_audio=None, cursor_text=None)
    await worker.run(UID, continuation=True)
    assert entries(reservation_db) == {'hold-1': entries(reservation_db)['hold-1']}  # hold-2 settled, hold-1 new
    assert harness.processed == ['hold-2', 'hold-2', 'hold-1']


@pytest.mark.asyncio
async def test_a_projection_between_the_allowance_read_and_settling_is_still_charged(harness, monkeypatch):
    # M1 review L06-1: an earlier run's 40-unit hold projects (usage +40, reservation released) after the
    # worker's first allowance read and before open_units settles it. Only an allowance read after settling
    # sees that spend; without it the next 40-unit hold is admitted against 60 with 40 already spent.
    spend = {'units': 0.0}
    monkeypatch.setattr(
        worker.funded_processing, 'allowance', lambda uid: SimpleNamespace(managed=True, spent=spend['units'])
    )
    monkeypatch.setattr(worker.funded_processing, 'capacity', lambda current: (60.0 - current.spent, 60.0))
    reservations.reserve(UID, 'earlier-hold', units=40, period=PERIOD, batch_job_id='bp_earlier')

    def status(uid, job_id):
        if job_id == 'bp_earlier' and not spend['units']:
            spend['units'] = 40.0  # the projection transaction commits usage and its completion together
        return 'projected' if job_id == 'bp_earlier' else 'pending'

    monkeypatch.setattr(reservations, 'batch_status', status)
    await worker.run(UID, continuation=True)
    assert harness.processed == []  # 60 - 40 spent = 20 < 40 for every candidate


def test_real_job_lease_serializes_two_workers_for_one_owner(monkeypatch):
    db = StrictFirestore(
        {('users', UID, backlog_store.SUMMARY, 'current'): {'state': 'processing', 'token': 't', 'period': PERIOD}}
    )
    monkeypatch.setattr(backlog_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(backlog_store, 'external_write_fence', lambda uid, firestore_client=None: nullcontext())
    monkeypatch.setattr(backlog_store, '_request_memo', lambda: SimpleNamespace(forget_request_reads=lambda uid: None))
    first = backlog_store.claim(UID, 't', PERIOD)
    second = backlog_store.claim(UID, 't', PERIOD)
    assert first is not None and second is None


# --- reservation lifecycle ---------------------------------------------------------------------------


def test_reserve_is_idempotent_per_hold_and_keeps_its_ttl_clock(reservation_db):
    reservations.reserve(UID, 'hold-1', units=40, period=PERIOD, batch_job_id='bp_1', now=100)
    reservations.reserve(UID, 'hold-1', units=99, period=PERIOD, batch_job_id='bp_1', now=500)
    assert entries(reservation_db) == {
        'hold-1': {'units': 40.0, 'period': PERIOD, 'batch_job_id': 'bp_1', 'reserved_at': 100}
    }
    with pytest.raises(ValueError):
        reservations.reserve(UID, 'hold-2', units=float('nan'), period=PERIOD, batch_job_id='bp_2')


@pytest.mark.parametrize('outcome', ['projected', 'failed', 'abandoned'])
def test_known_batch_outcomes_release_the_reservation(reservation_db, outcome):
    reservations.reserve(UID, 'hold-1', units=40, period=PERIOD, batch_job_id='bp_1', now=100)
    assert reservations.open_units(UID, PERIOD, status_reader=lambda uid, job: outcome, now=200) == 0
    assert entries(reservation_db) == {}


def test_slow_pending_reservations_keep_counting_and_alert_once(reservation_db, caplog):
    # Pending past the alert threshold is slow, not lost (lost jobs read as 'abandoned'): releasing it
    # would let the worker over-admit while batch still owes the debit.
    reservations.reserve(UID, 'hold-1', units=40, period=PERIOD, batch_job_id='bp_1', now=100)
    pending = lambda uid, job: 'pending'  # noqa: E731
    stale = reservations.CAP_HOLD_RESERVATIONS_RELEASED.labels(outcome='stale')
    before = stale._value.get()
    assert reservations.open_units(UID, PERIOD, status_reader=pending, now=100 + reservations.STALE_SECONDS - 1) == 40
    assert stale._value.get() == before and 'outcome=stale' not in caplog.text
    for later in (0, 3600, 30 * 86400):
        now = 100 + reservations.STALE_SECONDS + later
        assert reservations.open_units(UID, PERIOD, status_reader=pending, now=now) == 40
    assert stale._value.get() == before + 1  # marked and alerted once, never released
    assert caplog.text.count('outcome=stale') == 1
    assert entries(reservation_db)['hold-1']['stale_at'] == 100 + reservations.STALE_SECONDS
    assert reservations.open_units(UID, PERIOD, status_reader=lambda uid, job: 'projected', now=10**9) == 0
    assert entries(reservation_db) == {}


def test_other_period_entries_are_pruned_after_a_week(reservation_db):
    reservations.reserve(UID, 'old', units=40, period='2026-09', batch_job_id='bp_old', now=100)
    pending = lambda uid, job: 'pending'  # noqa: E731
    assert reservations.open_units(UID, PERIOD, status_reader=pending, now=100 + reservations.PRUNE_SECONDS - 1) == 0
    assert 'old' in entries(reservation_db)
    assert reservations.open_units(UID, PERIOD, status_reader=pending, now=100 + reservations.PRUNE_SECONDS) == 0
    assert entries(reservation_db) == {}


def test_previous_period_reservations_never_shrink_the_new_month(reservation_db):
    reservations.reserve(UID, 'old', units=40, period='2026-09', batch_job_id='bp_old', now=100)
    reservations.reserve(UID, 'new', units=10, period=PERIOD, batch_job_id='bp_new', now=100)
    pending = lambda uid, job: 'pending'  # noqa: E731
    assert reservations.open_units(UID, PERIOD, status_reader=pending, now=200) == 10
    assert set(entries(reservation_db)) == {'old', 'new'}  # kept until its own batch outcome settles it


# --- A-1: the recover_selected hand-off writes the reservation --------------------------------------


@pytest.mark.asyncio
async def test_batch_hand_off_reserves_the_candidates_units_before_it_is_durable(monkeypatch, reservation_db):
    events = []
    row = {'state': 'held', 'lease_token': 'lease', 'seconds': 40}
    monkeypatch.setattr(cap_hold, 'claim', lambda uid, ref, now: dict(row))
    monkeypatch.setattr(cap_hold, 'release', lambda uid, ref, token: events.append('release'))
    monkeypatch.setattr(cap_hold_recovery, 'recording_units_per_hour', lambda kind: RATE)
    monkeypatch.setattr(cap_hold_recovery.funded_processing, 'period_id', lambda: PERIOD)
    monkeypatch.setattr(cap_hold_recovery, '_new_dispatch_allowed', lambda uid, lane: True)

    async def selected_lane(uid, current):
        return 'sync'  # main #22494: recovery follows the hold's original lane (missing legacy origin = sync)

    monkeypatch.setattr(cap_hold_recovery, '_selected_lane', selected_lane)
    monkeypatch.setattr(cap_hold_recovery, '_erase', lambda *a: events.append('erase'))
    monkeypatch.setattr(adapter, 'enabled_for', lambda row, mode=None: True)

    async def admit(uid, snapshot, current):
        return adapter.HeldAdmission('admitted', 'bp_job')

    async def save(uid, snapshot, current, updates):
        events.append(('save', dict(entries(reservation_db))))
        return True

    monkeypatch.setattr(adapter, 'admit_held', admit)
    monkeypatch.setattr(cap_hold_recovery, '_save', save)
    snapshot = SimpleNamespace(id='hold-1', reference=object(), to_dict=lambda: dict(row))
    assert await cap_hold_recovery.recover_selected(UID, snapshot) is True
    reserved = {'hold-1': {'units': 40.0, 'period': PERIOD, 'batch_job_id': 'bp_job'}}
    saved = events[0][1]
    assert {k: {f: v for f, v in e.items() if f != 'reserved_at'} for k, e in saved.items()} == reserved
    assert events[1:] == ['erase', 'release']


# --- B: period attribution across a rollover --------------------------------------------------------


@pytest.mark.parametrize(
    'now,period,expected',
    [
        (
            datetime(2026, 11, 1, 0, 5, tzinfo=timezone.utc),
            '2026-10',
            datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc),
        ),
        (datetime(2027, 1, 1, tzinfo=timezone.utc), '2026-12', datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)),
        (datetime(2026, 10, 20, 3, tzinfo=timezone.utc), '2026-10', datetime(2026, 10, 20, 3, tzinfo=timezone.utc)),
        (
            datetime(2026, 10, 5, tzinfo=timezone.utc),
            '2026-11',
            datetime(2026, 10, 5, tzinfo=timezone.utc),
        ),  # never forward
        (datetime(2026, 11, 1, tzinfo=timezone.utc), None, datetime(2026, 11, 1, tzinfo=timezone.utc)),
        (datetime(2026, 11, 1, tzinfo=timezone.utc), '2026-13', datetime(2026, 11, 1, tzinfo=timezone.utc)),
        (datetime(2026, 11, 1, tzinfo=timezone.utc), 'garbage', datetime(2026, 11, 1, tzinfo=timezone.utc)),
    ],
)
def test_usage_stamp_backdates_only_across_a_rollover(now, period, expected):
    assert usage_stamp(now, period) == expected


def projection(usage_period):
    binding = ProjectionBinding(UID, 'bp_job', 'content', ('seg',))
    rows = {
        ('batch_pipeline_dev_results', 'seg'): {'projection': {'state': 'ready', 'speech_seconds': 30}},
        ('batch_pipeline_dev_jobs', 'seg'): {'priority': 2},
        ('batch_pipeline_dev_intakes', 'bp_job'): {
            'owner_id': UID,
            **({'usage_period': usage_period} if usage_period else {}),
        },
        ('users', UID, 'sync_content_ledger', 'content'): {'status': 'processing'},
    }
    return ProjectionStore(SimpleNamespace(client=StrictFirestore(rows), namespace='batch_pipeline_dev')), binding


@pytest.mark.parametrize('usage_period,hour', [('2026-10', '2026-10-31-23'), (None, '2026-11-01-00')])
def test_projection_charges_the_admission_period_after_a_rollover(monkeypatch, usage_period, hour):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda uid, firestore_client=None: 'plan')
    store, binding = projection(usage_period)
    now = datetime(2026, 11, 1, 0, 5, tzinfo=timezone.utc).timestamp()
    accounting = store.prepare_accounting(binding, now)
    assert accounting['hour'] == hour
    updates = accounting['updates']
    assert updates['id'] == hour and (updates['year'], updates['month']) == tuple(map(int, hour.split('-')[:2]))


# --- C: cap-hold admissions are never native_record -------------------------------------------------


def test_upload_admission_never_marks_a_binding_native_record():
    """accept_upload (the only path admit_held uses) builds its ProjectionBinding without native_record;
    only the live record lane sets it, and that lane is not reachable from cap-hold re-entry."""
    source = (Path(__file__).parents[2] / 'utils/batch_pipeline/intake.py').read_text()
    function = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'accept_upload'
    )
    bindings = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'ProjectionBinding'
    ]
    assert bindings, 'accept_upload must build the upload ProjectionBinding'
    assert all(keyword.arg != 'native_record' for call in bindings for keyword in call.keywords)
    assert ProjectionBinding(UID, 'bp', 'c', ('s',)).native_record is False
    admit_source = (Path(__file__).parents[2] / 'utils/batch_pipeline/cap_hold_admission.py').read_text()
    assert 'intake.accept_upload(' in admit_source and 'native_record' not in admit_source
