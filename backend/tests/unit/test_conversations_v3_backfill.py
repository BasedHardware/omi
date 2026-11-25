"""Per-owner v3 backfill/repair: live parity, partitions, reversible conversion, task chain, operator.

Synthetic data only. The parity tests feed the same sources through a live builder pass and a
derive pass and require identical windows, Home decisions and notes inputs; the only differences
allowed are the backfill stamps and the notes marker the backfill drains itself.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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
    for index, words in enumerate((19, 20, 299, 300)):
        cid = f'capture-{index}'
        row = legacy(cid, AT + timedelta(minutes=10 * index), words)
        row['transcript_segments'][0]['text'] = letter * words
        sources[cid] = as_derive(row)
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: (sources, {}, []))
    estimate = backfill.estimate_partition(
        'u', {'since': AT, 'until': AT + timedelta(days=1)}, RUN, now=AT + timedelta(days=2)
    )
    assert estimate['words'] == 19 + 20 + 299 + 300
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

    def decode(uid, snapshot, **_kwargs):
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
    monkeypatch.setattr(store, 'recording_input', lambda uid, snapshot, **_kwargs: {'_v3_unreadable': True})
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
    assert store.restore_backfill_donors('synthetic', token, ['r'], firestore_client=strict) == (1, [])
    assert store.delete_backfill_rows('synthetic', token, ['c0'], firestore_client=strict) == 1
    assert stored(strict.rows[R]) == {**LEGACY_DONOR, 'home_list_visible': True}
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

    client = object()
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'user_conversations', lambda *_: collection)
    decode = Mock(side_effect=lambda _, doc, *, data, **_kwargs: {'id': doc.id, **data})
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
        decode.assert_called_once_with('u', tail, data={}, firestore_client=client)
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
    return events


def test_undo_restores_donors_before_removing_copies_and_waits_for_notes(monkeypatch):
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
    order = []
    monkeypatch.setattr(
        store, 'restore_backfill_donors', lambda uid, token, ids, **kw: order.append(('restore', ids)) or (1, [])
    )
    monkeypatch.setattr(store, 'delete_backfill_rows', lambda uid, token, ids, **kw: order.append(('delete', ids)) or 1)
    result = backfill.undo_run('u', RUN)
    assert result == {
        'outcome': 'undone',
        'donors_restored': 1,
        'rows_removed': 1,
        'donors_kept_deleted': 0,
        'rows_kept_deleted': 0,
    }
    assert order == [('restore', ['d1']), ('delete', ['c1'])] and ledger.run['status'] == 'undone'


def test_undo_holds_both_builder_leases_before_it_enumerates_the_run(monkeypatch):
    ledger = _undo_ledger(monkeypatch)
    events = _undo_leases(monkeypatch, busy={'builder'})
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: pytest.fail('enumerated without both leases'))
    assert backfill.undo_run('u', RUN) == {'outcome': 'busy', 'reason': 'live_builder_in_flight'}
    assert ledger.run['undo']['reason'] == 'live_builder_in_flight'
    assert events == [('acquire', store.BACKFILL_LEASE), ('acquire', 'builder'), ('release', store.BACKFILL_LEASE)]
    events.clear()
    events_ok = _undo_leases(monkeypatch)
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: events_ok.append(('enumerate',)) or [])
    backfill.undo_run('u', RUN)
    assert events_ok[:3] == [('acquire', store.BACKFILL_LEASE), ('acquire', 'builder'), ('enumerate',)]
    assert {e for e in events_ok if e[0] == 'release'} == {('release', store.BACKFILL_LEASE), ('release', 'builder')}


def test_undo_keeps_what_the_owner_deleted_and_every_copy_it_shares():
    claims = lambda *ids: [{'conversation_id': i} for i in ids]  # noqa: E731
    donors = [
        {'id': 'd1', 'claims': [], 'deleted_spans': [{'conversation_id': 'gone'}]},
        {'id': 'd2', 'claims': claims('c1')},
        {'id': 'd3', 'claims': claims('c1', 'c2')},
        {'id': 'd4', 'claims': claims('c3')},
    ]
    derived = [
        {'id': 'c1', 'v3_recording_ids': ['d1', 'd2', 'd3']},
        {'id': 'c2', 'v3_recording_ids': ['d3']},
        {'id': 'c3', 'v3_recording_ids': ['d4']},
    ]
    assert backfill._kept_by_deletion(donors, derived, {'d1'}) == ({'d1', 'd2', 'd3'}, {'c1', 'c2'})
    assert backfill._kept_by_deletion(donors, derived, set()) == (set(), set())
    assert store.deleted_after_backfill(donors[0]) and not store.deleted_after_backfill(donors[1])
    # A span the donor already had before the run is not the owner's post-backfill deletion.
    old = {'id': 'd5', 'claims': claims('c4'), 'deleted_spans': [{'conversation_id': 'x'}]}
    assert not store.deleted_after_backfill({**old, 'v3_backfill_prior': {'deleted_spans': [{'conversation_id': 'x'}]}})


def test_undo_never_resurrects_a_donor_whose_copy_the_owner_deleted(strict, monkeypatch):
    token = convert(strict)
    store.leases.release('synthetic', store.BACKFILL_LEASE, token, firestore_client=strict)
    # The owner deletes the backfilled copy in the app: tombstone, then the copy's claim is released.
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    store.release_claims('synthetic', {**strict.rows[COPY]}, firestore_client=strict)
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
    result = backfill.undo_run('synthetic', RUN, firestore_client=strict)
    assert result['outcome'] == 'undone' and result['donors_kept_deleted'] == 1 and result['donors_restored'] == 0
    donor = strict.rows[R]
    # Still a hidden source, never a visible legacy conversation again.
    assert donor['recording'] is True and donor['v3_backfill_run'] == RUN


def test_restore_keeps_a_donor_deleted_while_undo_runs(strict):
    token = convert(strict)
    strict.rows[R] = {**strict.rows[R], 'claims': []}
    assert store.restore_backfill_donors('synthetic', token, ['r'], firestore_client=strict) == (0, ['r'])
    assert strict.rows[R]['recording'] is True


def test_undo_recomputes_what_it_keeps_when_a_deletion_races_it(monkeypatch):
    _undo_ledger(monkeypatch)
    _undo_leases(monkeypatch)
    docs = [
        {'id': 'd1', 'claims': [{'conversation_id': 'c1'}]},
        {'id': 'c1', 'v3_derived': True, 'v3_recording_ids': ['d1']},
    ]
    monkeypatch.setattr(store, 'backfill_run_documents', lambda *a, **kw: docs)
    monkeypatch.setattr(store, 'restore_backfill_donors', lambda uid, token, ids, **kw: (0, ['d1']))
    monkeypatch.setattr(store, 'delete_backfill_rows', lambda *a, **kw: pytest.fail('removed a copy of a kept donor'))
    result = backfill.undo_run('u', RUN)
    assert result['donors_kept_deleted'] == 1 and result['rows_kept_deleted'] == 1 and result['rows_removed'] == 0


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
    assert script.main(['run', '--owners-file', str(owners), '--dry-run']) == 0
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
