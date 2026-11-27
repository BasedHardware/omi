"""Per-owner v3 backfill/repair: live parity, partitions, reversible conversion, task chain, operator.

Synthetic data only. The parity tests feed the same sources through a live builder pass and a
derive pass and require identical windows, Home decisions and notes inputs; the only differences
allowed are the backfill stamps and the notes marker the backfill drains itself.
"""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

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

    def commit(*args, **kwargs):
        seen.update(kwargs)
        return set()

    monkeypatch.setattr(service, '_commit', commit)
    report = {}
    await service.reconcile(
        'u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN, rederive=True, report=report
    )
    assert seen['remove'] == ['stale'] and seen['key'] == store.BACKFILL_LEASE
    assert report['rows_removed'] == 0


@pytest.mark.asyncio
async def test_a_donor_no_window_claims_stays_a_visible_legacy_row(builder, monkeypatch, no_evidence):
    empty = {**legacy('empty', AT + timedelta(hours=2), 0), 'transcript_segments': []}
    sources = {'a': as_derive(legacy('a', AT, 400)), 'empty': as_derive(empty)}
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: (sources, {}, []))
    monkeypatch.setattr(service.models, 'outline', lambda *a: SCENARIOS['long_visible'][1])
    seen = {}
    monkeypatch.setattr(service, '_commit', lambda uid, token, recordings, *a, **kw: seen.update(recordings))
    report = {}
    outcome = await service.reconcile(
        'u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN, report=report
    )
    # Converting 'empty' would hide it as a recording with no derived row to replace it.
    assert outcome == 'committed' and set(seen) == {'a'} and report['sources_unclaimed'] == 1


@pytest.mark.asyncio
async def test_a_converted_donor_no_rebuilt_window_claims_blocks_the_partition(builder, monkeypatch, no_evidence):
    converted = {
        **legacy('b', AT + timedelta(hours=2), 0),
        'transcript_segments': [],
        'recording': True,
        '_v3_derive': True,
        '_v3_backfill_run': RUN,
    }
    sources = {'a': as_derive(legacy('a', AT, 400)), 'b': converted}
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: (sources, {}, []))
    monkeypatch.setattr(service.models, 'outline', lambda *a: SCENARIOS['long_visible'][1])
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: pytest.fail('left a converted donor hidden with no copy'))
    report = {}
    outcome = await service.reconcile(
        'u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN, rederive=True, report=report
    )
    assert outcome == 'blocked' and report['blocked_reason'] == 'backfill_donor_unclaimed'


@pytest.mark.asyncio
async def test_rederive_never_merges_rows_owned_by_different_runs(builder, monkeypatch, no_evidence):
    a = as_derive(legacy('a', AT, 200))
    b = {**as_derive(legacy('b', AT + timedelta(minutes=2), 200)), '_v3_backfill_run': 'run-2'}
    monkeypatch.setattr(store, 'load_derive', lambda *a_, **kw: ({'a': a, 'b': b}, {}, []))
    monkeypatch.setattr(service.models, 'outline', lambda *a_: SCENARIOS['resumes_within_silence_joins'][1])
    monkeypatch.setattr(service, '_commit', lambda *a_, **kw: pytest.fail('committed a mixed-run window'))
    report = {}
    outcome = await service.reconcile(
        'u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN, rederive=True, report=report
    )
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_mixed_runs'


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
    # Equal gaps cut at the latest one: full partitions, not one row (and one outline call) each.
    assert [p['documents'] for p in parts] == [11, 11, 8]


def test_empty_window_is_one_empty_partition():
    assert backfill.plan_partitions([], AT, AT + timedelta(days=2))[0]['documents'] == 0


def test_window_classification_counts_what_stays_legacy():
    rows = [
        {'source': 'omi', 'status': 'completed', 'started_at': AT},
        {'source': 'phone', 'status': 'completed', 'started_at': AT, 'data_protection_level': 'private'},
        {'source': 'omi', 'status': 'completed', 'started_at': AT, 'discarded': True},
        {'source': 'desktop', 'status': 'completed', 'started_at': AT},
        {'source': 'omi', 'status': 'processing', 'started_at': AT},
        {'source': 'omi', 'status': 'completed', 'started_at': AT, 'recording': True},
        {'source': 'omi', 'status': 'completed', 'started_at': AT, 'v3_backfill_run': RUN, 'recording': True},
    ]
    counts = backfill.classify_window(rows)
    assert counts['legacy_candidates'] == 1
    assert counts['skipped_private'] == 1 and counts['skipped_discarded'] == 1
    assert counts['skipped_other_source'] == 1 and counts['live_v3'] == 1 and counts['already_backfilled'] == 1
    assert counts['skipped_not_completed'] == 1


def test_estimate_prices_each_stretch_on_the_live_notes_floors(monkeypatch):
    gap = timedelta(minutes=10)
    sources = {
        cid: as_derive(legacy(cid, AT + i * gap, words))
        for i, (cid, words) in enumerate([('agent', 1600), ('notes', 400), ('tasks', 50), ('none', 5)])
    }
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: (sources, {}, []))
    est = backfill.estimate_partition(
        'u', {'since': AT, 'until': AT + timedelta(days=1)}, RUN, now=AT + timedelta(days=2)
    )
    assert est['stretches'] == est['outline_calls'] == 4 and est['words'] == 2055
    assert (est['notes_calls'], est['agent_notes'], est['short_task_calls'], est['no_model_windows']) == (2, 1, 1, 1)

    def usd(tokens_in, tokens_out):
        return tokens_in * 0.10 / 1e6 + tokens_out * 0.60 / 1e6

    expected = sum(usd(1100 + w * 1.4, 350) for w in (1600, 400, 50, 5))
    expected += 0.02 + usd(5000 + 400 * 1.4, 1500) + usd(1500 + 50 * 1.4, 250)
    assert est['usd'] == pytest.approx(expected)


@pytest.mark.parametrize('letter', ['界', 'あ'])
def test_backfill_estimate_uses_script_aware_notes_floors(monkeypatch, letter):
    sources = {}
    for index, words in enumerate((19, 20, 149, 150)):
        cid = f'capture-{index}'
        row = legacy(cid, AT + timedelta(minutes=10 * index), words)
        row['transcript_segments'][0]['text'] = letter * words
        sources[cid] = as_derive(row)
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: (sources, {}, []))
    estimate = backfill.estimate_partition(
        'u', {'since': AT, 'until': AT + timedelta(days=1)}, RUN, now=AT + timedelta(days=2)
    )
    assert estimate['words'] == 19 + 20 + 149 + 150
    assert estimate['no_model_windows'] == 1
    assert estimate['short_task_calls'] == 2
    assert estimate['notes_calls'] == 1


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
            'v3_backfill_attempts': 2,
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
    # The rebuilt window decides its own notes obligation; no stale marker rides along.
    assert existing['copy']['v3_backfill_process_pending'] is False and existing['copy']['v3_process_pending'] is False
    assert existing['copy']['v3_backfill_attempts'] == 0


def test_an_unreadable_converted_donor_blocks_instead_of_retiring_its_copy(loader, monkeypatch):
    rows = {
        'donor': {**legacy('donor', AT, 100), 'recording': True, 'v3_backfill_run': RUN},
        'copy': {
            'v3_derived': True,
            'backfilled': True,
            'v3_backfill_run': RUN,
            'started_at': AT,
            'finished_at': AT + timedelta(minutes=1),
            'status': 'completed',
        },
    }
    monkeypatch.setattr(store, 'recording_input', lambda uid, snapshot: {'_v3_unreadable': True})
    window = {'since': AT - timedelta(hours=1), 'until': AT + timedelta(hours=1)}
    for rederive in (False, True):
        with pytest.raises(store.Conflict, match='backfill_source_unreadable'):
            store.load_derive('u', run_id=RUN, rederive=rederive, firestore_client=Client(rows), **window)
    assert 'backfill_source_unreadable' in service.BLOCKED


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
    assert strict.rows[R]['home_list_visible'] is False
    assert strict.rows[COPY]['home_list_visible'] is True
    assert strict.rows[R]['claims'] and strict.rows[COPY]['backfilled'] is True
    assert store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict) == (
        'undone',
        1,
        1,
    )
    assert stored(strict.rows[R]) == {**LEGACY_DONOR, 'home_list_visible': True}
    assert COPY not in strict.rows
    # No tombstone: the window can be derived again later.
    assert ('users', 'synthetic', 'deleted_conversations', 'c0') not in strict.rows


def test_undo_never_touches_live_rows_and_requires_its_lease(strict):
    token = convert(strict)
    live = ('users', 'synthetic', 'conversations', 'live')
    strict.rows[live] = {'id': 'live', 'v3_derived': True, 'status': 'completed'}
    assert store.undo_backfill_group('synthetic', token, [], ['live'], run_id=RUN, firestore_client=strict) == (
        'undone',
        0,
        0,
    )
    assert live in strict.rows
    with pytest.raises(store.Conflict, match='lease_lost'):
        store.undo_backfill_group('synthetic', 'stale-token', ['r'], ['c0'], run_id=RUN, firestore_client=strict)


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
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda uid, **kw: False)


@pytest.mark.asyncio
async def test_drain_runs_live_notes_and_settles_each_row(direct, monkeypatch):
    rows = [{'id': 'ok'}, {'id': 'boom'}]
    pending = [rows, []]
    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid, **_: (pending.pop(0), None))
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


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['go', 'pending', None])
async def test_drain_reaches_python_notes_behind_saturated_foreign_page(direct, monkeypatch, engine):
    prefix_ownership = {'finalization_engine': engine, 'finalization_owner_epoch': 1} if engine else {}
    first = [SimpleNamespace(id=f'prefix-{n:03d}', to_dict=lambda: prefix_ownership) for n in range(128)]
    tail = SimpleNamespace(id='tail', to_dict=lambda: {})
    pending = {doc.id for doc in first + [tail]}
    collection = Mock()
    query = collection.where.return_value
    page = query.limit.return_value
    page.stream.side_effect = lambda **_: [doc for doc in first + [tail] if doc.id in pending][:128]
    seek = query.order_by.return_value.start_after
    seek.return_value.limit.return_value.stream.side_effect = lambda **_: [tail] if tail.id in pending else []

    monkeypatch.setattr(store, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(store, 'user_conversations', lambda *_: collection)
    decode = Mock(side_effect=lambda _, doc, *, data: {'id': doc.id, **data})
    monkeypatch.setattr(store, 'decode_row', decode)
    monkeypatch.setattr(leases, 'acquire', lambda *args: 'token')
    monkeypatch.setattr(leases, 'release', lambda *args: None)
    process = AsyncMock()
    monkeypatch.setattr(service, '_process_leased', process)

    def settle(_uid, cid, **_kwargs):
        pending.remove(cid)
        return 'settled'

    monkeypatch.setattr(writers, 'settle_backfill_processing', settle)
    counts = await service.drain_backfill('u', deadline=float('inf'))
    if engine is None:
        # The original full unmarked page still uses only the two existing scans.
        assert counts['processed'] == 128 and counts['remaining'] == 1
        assert page.stream.call_count == 2
        query.order_by.assert_not_called()
    else:
        process.assert_awaited_once_with('u', {'id': 'tail'}, 'token')
        assert counts['processed'] == 1
        assert counts['remaining'] == counts['ownership_blocked'] == 128
        assert seek.call_args_list == [(({'__name__': collection.document.return_value},), {})] * 2
        assert collection.document.call_args_list == [((first[-1].id,), {})] * 2
        decode.assert_called_once_with('u', tail, data={})
        assert pending == {doc.id for doc in first}


def test_expired_backfill_page_never_calls_firestore(monkeypatch):
    client = Mock(side_effect=AssertionError('expired scan acquired a Firestore client'))
    monkeypatch.setattr(store, 'get_firestore_client', client)
    assert store.pending_backfill_processing('u', deadline=0) is None
    client.assert_not_called()


@pytest.mark.asyncio
async def test_expired_drain_leaves_scan_for_continuation(direct, monkeypatch):
    read = Mock(side_effect=AssertionError('expired drain started a scan'))
    monkeypatch.setattr(store, 'pending_backfill_processing', read)
    counts = await service.drain_backfill('u', deadline=0, after='checkpoint')
    assert counts['remaining'] == 1 and counts['scan_pending']
    assert 'scan_after' not in counts  # Keep the durable cursor.
    read.assert_not_called()


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

    def update(self, uid, run_id, *, status=None, partition=None, patch=None, expect=None, expected_drain_seq=None):
        if expect is not None and self.run['status'] not in expect:
            return None
        if expected_drain_seq is not None:
            part = self.run['partitions'][partition[0]]
            assert int(part.get('drain_seq') or 0) == expected_drain_seq
        if status:
            self.run['status'] = status
        if partition:
            index, fields = partition
            self.run['partitions'][index].update(fields)
        self.run.update(patch or {})
        return self.run


def test_late_continuation_cannot_replace_a_newer_cursor(strict):
    uid = 'synthetic'
    path = ('users', uid, runs.COLLECTION, RUN)
    part = {'status': 'notes', 'drain_seq': 2, 'notes_scan_after': 'new'}
    strict.rows[path] = {'status': 'running', 'partitions': [dict(part)]}

    assert (
        runs.update_run(
            uid, RUN, partition=(0, {'notes_scan_after': 'old'}), expected_drain_seq=1, firestore_client=strict
        )
        is None
    )
    assert strict.rows[path]['partitions'] == [part]


@pytest.mark.asyncio
@pytest.mark.parametrize('stale_remaining', [1, 0], ids=['deadline-before-first-page', 'stale-completion'])
async def test_stale_drain_cannot_overwrite_newer_progress(direct, strict, monkeypatch, stale_remaining):
    uid = 'synthetic'
    path = ('users', uid, runs.COLLECTION, RUN)
    strict.rows[path] = {'status': 'running', 'partitions': [{'status': 'notes'}, {'status': 'pending'}]}
    monkeypatch.setattr(runs, 'get_firestore_client', lambda: strict)
    enqueue = Mock()
    monkeypatch.setattr(backfill, 'enqueue_step', enqueue)
    stale_started, finish_stale = asyncio.Event(), asyncio.Event()
    active_started, finish_active = asyncio.Event(), asyncio.Event()
    pending = {'processed': 0, 'failed': 0, 'remaining': 1, 'scan_pending': True}

    async def stale_drain(uid, **kwargs):
        stale_started.set()
        await finish_stale.wait()
        return {**pending, 'remaining': stale_remaining, 'scan_pending': bool(stale_remaining)}

    async def active_drain(uid, **kwargs):
        active_started.set()
        await finish_active.wait()
        return {**pending, 'scan_after': 'third'}

    drain = AsyncMock(side_effect=[pending, {**pending, 'scan_after': 'second'}])
    results = iter([stale_drain, drain, drain, active_drain])

    async def interleaved_drain(uid, **kwargs):
        return await next(results)(uid, **kwargs)

    monkeypatch.setattr(service, 'drain_backfill', interleaved_drain)
    stale = asyncio.create_task(backfill.run_step(uid, RUN, 0, 'drain'))
    await stale_started.wait()
    await backfill.run_step(uid, RUN, 0, 'drain')
    await backfill.run_step(uid, RUN, 0, 'drain')
    active = asyncio.create_task(backfill.run_step(uid, RUN, 0, 'drain'))
    await active_started.wait()
    finish_stale.set()
    stale_result = await stale
    after_stale = deepcopy(strict.rows[path]['partitions'][0])
    finish_active.set()
    active_result = await active

    assert stale_result['outcome'] == 'stopped'
    assert (after_stale['status'], after_stale['drain_seq'], after_stale['notes_scan_after']) == ('notes', 2, 'second')
    assert active_result['outcome'] == 'draining'
    final = strict.rows[path]['partitions'][0]
    assert (final['status'], final['drain_seq'], final['notes_scan_after']) == ('notes', 3, 'third')
    assert [call.args[2:5] for call in enqueue.call_args_list] == [(0, 'drain', seq) for seq in (1, 2, 3)]


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
async def test_a_redelivered_committed_partition_redispatches_a_lost_successor(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['status'] = 'running'
    ledger.run['partitions'][0]['status'] = 'committed'
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=AssertionError('derived twice')))
    assert (await backfill.run_step('u', RUN, 0, 'derive'))['outcome'] == 'committed'
    assert steps == [(1, 'derive', 0)]
    ledger.run['partitions'][1]['status'] = 'notes'
    await backfill.run_step('u', RUN, 0, 'derive')
    assert steps == [(1, 'derive', 0)]


@pytest.mark.asyncio
async def test_a_drain_stopped_by_undo_reports_stopped_and_enqueues_nothing(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['partitions'][0]['status'] = 'notes'

    async def drain(uid, **kw):
        ledger.run['status'] = 'undoing'
        return {'processed': 1, 'failed': 0, 'remaining': 5}

    monkeypatch.setattr(service, 'drain_backfill', drain)
    assert (await backfill.run_step('u', RUN, 0, 'drain'))['outcome'] == 'stopped' and not steps


@pytest.mark.asyncio
async def test_unfinished_notes_continue_on_a_new_named_drain_task(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['partitions'][0]['status'] = 'notes'
    service.drain_backfill.return_value = {'processed': 1, 'failed': 0, 'remaining': 5}
    assert (await backfill.run_step('u', RUN, 0, 'drain'))['outcome'] == 'draining'
    assert steps == [(0, 'drain', 1)] and ledger.run['partitions'][0]['notes_remaining'] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('budget', ['pages', 'deadline'])
async def test_backfill_resumes_its_persisted_cursor_after_scan_budget(direct, monkeypatch, budget):
    uid = 'synthetic'
    ledger = Ledger(1, status='running')
    part = ledger.run['partitions'][0]
    part['status'] = 'notes'
    monkeypatch.setattr(runs, 'get_run', ledger.get)
    monkeypatch.setattr(runs, 'update_run', ledger.update)
    clock = [50.0]
    monkeypatch.setattr(service, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(backfill, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 12345))
    if budget == 'pages':
        monkeypatch.setattr(service, 'BACKFILL_SCAN_MAX_PAGES', 1)
    foreign = {'id': 'foreign', 'finalization_engine': 'go', 'finalization_owner_epoch': 1}
    python = {'id': 'python'}
    owes_python = True
    reads = []

    def read(_uid, *, after, deadline):
        assert clock[0] < deadline
        reads.append(after)
        if after is None:
            if budget == 'deadline':
                clock[0] = deadline
            return [foreign], 'foreign'
        assert after == 'foreign'
        return ([python] if owes_python else []), None

    def settle(_uid, cid, **_):
        nonlocal owes_python
        assert cid == python['id']
        owes_python = False
        return 'settled'

    monkeypatch.setattr(store, 'pending_backfill_processing', read)
    monkeypatch.setattr(leases, 'acquire', lambda *args: 'token')
    monkeypatch.setattr(leases, 'release', lambda *args: None)
    monkeypatch.setattr(writers, 'settle_backfill_processing', settle)
    process = AsyncMock()
    monkeypatch.setattr(service, '_process_leased', process)
    enqueue = Mock()
    monkeypatch.setattr(backfill, 'enqueue_step', enqueue)

    assert await backfill.run_step(uid, RUN, 0, 'drain') == {'outcome': 'draining', 'remaining': 1}
    assert reads == [None]
    assert part['notes_scan_after'] == 'foreign'
    enqueue.assert_called_once_with(uid, RUN, 0, 'drain', 1, 0)
    process.assert_not_awaited()

    if budget == 'pages':
        monkeypatch.setattr(service, 'BACKFILL_SCAN_MAX_PAGES', 2)
    assert await backfill.run_step(uid, RUN, 0, 'drain') == {'outcome': 'draining', 'remaining': 1}
    assert reads == [None, 'foreign', 'foreign']
    assert part['notes_scan_after'] is None
    assert part['status'] == 'notes' and part['notes_processed'] == 1
    process.assert_awaited_once_with(uid, python, 'token')
    assert enqueue.call_args.kwargs == {'schedule_at': 12345 + backfill.OWNERSHIP_RECHECK_SECONDS}


@pytest.mark.asyncio
async def test_foreign_notes_keep_partition_open_until_handback(direct, strict, monkeypatch):
    uid = 'synthetic'
    path = ('users', uid, 'conversations', 'c')
    strict.rows[path] = {
        'id': 'c',
        'v3_backfill_process_pending': True,
        'finalization_engine': 'go',
        'finalization_owner_epoch': 1,
    }
    ledger = Ledger(1, status='running')
    part = ledger.run['partitions'][0]
    part['status'] = 'notes'
    monkeypatch.setattr(runs, 'get_run', ledger.get)
    monkeypatch.setattr(runs, 'update_run', ledger.update)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(
        store,
        'pending_backfill_processing',
        lambda _, **_kwargs: (
            [dict(strict.rows[path])] if strict.rows[path]['v3_backfill_process_pending'] else [],
            None,
        ),
    )
    process = AsyncMock()
    monkeypatch.setattr(service, '_process_leased', process)
    wakes = []
    monkeypatch.setattr(backfill, 'task_base', lambda: 'https://worker.invalid')
    monkeypatch.setattr(backfill, 'enqueue_named_task', lambda *args, **kwargs: wakes.append((args, kwargs)))
    clock = backfill.time.time()

    assert await backfill.run_step(uid, RUN, 0, 'drain') == {'outcome': 'draining', 'remaining': 1}
    assert part['status'] == 'notes' and part['notes_remaining'] == 1
    assert strict.rows[path]['v3_backfill_process_pending']
    process.assert_not_awaited()
    assert len(wakes) == 1
    args, kwargs = wakes.pop()
    assert kwargs['schedule_at'] >= int(clock) + backfill.OWNERSHIP_RECHECK_SECONDS

    strict.rows[path].update(finalization_engine='python', finalization_owner_epoch=2)
    payload = args[3]
    assert await backfill.run_step(payload['uid'], payload['run_id'], payload['partition'], payload['phase']) == {
        'outcome': 'committed',
        'last': True,
    }
    assert part['notes_processed'] == 1 and part['notes_remaining'] == 0
    assert not strict.rows[path]['v3_backfill_process_pending']
    process.assert_awaited_once()
    assert not wakes


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
    monkeypatch.setattr(runs, 'clear_start', lambda uid, run_id: cleared.append(run_id))
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


def _undo_ledger(monkeypatch):
    ledger = Ledger(1, status='committed')
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: ledger.get(*a))
    monkeypatch.setattr(
        runs,
        'update_run',
        lambda *a, **kw: ledger.update(*a[:2], **{k: v for k, v in kw.items() if k != 'firestore_client'}),
    )
    return ledger


def _group_stub(ledger, outcome='undone', calls=None):
    """Stands in for undo_backfill_group, writing the run's undo progress the way its transaction does."""

    def group(uid, token, donors, rows, run_id=None, **kw):
        if calls is not None:
            calls.append((donors, rows))
        if outcome == 'undone':
            progress = ledger.run.setdefault('undo_progress', {})
            progress['donors_restored'] = progress.get('donors_restored', 0) + len(donors)
            progress['rows_removed'] = progress.get('rows_removed', 0) + len(rows)
            progress['removed_ids'] = progress.get('removed_ids', []) + rows
        return outcome, 0, 0

    return group


def _undo_leases(monkeypatch, busy=()):
    events = []
    monkeypatch.setattr(
        leases,
        'acquire',
        lambda uid, key, **kw: events.append(('acquire', key)) or (None if key in busy else 'tok-' + key),
    )
    monkeypatch.setattr(leases, 'renew', lambda *a, **kw: None)
    monkeypatch.setattr(leases, 'release', lambda uid, key, token, **kw: events.append(('release', key)))
    monkeypatch.setattr(leases, 'held', lambda *a, **kw: False)
    monkeypatch.setattr(store, 'deleted_copy_ids', lambda *a, **kw: [])
    return events


def test_undo_works_one_group_per_call_and_refuses_while_notes_are_in_flight(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    events = _undo_leases(monkeypatch)
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}]},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
    ]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: events.append(('enumerate',)) or docs)
    monkeypatch.setattr(leases, 'held', lambda *a, **kw: True)
    assert backfill.undo_run('u', RUN) == {'outcome': 'busy', 'reason': 'notes_in_flight'}
    # The refusal is recorded; 'undoing' stays so in-flight drains stop, and rerunning undo finishes it.
    assert ledger.run['status'] == 'undoing' and ledger.run['undo']['reason'] == 'notes_in_flight'
    assert ('release', 'builder') in events and ('release', store.BACKFILL_LEASE) in events
    monkeypatch.setattr(leases, 'held', lambda *a, **kw: False)
    groups = []
    monkeypatch.setattr(store, 'undo_backfill_group', _group_stub(ledger, calls=groups))
    result = backfill.undo_run('u', RUN)
    assert result == {
        'outcome': 'undone',
        'donors_restored': 1,
        'rows_removed': 1,
        'groups_kept_deleted': 0,
        'donors_kept_deleted': 0,
        'groups_kept_live': 0,
        'donors_kept_live': 0,
        'deleted_during_undo': 0,
        'deleted_during_undo_ids': [],
    }
    # Each group's restore and copy removal is one transaction: never hidden or doubled partway.
    assert groups == [(['d1'], ['c1'])] and ledger.run['status'] == 'undone'


def test_undo_holds_both_builder_leases_before_it_enumerates_the_run(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    events = _undo_leases(monkeypatch, busy={'builder'})
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: pytest.fail('enumerated without both leases'))
    assert backfill.undo_run('u', RUN) == {'outcome': 'busy', 'reason': 'live_builder_in_flight'}
    assert ledger.run['undo']['reason'] == 'live_builder_in_flight'
    assert events == [('acquire', store.BACKFILL_LEASE), ('acquire', 'builder'), ('release', store.BACKFILL_LEASE)]
    events_ok = _undo_leases(monkeypatch)
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: events_ok.append(('enumerate',)) or [])
    backfill.undo_run('u', RUN)
    assert events_ok[:3] == [('acquire', store.BACKFILL_LEASE), ('acquire', 'builder'), ('enumerate',)]
    assert {e for e in events_ok if e[0] == 'release'} == {('release', store.BACKFILL_LEASE), ('release', 'builder')}


def test_undo_groups_link_donors_and_copies_including_deleted_copies():
    claims = lambda *ids: [{'conversation_id': i} for i in ids]  # noqa: E731
    docs = [
        # d1's copy 'gone' was deleted by the owner: only its post-run span still names it.
        {'id': 'd1', 'claims': claims('c1'), 'deleted_spans': [{'conversation_id': 'gone'}]},
        {'id': 'd2', 'claims': claims('c1')},
        {
            'id': 'd3',
            'claims': claims('c2'),
            'deleted_spans': [{'conversation_id': 'old'}],
            'v3_backfill_prior': {'deleted_spans': [{'conversation_id': 'old'}]},
        },
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1', 'd2']},
        {'id': 'c2', 'v3_derived': True, 'v3_recording_ids': ['d3']},
    ]
    groups = sorted(backfill.undo_groups(docs))
    # 'gone' links d1's group but is not read: d1's post-run span already keeps the group.
    assert groups == [(['d1', 'd2'], ['c1']), (['d3'], ['c2'])]


def test_deleted_copy_ids_never_count_against_the_group_read_bound():
    many = [{'conversation_id': f'gone{i}'} for i in range(400)]
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}], 'deleted_spans': many},
        {'id': 'd2', 'v3_backfill_deleted_copies': ['gone0']},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
    ]
    # d2 joins d1 through a shared deleted copy; only the existing copy is read.
    assert backfill.undo_groups(docs) == [(['d1', 'd2'], ['c1'])]


def test_only_a_post_run_deleted_span_counts_as_the_owners_deletion():
    assert store.deleted_after_backfill({'deleted_spans': [{'conversation_id': 'c0'}]})
    prior = {'v3_backfill_prior': {'deleted_spans': [{'conversation_id': 'x'}]}}
    assert not store.deleted_after_backfill({'deleted_spans': [{'conversation_id': 'x'}], **prior})
    # No claim and no new span: its copy never committed (interrupted run) or a re-derive retired it.
    assert not store.deleted_after_backfill({'claims': []})


def _strict_undo(strict, monkeypatch):
    ledger = Ledger(1, status='committed')
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: ledger.get(*a[:2]))
    monkeypatch.setattr(
        runs,
        'update_run',
        lambda *a, **kw: ledger.update(*a[:2], **{k: v for k, v in kw.items() if k != 'firestore_client'}),
    )

    def documents(uid, run_id, **kw):
        return [
            {**v, 'id': k[-1]}
            for k, v in strict.rows.items()
            if k[:3] == ('users', 'synthetic', 'conversations') and v.get('v3_backfill_run') == run_id
        ]

    monkeypatch.setattr(store, 'backfill_run_documents', documents)
    monkeypatch.setattr(store, 'deleted_copy_ids', lambda *a, **kw: [])


def test_undo_never_resurrects_a_donor_whose_copy_the_owner_deleted(strict, monkeypatch):
    token = convert(strict)
    store.leases.release('synthetic', store.BACKFILL_LEASE, token, firestore_client=strict)
    # The owner deletes the backfilled copy in the app: tombstone, then the copy's claim is released.
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    store.release_claims('synthetic', {**strict.rows[COPY]}, firestore_client=strict)
    _strict_undo(strict, monkeypatch)
    result = backfill.undo_run('synthetic', RUN, firestore_client=strict)
    assert result['outcome'] == 'undone_partial' and result['groups_kept_deleted'] == 1
    assert result['donors_restored'] == 0
    assert result['donors_kept_deleted'] == 1
    donor = strict.rows[R]
    # Still a hidden source, never a visible legacy conversation again.
    assert donor['recording'] is True and donor['v3_backfill_run'] == RUN


def test_a_deletion_racing_undo_keeps_the_group_and_hands_owed_notes_to_live(strict):
    token = convert(strict)
    # Delete intent written; the claim release has not run yet (the window undo used to race).
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    strict.rows[COPY] = {**strict.rows[COPY], 'v3_backfill_process_pending': True, 'v3_process_pending': True}
    sibling = ('users', 'synthetic', 'conversations', 'c1')
    strict.rows[sibling] = {**strict.rows[COPY], 'id': 'c1', 'v3_process_pending': False}
    result = store.undo_backfill_group('synthetic', token, ['r'], ['c0', 'c1'], run_id=RUN, firestore_client=strict)
    assert result == ('kept', 1, 0)
    assert strict.rows[R]['recording'] is True and COPY in strict.rows
    # The deleted copy never goes to the notes model; a kept sibling's owed notes move to the live drain.
    assert strict.rows[COPY]['v3_backfill_process_pending'] is False
    assert strict.rows[COPY]['v3_process_pending'] is False
    assert (
        strict.rows[sibling]['v3_backfill_process_pending'] is False
        and strict.rows[sibling]['v3_process_pending'] is True
    )


def test_a_kept_group_clears_the_live_notes_marker_of_a_deleted_copy(strict):
    token = convert(strict)
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    strict.rows[COPY] = {**strict.rows[COPY], 'v3_backfill_process_pending': False, 'v3_process_pending': True}
    assert store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict) == (
        'kept',
        1,
        0,
    )
    assert strict.rows[COPY]['v3_process_pending'] is False


def test_undoing_an_undone_run_reports_the_record_and_changes_nothing(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    events = _undo_leases(monkeypatch)
    ledger.run.update(status='undone_partial', undo={'groups_kept_deleted': 1, 'at': 'then'})
    result = backfill.undo_run('u', RUN)
    assert result == {'groups_kept_deleted': 1, 'outcome': 'undone_partial'}
    assert ledger.run['status'] == 'undone_partial' and not events


def test_undo_keeps_a_copy_a_live_pass_extended_with_live_capture(strict, monkeypatch):
    token = convert(strict)
    # A live pass after the run merged a new recording into the run-tagged copy.
    strict.rows[COPY] = {**strict.rows[COPY], 'v3_recording_ids': ['r', 'live-rec']}
    assert store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict) == (
        'kept_live',
        1,
        0,
    )
    assert COPY in strict.rows and strict.rows[R]['recording'] is True
    store.leases.release('synthetic', store.BACKFILL_LEASE, token, firestore_client=strict)
    _strict_undo(strict, monkeypatch)
    result = backfill.undo_run('synthetic', RUN, firestore_client=strict)
    assert result['outcome'] == 'undone_partial'
    assert result['groups_kept_live'] == 1 and result['donors_kept_live'] == 1 and result['groups_kept_deleted'] == 0


def test_an_interrupted_conversion_with_no_claim_is_restored(strict):
    token = convert(strict)
    strict.rows[R] = {**strict.rows[R], 'claims': []}
    assert store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict) == (
        'undone',
        1,
        1,
    )
    assert stored(strict.rows[R]) == {**LEGACY_DONOR, 'home_list_visible': True}


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
    busy = await route.run_backfill(body, _retry=0)
    assert busy.status_code == 409
    assert json.loads(busy.body) == {'status': 'retry', 'reason': 'locked'}


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


def test_start_markers_live_under_the_owner_so_account_deletion_purges_them():
    written, deleted = [], []

    class Ref:
        def __init__(self, path):
            self.path = path

        def collection(self, name):
            return Ref(self.path + [name])

        def document(self, name):
            return Ref(self.path + [name])

        def set(self, data):
            written.append((self.path, data))

        def delete(self):
            deleted.append(self.path)

    doc = SimpleNamespace(id=RUN, reference=SimpleNamespace(parent=SimpleNamespace(parent=SimpleNamespace(id='u'))))
    client = SimpleNamespace(
        collection=lambda name: Ref([name]),
        collection_group=lambda name: SimpleNamespace(
            limit=lambda n: SimpleNamespace(stream=lambda: [doc] if name == runs.STARTS else [])
        ),
    )
    runs.mark_start('u', RUN, firestore_client=client)
    assert written[0][0] == ['users', 'u', runs.STARTS, RUN] and 'uid' not in written[0][1]
    assert runs.pending_starts(20, firestore_client=client) == [{'uid': 'u', 'run_id': RUN}]
    runs.clear_start('u', RUN, firestore_client=client)
    assert deleted == [['users', 'u', runs.STARTS, RUN]]


def test_operator_refuses_a_new_run_while_one_is_blocked(tmp_path, monkeypatch, capsys):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('synthetic-owner\n')
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [{'run_id': RUN, 'status': 'blocked'}])
    monkeypatch.setattr(store, 'backfill_window_metadata', lambda *a: pytest.fail('planned over a blocked run'))
    # Skipped owners fail the exit code so automation never reads a partial batch as done.
    assert script.main(['run', '--owners-file', str(owners), '--dry-run']) == 1
    assert 'resume or undo it first' in capsys.readouterr().out


def test_undo_and_resume_fail_when_no_owner_has_the_run(tmp_path, monkeypatch):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('synthetic-owner\n')
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: None)
    assert script.main(['undo', '--owners-file', str(owners), '--run', RUN, '--dry-run']) == 1
    assert script.main(['resume', '--owners-file', str(owners), '--run', RUN]) == 1


def test_undo_of_a_rederive_run_names_the_original_run_and_fails(tmp_path, monkeypatch, capsys):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('synthetic-owner\n')
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: {'run_id': RUN, 'mode': 'rederive'})
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: pytest.fail('empty scope printed'))
    assert script.main(['undo', '--owners-file', str(owners), '--run', RUN, '--dry-run']) == 1
    assert 'undo the original run' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_the_drain_stops_once_account_deletion_starts(direct, monkeypatch):
    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid, **_: ([{'id': 'a'}], None))
    fresh = []
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda uid, **kw: fresh.append(kw) or True)
    monkeypatch.setattr(service, '_process_leased', AsyncMock(side_effect=AssertionError('sent a transcript')))
    counts = await service.drain_backfill('u', deadline=float('inf'))
    assert counts['account_deletion'] == 1 and counts['processed'] == 0
    # The ledger still learns what is owed.
    assert counts['remaining'] == 1
    # Read past the negative cache: a marker written seconds ago still stops the drain.
    assert fresh == [{'fresh': True}]


@pytest.mark.asyncio
async def test_a_step_blocks_the_run_when_the_drain_stops_for_account_deletion(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['partitions'][0]['status'] = 'notes'
    service.drain_backfill.return_value = {'processed': 0, 'failed': 0, 'remaining': 0, 'account_deletion': 1}
    assert await backfill.run_step('u', RUN, 0, 'drain') == {'outcome': 'blocked', 'reason': 'account_deletion'}
    assert ledger.run['status'] == 'blocked' and not steps


def test_one_owners_blocked_plan_never_stops_the_others(tmp_path, monkeypatch, capsys):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('owner-one\nowner-two\n')
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])
    planned = []

    def plan(uid, label, *a, **kw):
        if uid == 'owner-one':
            raise store.Conflict('backfill_partition_budget')
        planned.append(label)
        return {}, [], {}

    monkeypatch.setattr(script, 'plan_owner', plan)
    assert script.main(['run', '--owners-file', str(owners), '--dry-run']) == 1
    out = capsys.readouterr().out
    assert 'owner[1] blocked: backfill_partition_budget' in out and planned == ['owner[2]']
    assert 'owner-one' not in out


@pytest.mark.asyncio
async def test_a_row_rechecks_account_deletion_right_before_its_notes_call(direct, monkeypatch):
    rows = [{'id': 'a'}, {'id': 'b'}]
    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid, **_: (rows, None))
    admitted_row = {}

    async def blocking(pool, fn, *args, **kwargs):
        task = asyncio.current_task()
        if fn is leases.acquire:
            admitted_row[task] = args[1]
            return 'token'
        if fn is store.account_deletion_blocks_user_work:
            return admitted_row.get(task) == 'summary-b'
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    released = []
    monkeypatch.setattr(leases, 'release', lambda *a: released.append(a[1]))
    processed = []

    async def process(uid, row, token):
        processed.append(row['id'])

    monkeypatch.setattr(service, '_process_leased', process)
    monkeypatch.setattr(writers, 'settle_backfill_processing', lambda *a, **kw: 'settled')
    counts = await service.drain_backfill('u', deadline=float('inf'), concurrency=2)
    assert processed == ['a'] and counts['account_deletion'] == 1
    assert sorted(released) == ['summary-a', 'summary-b']


@pytest.mark.asyncio
async def test_deletion_between_drain_guard_and_model_dispatch(direct, strict, monkeypatch):
    from utils.conversations import process_conversation as process

    row = legacy(
        'a',
        AT,
        400,
        created_at=AT,
        v3_derived=True,
        backfilled=True,
        v3_backfill_process_pending=True,
        tile_state='done',
        summary_retryable=True,
        v3_process_attempts=1,
    )
    row['v3_process_fingerprint'] = writers.processing_hash(row)
    path = ('users', 'u', 'conversations', 'a')
    strict.rows[path] = dict(row)
    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid, **_: ([row], None))
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(service.models, 'account_deletion_firestore_client', lambda: strict)
    token = leases.acquire('u', 'summary-a', firestore_client=strict)
    monkeypatch.setattr(leases, 'acquire', lambda *a: token)
    released = []
    monkeypatch.setattr(leases, 'release', lambda *a: released.append(a[1]))

    def prepare_notes(*args, **kwargs):
        # The original drain checks have passed and the leased worker has started.
        strict.rows[('account_deletions', 'u')] = {'wipe_status': 'pending'}
        service.models.dispatch_notes_model(lambda: pytest.fail('transcript reached the model'))

    monkeypatch.setattr(process, 'process_conversation', prepare_notes)
    monkeypatch.setattr(
        writers, 'settle_backfill_processing', lambda *a, **kw: pytest.fail('spent a notes retry on deletion')
    )

    counts = await service.drain_backfill('u', deadline=float('inf'))
    assert counts['account_deletion'] == counts['remaining'] == 1
    assert counts['processed'] == counts['failed'] == counts['retry'] == 0
    assert released == ['summary-a']
    assert stored(strict.rows[path]) == {**row, 'v3_process_pending': False}


@pytest.mark.asyncio
async def test_slow_notes_admission_spends_one_backfill_retry(direct, strict, monkeypatch):
    models = service.models
    monkeypatch.setattr(models, 'account_deletion_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid, **_: ([{'id': 'a'}], None))
    monkeypatch.setattr(leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(leases, 'release', lambda *a: None)
    paid_turns = []
    settled = []

    now = 100.0
    monkeypatch.setattr(models, 'monotonic', lambda: now)

    async def paid_turn(cid):
        nonlocal now
        paid_turns.append(cid)
        # Expire the actual asyncio timeout after dispatch without waiting on wall time.
        now += models.BACKFILL_NOTES_BUDGET_SECONDS + 1
        await asyncio.get_running_loop().create_future()
        pytest.fail('the expired provider turn completed')

    async def invoke(cid):
        monkeypatch.setattr(asyncio.get_running_loop(), 'time', lambda: now)
        await models.within_notes_admission(lambda: paid_turn(cid))

    async def process(uid, row, token):
        def dispatch():
            with models.notes_mode(uid, backfilled=True):
                try:
                    models.dispatch_notes_model(lambda: asyncio.run(invoke(row['id'])))
                except models.BackfillNotesAdmissionTimeout:
                    raise
                except Exception as error:
                    pytest.fail(f'unexpected timeout type: {type(error).__name__}')

        await asyncio.to_thread(dispatch)

    def settle(uid, cid, *, failed, max_attempts):
        settled.append((cid, failed))
        return 'retry' if failed else 'settled'

    monkeypatch.setattr(service, '_process_leased', process)
    monkeypatch.setattr(writers, 'settle_backfill_processing', settle)
    counts = await service.drain_backfill('u', deadline=float('inf'))
    assert paid_turns == ['a']
    assert settled == [('a', True)]
    assert counts['processed'] == 0 and counts['retry'] == 1


def test_an_oversized_undo_group_is_refused_whole(strict):
    # Reads per copy are three (row, tombstone, notes lease): 167 copies plus 2 exceed 500.
    with pytest.raises(store.Conflict, match='undo_group_too_large'):
        store.undo_backfill_group(
            'synthetic', 'token', [], [f'c{i}' for i in range(167)], run_id=RUN, firestore_client=strict
        )


@pytest.mark.asyncio
async def test_a_failed_deletion_read_releases_the_rows_summary_lease(direct, monkeypatch):
    checks = iter([False])

    def marker(uid, **kw):
        try:
            return next(checks)
        except StopIteration:
            raise RuntimeError('marker authority unavailable') from None

    monkeypatch.setattr(store, 'pending_backfill_processing', lambda uid, **_: ([{'id': 'a'}], None))
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', marker)
    monkeypatch.setattr(leases, 'acquire', lambda *a: 'token')
    released = []
    monkeypatch.setattr(leases, 'release', lambda *a: released.append(a[1]))
    monkeypatch.setattr(service, '_process_leased', AsyncMock(side_effect=AssertionError('processed')))
    with pytest.raises(RuntimeError):
        await service.drain_backfill('u', deadline=float('inf'))
    assert released == ['summary-a']


@pytest.mark.asyncio
async def test_an_account_deletion_block_keeps_the_chunks_notes_counts(chain, monkeypatch):
    ledger, steps = chain
    ledger.run['partitions'][0].update(status='notes', notes_processed=2)
    ledger.run['partitions'][0]['notes_remaining'] = 9
    service.drain_backfill.return_value = {'processed': 3, 'failed': 1, 'remaining': 2, 'account_deletion': 1}
    await backfill.run_step('u', RUN, 0, 'drain')
    part = ledger.run['partitions'][0]
    assert part['status'] == 'blocked' and part['notes_processed'] == 5 and part['notes_failed'] == 1
    assert part['notes_remaining'] == 2


def test_a_blocked_owner_still_fails_the_exit_code_with_no_wait(tmp_path, monkeypatch):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('owner-one\nowner-two\n')
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])

    def plan(uid, label, *a, **kw):
        if uid == 'owner-one':
            raise store.Conflict('backfill_partition_budget')
        return {}, [], {}

    monkeypatch.setattr(script, 'plan_owner', plan)
    monkeypatch.setattr(backfill, 'create_run', lambda *a, **kw: 'run-x')
    assert script.main(['run', '--owners-file', str(owners), '--no-wait']) == 1


def test_a_failed_undo_group_is_recorded_and_leaves_the_run_resumable(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    _undo_leases(monkeypatch)
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}]},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
    ]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: docs)

    def fail(*a, **kw):
        raise store.Conflict('lease_lost')

    monkeypatch.setattr(store, 'undo_backfill_group', fail)
    ledger.run['undo_progress'] = {'removed_ids': ['c0']}
    monkeypatch.setattr(store, 'deleted_copy_ids', lambda uid, ids, **kw: list(ids))
    result = backfill.undo_run('u', RUN)
    assert result['outcome'] == 'error' and result['reason'] == 'lease_lost'
    # Copies removed before the failure are still checked for a racing delete.
    assert ledger.run['undo']['deleted_during_undo_ids'] == ['c0']
    assert ledger.run['status'] == 'undoing' and ledger.run['undo']['reason'] == 'lease_lost'


def test_a_lease_lost_on_renew_is_recorded_like_a_failed_group(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    _undo_leases(monkeypatch)
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}]},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
    ]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: docs)
    monkeypatch.setattr(store, 'undo_backfill_group', lambda *a, **kw: ('undone', 1, 1))

    def lost(*a, **kw):
        raise store.Conflict('lease_lost')

    monkeypatch.setattr(leases, 'renew', lost)
    result = backfill.undo_run('u', RUN)
    assert result['outcome'] == 'error' and result['reason'] == 'lease_lost'
    assert ledger.run['status'] == 'undoing' and ledger.run['undo']['reason'] == 'lease_lost'


def test_an_existing_run_is_a_typed_blocked_owner(tmp_path, monkeypatch, capsys):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('owner-one\nowner-two\n')
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])
    monkeypatch.setattr(script, 'plan_owner', lambda *a, **kw: ({}, [], {}))
    monkeypatch.setattr(runs, 'create_run', lambda *a, **kw: False)
    assert issubclass(backfill.BackfillRunExists, ValueError)
    assert script.main(['run', '--owners-file', str(owners), '--no-wait']) == 1
    assert capsys.readouterr().out.count('blocked: backfill_run_exists') == 2


def test_undo_refuses_a_group_whose_copy_took_a_notes_lease_after_the_first_check(strict):
    token = convert(strict)
    strict.rows[('users', 'synthetic', 'conversation_v3_leases', 'summary-c0')] = {
        'token': 'drain',
        'until': datetime.now(timezone.utc) + timedelta(minutes=4),
    }
    with pytest.raises(store.Conflict, match='notes_in_flight'):
        store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict)
    assert strict.rows[R]['recording'] is True and COPY in strict.rows


def test_a_rerun_undo_keeps_the_totals_of_groups_already_undone(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    ledger.run.update(
        status='undoing',
        undo={'groups_kept_deleted': 1, 'donors_kept_deleted': 2},
        undo_progress={'donors_restored': 4, 'rows_removed': 3, 'removed_ids': ['old']},
    )
    _undo_leases(monkeypatch)
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}]},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
    ]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: docs)
    monkeypatch.setattr(store, 'undo_backfill_group', _group_stub(ledger))
    checked = []
    monkeypatch.setattr(store, 'deleted_copy_ids', lambda uid, ids, **kw: checked.append(ids) or [])
    result = backfill.undo_run('u', RUN)
    assert result['donors_restored'] == 5 and result['rows_removed'] == 4
    # Every attempt's removed copies are checked for a racing delete, not only this attempt's.
    assert checked == [['old', 'c1']]
    assert ledger.run['undo']['donors_restored'] == 5
    # Kept groups are still in the run's documents and recounted, never carried twice.
    assert result['groups_kept_deleted'] == 0 and result['donors_kept_deleted'] == 0


def test_a_refused_undo_keeps_the_earlier_totals(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    ledger.run['undo'] = {'donors_restored': 4}
    _undo_leases(monkeypatch, busy={'builder'})
    backfill.undo_run('u', RUN)
    assert ledger.run['undo']['donors_restored'] == 4 and ledger.run['undo']['reason'] == 'live_builder_in_flight'


def test_the_loader_reads_the_deletion_marker_on_its_own_data_plane(loader, monkeypatch):
    calls = []
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda uid, **kw: calls.append(kw) or False)
    store.load_derive('u', since=AT, until=AT + timedelta(hours=1), run_id=RUN, firestore_client=Client({}))
    # Never the conversations client it was handed (the marker lives on the data plane), and fresh,
    # since this load gates sending the transcript to the outline model.
    assert calls == [{'fresh': True}]


def test_undo_lists_deletes_that_raced_it_and_ends_partial(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    _undo_leases(monkeypatch)
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}]},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
        {'id': 'd2', 'claims': [{'conversation_id': 'c2'}]},
        {'id': 'c2', 'v3_derived': True, 'v3_recording_ids': ['d2']},
    ]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: docs)
    monkeypatch.setattr(store, 'undo_backfill_group', _group_stub(ledger))
    monkeypatch.setattr(store, 'deleted_copy_ids', lambda uid, ids, **kw: [i for i in ids if i == 'c2'])
    result = backfill.undo_run('u', RUN)
    assert result['outcome'] == 'undone_partial' and ledger.run['status'] == 'undone_partial'
    assert result['deleted_during_undo'] == 1 and ledger.run['undo']['deleted_during_undo_ids'] == ['c2']


def test_the_group_transaction_records_undo_progress_in_the_ledger(strict):
    token = convert(strict)
    ledger = ('users', 'synthetic', runs.COLLECTION, RUN)
    strict.rows[ledger] = {'run_id': RUN, 'status': 'undoing'}
    result = store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict)
    assert result == ('undone', 1, 1)
    assert strict.rows[ledger]['undo_progress'] == {'donors_restored': 1, 'rows_removed': 1, 'removed_ids': ['c0']}


def test_a_deleted_copy_fully_covered_by_another_claim_still_keeps_its_group(strict):
    convert(strict)
    # A second copy claims the same interval, so deleting c0 leaves no uncovered span.
    donor = strict.rows[R]
    strict.rows[R] = {**donor, 'claims': donor['claims'] + [{**donor['claims'][0], 'conversation_id': 'c9'}]}
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    store.release_claims('synthetic', {**strict.rows[COPY]}, firestore_client=strict)
    assert strict.rows[R]['v3_backfill_deleted_copies'] == ['c0']
    assert store.deleted_after_backfill(strict.rows[R])
    # The donor's recorded deleted copy keeps the group; c0 itself is not read again.
    groups = backfill.undo_groups([{**strict.rows[R], 'id': 'r'}])
    assert groups == [(['r'], ['c9'])]


def test_an_owner_skipped_for_an_active_run_fails_the_exit_code(tmp_path, monkeypatch):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('owner-one\nowner-two\n')
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [{'status': 'running'}] if uid == 'owner-one' else [])
    monkeypatch.setattr(script, 'plan_owner', lambda *a, **kw: ({}, [], {}))
    assert script.main(['run', '--owners-file', str(owners), '--dry-run']) == 1


@pytest.mark.asyncio
async def test_a_resume_keeps_going_when_a_converted_donor_is_unclaimed(builder, monkeypatch, no_evidence):
    converted = {
        **legacy('b', AT + timedelta(hours=2), 0),
        'transcript_segments': [],
        'recording': True,
        '_v3_derive': True,
        '_v3_backfill_run': RUN,
    }
    sources = {'a': as_derive(legacy('a', AT, 400)), 'b': converted}
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: (sources, {}, []))
    monkeypatch.setattr(service.models, 'outline', lambda *a: SCENARIOS['long_visible'][1])
    committed = []
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: committed.append(kw))
    outcome = await service.reconcile('u', derive=True, since=AT, until=AT + timedelta(days=1), run_id=RUN)
    # A resume retires nothing, so the donor keeps its existing copy: no block.
    assert outcome == 'committed' and committed


def test_an_unexpected_plan_error_is_not_reported_as_a_blocked_owner(tmp_path, monkeypatch):
    from scripts import conversations_v3_backfill as script

    owners = tmp_path / 'owners.txt'
    owners.write_text('owner-one\n')
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])

    def plan(*a, **kw):
        raise ValueError('bug')

    monkeypatch.setattr(script, 'plan_owner', plan)
    with pytest.raises(ValueError, match='bug'):
        script.main(['run', '--owners-file', str(owners), '--dry-run'])


@pytest.mark.parametrize('foreign_target', [R, COPY])
def test_undo_keeps_a_group_linked_to_another_run(strict, foreign_target):
    token = convert(strict)
    strict.rows[foreign_target]['v3_backfill_run'] = 'another-run'
    strict.rows[COPY]['v3_backfill_process_pending'] = True
    foreign_before = deepcopy(strict.rows[foreign_target])
    result = store.undo_backfill_group('synthetic', token, ['r'], ['c0'], run_id=RUN, firestore_client=strict)
    assert result == ('kept_live', int(foreign_target != R), 0)
    assert strict.rows[foreign_target] == foreign_before
    assert strict.rows[R]['recording'] is True
    assert strict.rows[COPY]['v3_backfill_process_pending'] is (foreign_target == COPY)


@pytest.mark.parametrize('marker_state', ['absent', 'cancelled'])
@pytest.mark.parametrize('grace', [False, True], ids=['immediate', 'grace'])
def test_backfill_notes_admission_orders_on_firestore_emulator(monkeypatch, marker_state, grace):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '').rpartition(':')[0]
    if host not in ('127.0.0.1', 'localhost', '[::1]'):
        pytest.skip('requires a loopback Firestore emulator')

    from google.cloud.firestore import Client
    from database import account_deletion_grace, users

    client = Client(project='demo-backfill-notes')
    uid = uuid4().hex
    models = service.models
    marker = models.account_deletion_document(uid, firestore_client=client)
    monkeypatch.setattr(models, 'account_deletion_firestore_client', lambda: client)
    monkeypatch.setenv('BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED', 'off')

    def reset_marker():
        if marker_state == 'absent':
            marker.delete()
        else:
            marker.set({'wipe_status': 'cancelled'})

    def delete_account():
        if grace:
            return account_deletion_grace._mark_user_deletion_grace_intent_txn(
                client.transaction(), marker, 'job', datetime.now(timezone.utc) + timedelta(days=1)
            )
        return users._mark_user_deletion_wipe_intent_txn(client.transaction(), marker, 'job')

    def dispatch(invoke):
        with models.notes_mode(uid, backfilled=True):
            return models.dispatch_notes_model(invoke)

    try:
        reset_marker()
        delete_account()
        with pytest.raises(models.BackfillNotesDeletionBlocked):
            dispatch(lambda: pytest.fail('deletion won admission but the model was called'))

        reset_marker()
        model_entered = Event()
        release_model = Event()
        deletion_started = Event()

        def invoke():
            model_entered.set()
            assert release_model.wait(5)
            return 'notes'

        def concurrent_delete():
            deletion_started.set()
            return delete_account()

        with ThreadPoolExecutor(max_workers=2) as pool:
            notes = pool.submit(dispatch, invoke)
            try:
                assert model_entered.wait(5)
                deletion = pool.submit(concurrent_delete)
                assert deletion_started.wait(5)
                # The intent writer may read the marker, but cannot commit while admission locks it.
                try:
                    deletion.result(timeout=0.25)
                except TimeoutError:
                    pass
                else:
                    pytest.fail('deletion committed while notes held the admission fence')
            finally:
                release_model.set()
            assert notes.result(timeout=5) == 'notes'
            deletion.result(timeout=10)
        with pytest.raises(models.BackfillNotesDeletionBlocked):
            dispatch(lambda: pytest.fail('a later model call was admitted during deletion'))
    finally:
        marker.delete()
        client.close()
