"""Per-owner v3 backfill/repair: live parity, partitions, reversible conversion, task chain, operator.

Synthetic data only. The parity tests feed the same sources through a live builder pass and a
derive pass and require identical windows, Home decisions and notes inputs; the only differences
allowed are the backfill stamps and the notes marker the backfill drains itself.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from database import conversations_v3_leases as leases
from database import conversations_v3_processing as writers
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.v3 import backfill, outline, service
from tests.unit.test_conversations_v3_review import AT, builder  # noqa: F401
from tests.unit.test_conversations_v3_transactions import R, strict  # noqa: F401

RUN = 'run-1'
BACKFILL_ONLY = {'backfilled', 'v3_backfill_run', 'v3_process_pending', 'v3_backfill_process_pending'}


def legacy(cid, start, words, **extra):
    """A completed legacy capture as the derive loader hands it to the builder."""
    return {
        'id': cid,
        'source': 'omi',
        'status': 'completed',
        'started_at': start,
        'finished_at': start + timedelta(seconds=60),
        'language': 'en',
        'structured': {'title': 'Legacy notes'},
        'transcript_segments': [
            {'id': cid + '-s', 'text': 'word ' * words, 'start': 0, 'end': 60, 'is_user': extra.pop('is_user', True)}
        ],
        **extra,
    }


def as_live(row):
    return {**row, 'recording': True, 'v3_pending': True}


def as_derive(row):
    return {**row, 'recording': True, '_v3_derive': True, '_v3_backfill_run': RUN, '_v3_backfill_prior': {}}


def outline_reply(*chapters):
    import json

    return json.dumps({'conversations': list(chapters)})


async def committed_rows(builder_fixture, monkeypatch, sources, *, derive):
    committed, _ = builder_fixture
    committed.clear()
    if derive:
        monkeypatch.setattr(
            store, 'load_derive', lambda *a, **kw: ({k: as_derive(v) for k, v in sources.items()}, {}, [])
        )
        outcome = await service.reconcile('u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN)
    else:
        monkeypatch.setattr(store, 'load', lambda *a, **kw: ({k: as_live(v) for k, v in sources.items()}, {}, []))
        outcome = await service.reconcile('u')
    assert outcome == 'committed'
    return committed[-1][4]


def comparable(row):
    return {k: v for k, v in row.items() if k not in BACKFILL_ONLY}


SCENARIOS = {
    'long_visible': (
        {'a': legacy('a', AT, 400)},
        outline_reply({'first_line': 1, 'title': 'Planning', 'line': 'You planned.', 'kind': 'conversation'}),
    ),
    'short_hidden': (
        {'a': legacy('a', AT, 50)},
        outline_reply({'first_line': 1, 'title': 'Short', 'line': '', 'kind': 'conversation'}),
    ),
    'media_hidden': (
        {'a': legacy('a', AT, 500)},
        outline_reply({'first_line': 1, 'title': 'A film', 'line': '', 'kind': 'media'}),
    ),
    'background_recognised_hidden': (
        {'a': legacy('a', AT, 500, is_user=True)},
        outline_reply({'first_line': 1, 'title': 'Nearby talk', 'line': '', 'kind': 'background'}),
    ),
    'background_uncertain_shown': (
        {'a': legacy('a', AT, 500, is_user=False)},
        outline_reply({'first_line': 1, 'title': 'Nearby talk', 'line': '', 'kind': 'background'}),
    ),
    'manual_end_short_visible': (
        {'a': legacy('a', AT, 30, v3_manual_end=True)},
        outline_reply({'first_line': 1, 'title': 'Quick note', 'line': '', 'kind': 'voice_work'}),
    ),
    'silence_splits': (
        {'a': legacy('a', AT, 400), 'b': legacy('b', AT + timedelta(minutes=7), 400)},
        outline_reply({'first_line': 1, 'title': 'Part', 'line': '', 'kind': 'conversation'}),
    ),
    'resumes_within_silence_joins': (
        {'a': legacy('a', AT, 200), 'b': legacy('b', AT + timedelta(minutes=2), 200)},
        outline_reply({'first_line': 1, 'title': 'Long talk', 'line': '', 'kind': 'conversation'}),
    ),
}


@pytest.fixture
def no_evidence(monkeypatch):
    def hydrate(uid, recordings, windows):
        for row in recordings.values():
            row['_v3_wearer_recognized'] = any(s.get('is_user') is True for s in row.get('transcript_segments') or [])

    monkeypatch.setattr(service.visibility, 'hydrate_recognition', hydrate)


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', sorted(SCENARIOS))
async def test_derive_pass_matches_the_live_builder_on_the_same_inputs(builder, monkeypatch, no_evidence, scenario):
    sources, reply = SCENARIOS[scenario]
    monkeypatch.setattr(service.models, 'outline', lambda *a: reply)
    live = await committed_rows(builder, monkeypatch, sources, derive=False)
    derived = await committed_rows(builder, monkeypatch, sources, derive=True)
    assert live and [comparable(r) for r in derived] == [comparable(r) for r in live]
    for live_row, row in zip(live, derived):
        assert row['backfilled'] is True and row['v3_backfill_run'] == RUN
        # Same notes obligation, on the backfill's own marker (never the live sweep's).
        assert bool(row.get('v3_backfill_process_pending')) == bool(live_row.get('v3_process_pending'))
        assert not row.get('v3_process_pending')


@pytest.mark.asyncio
async def test_parity_scenarios_cover_each_home_rule(builder, monkeypatch, no_evidence):
    reasons = set()
    for sources, reply in SCENARIOS.values():
        monkeypatch.setattr(service.models, 'outline', lambda *a, reply=reply: reply)
        reasons.update(
            r['home_hidden_reason'] for r in await committed_rows(builder, monkeypatch, sources, derive=True)
        )
    assert reasons >= {
        'conversation',
        'below_word_minimum',
        'media',
        'background_wearer_recognized',
        'wearer_recognition_uncertain',
        'manual_end',
    }


@pytest.mark.asyncio
async def test_a_live_pass_over_an_interrupted_backfill_keeps_rows_historical(builder, monkeypatch, no_evidence):
    committed, _ = builder
    donor = {**as_live(legacy('a', AT, 400)), 'v3_backfill_run': RUN}
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'a': donor}, {}, []))
    await service.reconcile('u')
    row = committed[-1][4][0]
    assert row['backfilled'] is True and row['v3_backfill_run'] == RUN


@pytest.mark.asyncio
async def test_derive_never_wakes_the_live_queue_and_leaves_notes_to_its_own_drain(builder, monkeypatch, no_evidence):
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: pytest.fail('backfill must not use the live queue'))
    sources, reply = SCENARIOS['long_visible']
    monkeypatch.setattr(service.models, 'outline', lambda *a: reply)
    await committed_rows(builder, monkeypatch, sources, derive=True)
    service.drain_processing.assert_not_awaited()


@pytest.mark.asyncio
async def test_rederive_retires_prior_copies_no_new_window_claims(builder, monkeypatch, no_evidence):
    committed, _ = builder
    stale = {
        'id': 'stale',
        'v3_derived': True,
        'backfilled': True,
        'status': 'in_progress',
        'started_at': AT + timedelta(hours=3),
        'finished_at': AT + timedelta(hours=3, minutes=1),
        '_v3_revision': 1,
    }
    monkeypatch.setattr(
        store, 'load_derive', lambda *a, **kw: ({'a': as_derive(legacy('a', AT, 400))}, {'stale': stale}, [])
    )
    monkeypatch.setattr(service.models, 'outline', lambda *a: SCENARIOS['long_visible'][1])
    seen = {}
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: seen.update(kw))
    await service.reconcile('u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN, rederive=True)
    assert seen['remove'] == ['stale'] and seen['key'] == store.BACKFILL_LEASE


def test_backfilled_rows_take_the_live_trigger_and_floor(monkeypatch):
    from utils.conversations import lifecycle, process_conversation as process

    row = {
        'id': 'w',
        'v3_derived': True,
        'backfilled': True,
        'kind': 'conversation',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'structured': {},
        # 100 words: live writes task-only notes; the previous backfill floor (600) skipped them.
        'transcript_segments': [{'text': 'word ' * 100, 'start': 0, 'end': 10, 'is_user': False}],
    }
    triggers = []
    monkeypatch.setattr(writers, 'begin_processing', lambda *a, **kw: True)
    monkeypatch.setattr(writers, 'settle_processing', lambda *a, **kw: None)
    monkeypatch.setattr(lifecycle, 'complete', lambda *a: pytest.fail('backfill skipped live notes'))

    def notes(uid, language, conversation, **kw):
        triggers.append(kw['trigger'])
        kw['persistence_observer'](True)
        return SimpleNamespace(status='completed')

    monkeypatch.setattr(process, 'process_conversation', notes)
    service._process('u', row, 'token')
    assert triggers == [ProcessingTrigger.CAPTURE_END]


# ---- partitions -----------------------------------------------------------------------------


def meta(minutes, length=1):
    return {
        'id': f'm{minutes}',
        'started_at': AT + timedelta(minutes=minutes),
        'finished_at': AT + timedelta(minutes=minutes + length),
    }


def test_partitions_cut_only_at_live_silence_boundaries():
    # Ten rows two minutes apart, a 30-minute silence, ten more.
    rows = [meta(2 * i) for i in range(10)] + [meta(60 + 2 * i) for i in range(10)]
    parts = backfill.plan_partitions(rows, AT, AT + timedelta(days=1), max_rows=12)
    assert [p['documents'] for p in parts] == [10, 10]
    assert parts[0]['since'] == AT and parts[-1]['until'] == AT + timedelta(days=1)
    assert parts[1]['since'] == AT + timedelta(minutes=60) == parts[0]['until']
    assert not any(p['forced_cut'] for p in parts)
    # Each partition is a whole set of live stretches.
    stretch_ids = [
        {line['conversation_id'] for line in group['lines']}
        for group in outline.stretches(
            [{**r, 'transcript_segments': [{'text': 'x', 'start': 0, 'end': 60}]} for r in rows],
            AT + timedelta(days=1),
        )
    ]
    for ids in stretch_ids:
        assert (
            sum(bool(ids & {r['id'] for r in rows if p['since'] <= r['started_at'] < p['until']}) for p in parts) == 1
        )


def test_a_gap_free_run_over_the_cap_is_a_counted_forced_cut():
    rows = [meta(2 * i) for i in range(30)]
    parts = backfill.plan_partitions(rows, AT, AT + timedelta(days=1), max_rows=12)
    assert sum(p['documents'] for p in parts) == 30 and max(p['documents'] for p in parts) <= 12
    assert any(p['forced_cut'] for p in parts)


def test_empty_window_is_one_empty_partition():
    assert backfill.plan_partitions([], AT, AT + timedelta(days=2))[0]['documents'] == 0


def test_window_classification_counts_what_stays_legacy():
    rows = [
        {'source': 'omi', 'status': 'completed', 'started_at': AT},
        {'source': 'phone', 'status': 'completed', 'started_at': AT, 'data_protection_level': 'private'},
        {'source': 'omi', 'status': 'completed', 'started_at': AT, 'discarded': True},
        {'source': 'desktop', 'status': 'completed', 'started_at': AT},
        {'source': 'omi', 'status': 'completed', 'started_at': AT, 'recording': True},
        {'source': 'omi', 'status': 'completed', 'started_at': AT, 'v3_backfill_run': RUN, 'recording': True},
    ]
    counts = backfill.classify_window(rows)
    assert counts['legacy_donors'] == 1
    assert counts['skipped_private'] == 1 and counts['skipped_discarded'] == 1
    assert counts['skipped_other_source'] == 1 and counts['live_v3'] == 1 and counts['already_backfilled'] == 1


# ---- loader ---------------------------------------------------------------------------------


class Snapshot:
    def __init__(self, cid, data):
        self.id, self._data, self.exists, self.update_time = cid, data, data is not None, 1

    def to_dict(self):
        return deepcopy(self._data)


class Query:
    def __init__(self, rows, filters=()):
        self.rows, self.filters = rows, filters

    def where(self, filter):
        return Query(self.rows, (*self.filters, filter))

    def order_by(self, *a, **kw):
        return self

    def limit(self, n):
        return self

    def select(self, fields):
        return self

    def stream(self):
        ops = {'>=': lambda a, b: a >= b, '<': lambda a, b: a < b, '==': lambda a, b: a == b}
        for cid, row in self.rows.items():
            if all(
                row.get(f.field_path) is not None and ops[f.op_string](row.get(f.field_path), f.value)
                for f in self.filters
            ):
                yield Snapshot(cid, row)

    def document(self, cid):
        return SimpleNamespace(get=lambda: Snapshot(cid, self.rows.get(cid)))


class Client:
    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        return SimpleNamespace(document=lambda uid: SimpleNamespace(collection=lambda sub: self._coll(sub)))

    def _coll(self, sub):
        return Query(self.rows) if sub == 'conversations' else Query({})


@pytest.fixture
def loader(monkeypatch):
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a, **kw: False)

    def decode(uid, snapshot):
        return {**snapshot.to_dict(), 'id': snapshot.id, '_v3_revision': snapshot.update_time}

    monkeypatch.setattr(store, 'decode_row', decode)


def test_loader_takes_legacy_donors_and_leaves_everything_else(loader):
    rows = {
        'donor': legacy('donor', AT, 100, relevance_decision={'trigger': 'client_finalize'}),
        'private': legacy('private', AT, 100, data_protection_level='private'),
        'discarded': legacy('discarded', AT, 100, discarded=True),
        'imported': legacy('imported', AT, 100, imported=True),
        'live': {**legacy('live', AT, 100), 'recording': True},
        'outside': legacy('outside', AT + timedelta(days=3), 100),
    }
    recordings, existing, _ = store.load_derive(
        'u', since=AT - timedelta(hours=1), until=AT + timedelta(days=1), run_id=RUN, firestore_client=Client(rows)
    )
    assert set(recordings) == {'donor'} and existing == {}
    donor = recordings['donor']
    assert donor['_v3_derive'] and donor['_v3_backfill_run'] == RUN and donor['recording'] is True
    # Manual stop survives from the legacy relevance record into the v3 manual-end rule.
    assert donor['v3_manual_end'] is True
    assert donor['_v3_backfill_prior'] == {}


def test_loader_resumes_its_own_run_and_rederive_resets_prior_copies(loader):
    rows = {
        'donor': {**legacy('donor', AT, 100), 'recording': True, 'v3_backfill_run': RUN},
        'other-run': {**legacy('other-run', AT, 100), 'recording': True, 'v3_backfill_run': 'run-0'},
        'copy': {
            'v3_derived': True,
            'backfilled': True,
            'v3_backfill_run': RUN,
            'started_at': AT,
            'finished_at': AT + timedelta(minutes=1),
            'status': 'completed',
            'structured': {'title': 'Old derived'},
            'title_locked': True,
        },
    }
    window = {'since': AT - timedelta(hours=1), 'until': AT + timedelta(hours=1)}
    recordings, existing, _ = store.load_derive('u', run_id=RUN, firestore_client=Client(rows), **window)
    assert set(recordings) == {'donor'} and existing['copy']['status'] == 'completed'
    recordings, existing, _ = store.load_derive('u', run_id=RUN, rederive=True, firestore_client=Client(rows), **window)
    assert set(recordings) == {'donor', 'other-run'}
    # Same id offered as an open window: rebuilt boundaries, text and notes, never a delete+recreate.
    assert existing['copy']['status'] == 'in_progress' and existing['copy']['structured'] == {}
    assert existing['copy']['title_locked'] is False


def test_loader_refuses_an_overfull_partition(loader, monkeypatch):
    monkeypatch.setattr(store, 'LIMIT', 2)
    rows = {f'r{i}': legacy(f'r{i}', AT, 10) for i in range(3)}
    with pytest.raises(store.Conflict, match='backfill_partition_budget'):
        store.load_derive('u', since=AT, until=AT + timedelta(days=1), run_id=RUN, firestore_client=Client(rows))


# ---- reversible conversion and undo ---------------------------------------------------------

LEGACY_DONOR = {
    'id': 'r',
    'source': 'omi',
    'status': 'completed',
    'started_at': AT,
    'finished_at': AT + timedelta(minutes=1),
    'structured': {'title': 'Old notes', 'overview': 'Legacy summary'},
    'v3_pending': False,
}
COPY = ('users', 'synthetic', 'conversations', 'c0')
BACKFILL_LEASE = ('users', 'synthetic', 'conversation_v3_leases', store.BACKFILL_LEASE)


def convert(strict):
    strict.rows[R] = deepcopy(LEGACY_DONOR)
    token = leases.acquire('synthetic', store.BACKFILL_LEASE, firestore_client=strict)
    donor = {
        **deepcopy(LEGACY_DONOR),
        'recording': True,
        '_v3_derive': True,
        '_v3_revision': 1,
        '_v3_backfill_run': RUN,
        '_v3_backfill_prior': {k: LEGACY_DONOR[k] for k in store.BACKFILL_TRACKED if k in LEGACY_DONOR},
    }
    row = {
        'id': 'c0',
        'v3_derived': True,
        'backfilled': True,
        'v3_backfill_run': RUN,
        'status': 'processing',
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=1),
        'v3_recording_ids': ['r'],
        'transcript_segments': [{'text': 'copied speech'}],
    }
    store.commit_projection(
        'synthetic', token, {'r': donor}, {}, [row], [], key=store.BACKFILL_LEASE, firestore_client=strict
    )
    return token


def stored(row):
    """The document as Firestore would hold it: StrictFirestore keeps DELETE_FIELD as a value."""
    return {k: v for k, v in row.items() if type(v).__name__ != 'Sentinel'}


def test_conversion_keeps_legacy_notes_and_undo_restores_the_donor_exactly(strict):
    token = convert(strict)
    assert strict.rows[R]['recording'] is True and strict.rows[R]['structured'] == LEGACY_DONOR['structured']
    assert strict.rows[R]['claims'] and strict.rows[COPY]['backfilled'] is True
    assert store.restore_backfill_donors('synthetic', token, ['r'], firestore_client=strict) == 1
    assert store.delete_backfill_rows('synthetic', token, ['c0'], firestore_client=strict) == 1
    assert stored(strict.rows[R]) == LEGACY_DONOR
    assert COPY not in strict.rows
    # No tombstone: the window can be derived again later.
    assert ('users', 'synthetic', 'deleted_conversations', 'c0') not in strict.rows


def test_undo_never_touches_live_rows_and_requires_its_lease(strict):
    token = convert(strict)
    live = ('users', 'synthetic', 'conversations', 'live')
    strict.rows[live] = {'id': 'live', 'v3_derived': True, 'status': 'completed'}
    assert store.delete_backfill_rows('synthetic', token, ['live'], firestore_client=strict) == 0
    assert live in strict.rows
    with pytest.raises(store.Conflict, match='lease_lost'):
        store.restore_backfill_donors('synthetic', 'stale-token', ['r'], firestore_client=strict)


def test_deleting_a_backfilled_copy_never_arms_the_donor_audio_purge(strict):
    convert(strict)
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    copy = {**strict.rows[COPY]}
    store.release_claims('synthetic', copy, firestore_client=strict)
    assert strict.rows[R]['claims'] == [] and strict.rows[R]['v3_audio_purge_pending'] is False
    strict.rows[R]['v3_audio_purge_pending'] = True
    assert store.claim_audio_purge('synthetic', 'r', firestore_client=strict) is False
    assert not strict.rows[R].get('deleted')


@pytest.mark.parametrize(
    'failed,attempts,live_failed,expected',
    [(False, 0, False, 'settled'), (False, 0, True, 'failed'), (True, 0, False, 'retry'), (True, 2, False, 'failed')],
)
def test_backfill_notes_marker_settles_parks_or_fails(strict, failed, attempts, live_failed, expected):
    path = ('users', 'synthetic', 'conversations', 'w')
    strict.rows[path] = {
        'id': 'w',
        'v3_backfill_process_pending': True,
        'v3_process_pending': failed,
        'v3_process_failed': live_failed,
        'v3_backfill_attempts': attempts,
        'transcript_segments': [{'text': 'x'}],
    }
    outcome = writers.settle_backfill_processing(
        'synthetic', 'w', failed=failed, max_attempts=3, firestore_client=strict
    )
    assert outcome == expected
    row = strict.rows[path]
    # Never left on the live sweep's marker.
    assert row['v3_process_pending'] is False
    assert row['v3_backfill_process_pending'] is (expected == 'retry')
    if expected == 'failed':
        assert row['v3_process_failed'] is True
    if failed and expected == 'failed':
        assert row['tile_state'] == 'failed'


# ---- drain, task chain and undo orchestration -----------------------------------------------


@pytest.fixture
def direct(monkeypatch):
    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    for module in (service, backfill):
        monkeypatch.setattr(module, 'run_blocking', blocking)


@pytest.mark.asyncio
async def test_drain_runs_live_notes_and_settles_each_row(direct, monkeypatch):
    rows = [{'id': 'ok'}, {'id': 'boom'}]
    pending = [rows, []]
    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid: pending.pop(0))
    monkeypatch.setattr(leases, 'acquire', lambda *a: 'token')
    released = []
    monkeypatch.setattr(leases, 'release', lambda *a: released.append(a[1]))

    async def process(uid, row, token):
        if row['id'] == 'boom':
            raise RuntimeError('synthetic')

    monkeypatch.setattr(service, '_process_leased', process)
    settled = []

    def settle(uid, cid, *, failed, max_attempts):
        settled.append((cid, failed))
        return 'retry' if failed else 'settled'

    monkeypatch.setattr(writers, 'settle_backfill_processing', settle)
    counts = await service.drain_backfill('u', deadline=float('inf'))
    assert sorted(settled) == [('boom', True), ('ok', False)]
    assert counts['processed'] == 1 and counts['retry'] == 1 and counts['remaining'] == 0
    assert sorted(released) == ['summary-boom', 'summary-ok']


class Ledger:
    def __init__(self, partitions, status='planned', mode='derive'):
        self.run = {
            'run_id': RUN,
            'status': status,
            'mode': mode,
            'partitions': [
                {'since': AT, 'until': AT + timedelta(hours=1), 'status': 'pending'} for _ in range(partitions)
            ],
        }

    def get(self, uid, run_id):
        return deepcopy(self.run)

    def update(self, uid, run_id, *, status=None, partition=None, patch=None, expect=None):
        if expect is not None and self.run['status'] not in expect:
            return None
        if status:
            self.run['status'] = status
        if partition:
            index, fields = partition
            self.run['partitions'][index].update(fields)
        self.run.update(patch or {})
        return self.run


@pytest.fixture
def chain(direct, monkeypatch):
    ledger = Ledger(2)
    monkeypatch.setattr(runs, 'get_run', ledger.get)
    monkeypatch.setattr(runs, 'update_run', ledger.update)
    steps = []
    monkeypatch.setattr(
        backfill,
        'enqueue_step',
        lambda uid, run_id, index, phase='derive', seq=0, gen=0: steps.append((index, phase, seq)),
    )
    monkeypatch.setattr(
        service, 'drain_backfill', AsyncMock(return_value={'processed': 3, 'failed': 0, 'remaining': 0})
    )
    return ledger, steps


@pytest.mark.asyncio
async def test_a_step_derives_drains_records_and_chains_the_next_partition(chain, monkeypatch):
    ledger, steps = chain

    async def reconcile(uid, **kw):
        kw['report'].update(windows=4, outline_calls=2)
        return 'committed'

    monkeypatch.setattr(service, 'reconcile', reconcile)
    assert (await backfill.run_step('u', RUN, 0, 'derive'))['outcome'] == 'committed'
    assert steps == [(1, 'derive', 0)]
    part = ledger.run['partitions'][0]
    assert part['status'] == 'committed' and part['windows'] == 4 and part['notes_processed'] == 3
    assert ledger.run['status'] == 'running'
    assert (await backfill.run_step('u', RUN, 1, 'derive'))['last'] is True
    assert ledger.run['status'] == 'committed' and steps == [(1, 'derive', 0)]


@pytest.mark.asyncio
async def test_a_redelivered_step_after_commit_only_drains(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['partitions'][0]['status'] = 'notes'
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=AssertionError('derived twice')))
    await backfill.run_step('u', RUN, 0, 'derive')
    assert ledger.run['partitions'][0]['status'] == 'committed'


@pytest.mark.asyncio
async def test_unfinished_notes_continue_on_a_new_named_drain_task(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['partitions'][0]['status'] = 'notes'
    service.drain_backfill.return_value = {'processed': 1, 'failed': 0, 'remaining': 5}
    assert (await backfill.run_step('u', RUN, 0, 'drain'))['outcome'] == 'draining'
    assert steps == [(0, 'drain', 1)] and ledger.run['partitions'][0]['notes_remaining'] == 5


@pytest.mark.asyncio
async def test_blocked_partition_stops_the_run_and_busy_retries(chain, monkeypatch):
    ledger, steps = chain

    async def busy(uid, **kw):
        return 'busy'

    monkeypatch.setattr(service, 'reconcile', busy)
    with pytest.raises(backfill.BackfillRetry):
        await backfill.run_step('u', RUN, 0, 'derive')

    async def blocked(uid, **kw):
        kw['report']['blocked_reason'] = 'backfill_partition_budget'
        return 'blocked'

    monkeypatch.setattr(service, 'reconcile', blocked)
    result = await backfill.run_step('u', RUN, 0, 'derive')
    assert result == {'outcome': 'blocked', 'reason': 'backfill_partition_budget'}
    assert ledger.run['status'] == 'blocked' and not steps
    # A stopped run takes no further work.
    assert (await backfill.run_step('u', RUN, 1, 'derive'))['outcome'] == 'blocked'


@pytest.mark.asyncio
async def test_sweep_start_is_inert_while_the_switch_is_off(direct, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'off')
    monkeypatch.setattr(runs, 'pending_starts', lambda *a: pytest.fail('read while off'))
    assert await backfill.start_planned() == 0
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(runs, 'pending_starts', lambda *a: [{'uid': 'u', 'run_id': RUN}])
    monkeypatch.setattr(runs, 'get_run', Ledger(1).get)
    cleared, steps = [], []
    monkeypatch.setattr(runs, 'clear_start', cleared.append)
    monkeypatch.setattr(backfill, 'enqueue_step', lambda *a: steps.append(a))
    assert await backfill.start_planned() == 1 and steps == [('u', RUN, 0, 'derive', 0, 0)] and cleared == [RUN]


def test_resume_rearms_a_blocked_run_from_its_first_unfinished_partition(monkeypatch):
    ledger = Ledger(3, status='blocked')
    ledger.run['partitions'][0]['status'] = 'committed'
    ledger.run['partitions'][1].update(status='blocked', reason='source_changed')
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: ledger.get(*a))
    monkeypatch.setattr(
        runs,
        'update_run',
        lambda *a, **kw: ledger.update(*a[:2], **{k: v for k, v in kw.items() if k != 'firestore_client'}),
    )
    starts = []
    monkeypatch.setattr(runs, 'mark_start', lambda uid, run_id, **kw: starts.append(run_id))
    assert backfill.resume_run('u', RUN) == {'outcome': 'resumed', 'partition': 1}
    assert ledger.run['status'] == 'planned' and ledger.run['resumes'] == 1 and starts == [RUN]
    assert ledger.run['partitions'][1]['status'] == 'pending'
    ledger.run['status'] = 'undone'
    assert backfill.resume_run('u', RUN)['outcome'] == 'not_resumable'


def test_undo_restores_donors_before_removing_copies_and_waits_for_notes(monkeypatch):
    ledger = Ledger(1, status='committed')
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: ledger.get(*a))
    monkeypatch.setattr(
        runs,
        'update_run',
        lambda *a, **kw: ledger.update(*a[:2], **{k: v for k, v in kw.items() if k != 'firestore_client'}),
    )
    docs = [{'id': 'd1'}, {'id': 'c1', 'v3_derived': True}]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: docs)
    monkeypatch.setattr(leases, 'held', lambda *a, **kw: True)
    assert backfill.undo_run('u', RUN) == {'outcome': 'busy', 'reason': 'notes_in_flight'}
    assert ledger.run['status'] == 'undoing'
    monkeypatch.setattr(leases, 'held', lambda *a, **kw: False)
    monkeypatch.setattr(leases, 'acquire', lambda *a, **kw: 'token')
    monkeypatch.setattr(leases, 'renew', lambda *a, **kw: None)
    monkeypatch.setattr(leases, 'release', lambda *a, **kw: None)
    order = []
    monkeypatch.setattr(
        store, 'restore_backfill_donors', lambda uid, token, ids, **kw: order.append(('restore', ids)) or 1
    )
    monkeypatch.setattr(store, 'delete_backfill_rows', lambda uid, token, ids, **kw: order.append(('delete', ids)) or 1)
    result = backfill.undo_run('u', RUN)
    assert result == {'outcome': 'undone', 'donors_restored': 1, 'rows_removed': 1}
    assert order == [('restore', ['d1']), ('delete', ['c1'])] and ledger.run['status'] == 'undone'


@pytest.mark.asyncio
async def test_route_respects_the_switch_and_maps_busy_to_retry(monkeypatch):
    from fastapi import HTTPException
    from routers import conversations_v3_tasks as route

    body = route.BackfillRequest(uid='u', run_id=RUN, partition=0)
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'off')
    with pytest.raises(HTTPException) as off:
        await route.run_backfill(body, _retry=0)
    assert off.value.status_code == 404
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=backfill.BackfillRetry('busy')))
    with pytest.raises(HTTPException) as busy:
        await route.run_backfill(body, _retry=0)
    assert busy.value.status_code == 503


# ---- operator script ------------------------------------------------------------------------


def test_dry_run_prints_counts_only_and_writes_nothing(tmp_path, monkeypatch, capsys):
    from scripts import conversations_v3_backfill as script

    secret_uid = 'synthetic-owner-uid-123'
    owners = tmp_path / 'owners.txt'
    owners.write_text('# owners\n' + secret_uid + '\n')
    rows = [meta(2 * i) for i in range(5)]
    monkeypatch.setattr(store, 'backfill_window_metadata', lambda *a: rows)
    monkeypatch.setattr(
        backfill,
        'estimate_partition',
        lambda *a, **kw: {'sources': 5, 'stretches': 1, 'outline_calls': 1, 'notes_calls': 1, 'usd': 0.01},
    )
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])
    monkeypatch.setattr(backfill, 'create_run', lambda *a, **kw: pytest.fail('dry-run wrote a run'))
    monkeypatch.setattr(runs, 'mark_start', lambda *a, **kw: pytest.fail('dry-run wrote a start'))
    assert script.main(['run', '--owners-file', str(owners), '--days', '2', '--dry-run']) == 0
    out = capsys.readouterr().out
    assert secret_uid not in out
    assert 'owner[1] estimate' in out and 'outline_calls=1' in out and 'partitions=1' in out


def test_owner_file_rejects_paths_and_duplicates(tmp_path):
    from scripts import conversations_v3_backfill as script

    bad = tmp_path / 'owners.txt'
    bad.write_text('a\na\n')
    with pytest.raises(SystemExit):
        script.read_owners(str(bad))
    bad.write_text('users/a\n')
    with pytest.raises(SystemExit):
        script.read_owners(str(bad))
