"""Synthetic older-data recall, sampling and cooldown contracts."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from types import SimpleNamespace
import random
import string
from bisect import bisect_left
from collections import Counter
from uuid import UUID
import pytest

from config.dream_agent import Caps
from database import dream_history, dream_store
from tests.support.dream_firestore import DreamFirestore
from utils import dream_cleanup as cleanup, dream_reads, dream_prompt, dream_context
from utils.dream_context import EvidenceRecords, add_context

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=60)


def test_problem_signals_and_review_cooldown():
    pool = {
        'action_items/task': {'created_at': OLD, 'description': 'Replace synthetic gears'},
        'people/a': {'created_at': OLD, 'name': 'Mira Holloway'},
        'people/b': {'created_at': OLD, 'name': 'Mira Holoway'},
        'memory_items/a': {'created_at': OLD, 'content': 'Prefers blue synthetic gears', 'visibility': 'private'},
        'memory_items/b': {'created_at': OLD, 'content': 'Prefers blue synthetic gear', 'visibility': 'private'},
        'conversations/a': {'created_at': OLD, 'transcript_segments': [{'text': 'synthetic discussion ' * 30}]},
    }
    assert [cleanup.problem_score(ref, row, pool, NOW) for ref, row in pool.items()] == [2, 3, 3, 3, 3, 2]
    assert cleanup.choose_weighted(pool, {ref: NOW for ref in pool}, NOW, random.Random(1)) is None
    assert cleanup.choose_weighted(pool, {}, NOW, random.Random(1)) in pool
    assert not cleanup.eligible_seed(pool['people/a'], 'malformed', NOW)
    assert cleanup.eligible_seed(pool['people/a'], NOW - timedelta(days=30), NOW)
    pool['memory_items/b']['visibility'] = 'public'
    assert cleanup.problem_score('memory_items/a', pool['memory_items/a'], pool, NOW) == 0


def test_weight_is_problem_times_staleness():
    pool = {'action_items/a': {'created_at': OLD}, 'action_items/b': {'created_at': NOW - timedelta(days=15)}}
    rng = Mock()
    rng.choices.return_value = ['action_items/a']
    cleanup.choose_weighted(pool, {}, NOW, rng)
    assert rng.choices.call_args.kwargs['weights'] == [120, 30]


def test_pinned_people_never_seed_or_partner_cleanup():
    pool = {
        'people/a': {'created_at': OLD, 'name': 'Mira Holloway', 'pinned': True},
        'people/b': {'created_at': OLD, 'name': 'Mira Holoway'},
    }
    assert not cleanup.eligible_seed(pool['people/a'], None, NOW)
    assert all(cleanup.problem_score(ref, row, pool, NOW) == 0 for ref, row in pool.items())


def test_review_cooldowns_use_one_bounded_batch():
    refs = ['people/a', 'people/b']

    def get_all(documents, *, timeout):
        assert timeout == 3
        assert len(documents) == 2
        return [
            SimpleNamespace(id=documents[1].id, to_dict=lambda: {'last_reviewed_at': NOW}),
            SimpleNamespace(id=documents[0].id, to_dict=lambda: None),
        ]

    db = DreamFirestore()
    db.get_all = get_all
    assert dream_history.review_states('synthetic', refs, firestore_client=db) == {
        'people/a': {},
        'people/b': {'last_reviewed_at': NOW},
    }
    assert dream_history.review_states('synthetic', [], firestore_client=db) == {}


def test_count_weighted_sample_includes_every_collection(monkeypatch):
    counts = dict(zip(dream_history.COLLECTIONS, [2, 1, 3, 2]))
    monkeypatch.setattr(dream_history, 'history_count', lambda uid, col: counts[col])
    monkeypatch.setattr(dream_history, 'history_from_key', lambda uid, col, key: 'picked')
    refs = []
    for rank in range(8):
        rng = Mock()
        rng.randrange.return_value = rank
        rng.getrandbits.return_value = 0
        rng.choice.return_value = '0'
        refs.append(cleanup.uniform_ref('synthetic', rng))
    assert refs == [
        'conversations/picked',
        'conversations/picked',
        'action_items/picked',
        'people/picked',
        'people/picked',
        'people/picked',
        'memory_items/picked',
        'memory_items/picked',
    ]


@pytest.mark.parametrize('collection', ['memory_items', 'action_items', 'conversations', 'people'])
def test_random_successor_distribution_covers_real_id_namespace(monkeypatch, collection):
    if collection == 'action_items':
        keys = sorted(char + 'm' * 19 for char in string.ascii_letters + string.digits)
    elif collection == 'memory_items':
        keys = [f'mem_{char}' + '8' * 31 for char in '0123456789abcdef']
    else:
        keys = [str(UUID(int=(i << 124) | int('8' * 31, 16), version=4)) for i in range(16)]
    monkeypatch.setattr(dream_history, 'history_count', lambda uid, col: len(keys) if col == collection else 0)

    def successor(uid, col, pivot):
        assert col == collection
        if col == 'memory_items':
            assert pivot.startswith('mem_') and len(pivot) == 36
            int(pivot[4:], 16)
        elif col == 'action_items':
            assert len(pivot) == 20 and set(pivot) <= set(string.ascii_letters + string.digits)
        else:
            assert UUID(pivot).version == 4
        return keys[bisect_left(keys, pivot) % len(keys)]

    monkeypatch.setattr(dream_history, 'history_from_key', successor)
    rng = random.Random(827)
    draws = 6200
    counts = Counter(cleanup.uniform_ref('synthetic', rng).split('/', 1)[1] for _ in range(draws))
    assert set(counts) == set(keys)
    # Balanced synthetic gaps expose namespace collapse, without claiming that
    # arbitrary real document gaps are an unbiased per-document sample.
    expected = draws / len(keys)
    assert all(0.5 * expected < count < 1.5 * expected for count in counts.values())


@pytest.mark.parametrize('random_share', ['0', '1'])
def test_cleanup_deferral_expires_at_utc_midnight_without_hydration(monkeypatch, random_share):
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', random_share)
    monkeypatch.setattr(dream_history, 'history_page', lambda *a, **k: ['a'])
    monkeypatch.setattr(cleanup, 'uniform_ref', lambda *a: 'action_items/a')
    midnight = NOW + timedelta(days=1)
    monkeypatch.setattr(dream_history, 'review_states', lambda *a: {'action_items/a': {'deferred_until': midnight}})
    loaded = []

    def read(uid, ref):
        loaded.append(ref)
        return {'created_at': OLD, 'description': 'Synthetic task'}

    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'action_items'
    rng.choices.return_value = ['action_items/a']
    lease = {'started_at': midnight - timedelta(microseconds=1), 'cleanup_selected': True}
    assert not cleanup.add_seed('synthetic', EvidenceRecords(), lease, Caps(), [], read_record=read, rng=rng)
    assert loaded == []
    lease['started_at'] = midnight
    result = cleanup.add_seed('synthetic', EvidenceRecords(), lease, Caps(), [], read_record=read, rng=rng)
    assert result.targets == {'action_items/a'} and loaded == ['action_items/a']


def test_seeded_cap_deferral_is_persisted_without_review_stamp(monkeypatch):
    uid = 'synthetic-seed-defer'
    db = DreamFirestore()
    db.rows[('users', uid)] = {}
    db.rows[('dream_users', uid)] = {'score': 0, 'watermark': OLD}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    lease = dream_store.acquire(uid, Caps(), now=NOW, firestore_client=db)
    dream_store.finish(
        uid, lease, {}, success=True, deferred={'people/a'}, reviewed={'people/a'}, now=NOW, firestore_client=db
    )
    state = db.rows[('dream_users', uid, 'reviews', dream_history.review_id('people/a'))]
    assert state == {'deferred_until': NOW + timedelta(days=1)}


def test_seed_duplicate_operands_and_context_roles(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '0')
    monkeypatch.setattr(dream_history, 'history_page', lambda *args, **kwargs: ['a', 'b'])
    monkeypatch.setattr(dream_history, 'review_states', lambda *args: {})
    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'people'
    rng.choices.return_value = ['people/a']
    records = cleanup.add_seed(
        'synthetic',
        EvidenceRecords(),
        {'started_at': NOW},
        Caps(),
        [],
        read_record=lambda uid, ref: {'created_at': OLD, 'name': 'Mira Holloway'},
        rng=rng,
    )
    assert records.targets == {'people/a', 'people/b'}
    assert records.target_sources == {'people/a': 'seeded', 'people/b': 'seeded'}
    combined = add_context(records, [('screen/context', {'text': 'synthetic'}, 'temporal')], Caps())
    assert combined.targets == records.targets
    assert combined.target_sources == records.target_sources
    assert combined.cleanup_cursor == {'people': 'b'}


def test_random_seed_rejected_without_resampling_and_budget_defers(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '1')
    pick = Mock(return_value='action_items/a')
    monkeypatch.setattr(cleanup, 'uniform_ref', pick)
    monkeypatch.setattr(dream_history, 'review_states', lambda *args: {'action_items/a': {'last_reviewed_at': NOW}})
    records = EvidenceRecords()
    assert (
        cleanup.add_seed(
            'synthetic',
            records,
            {'started_at': NOW},
            Caps(),
            [],
            read_record=lambda *args: {'created_at': OLD},
            rng=random.Random(1),
        )
        is records
    )
    pick.assert_called_once()
    monkeypatch.setattr(dream_history, 'review_states', lambda *args: {})
    monkeypatch.setattr(cleanup, 'fits_pass', lambda *args: False)
    assert (
        cleanup.add_seed(
            'synthetic',
            records,
            {'started_at': NOW},
            Caps(),
            [],
            read_record=lambda *args: {'created_at': OLD},
            rng=random.Random(1),
        )
        is records
    )


def test_success_review_metadata_idle_admission_and_failure_fence(monkeypatch):
    uid = 'synthetic-cleanup'
    db = DreamFirestore()
    db.rows[('users', uid)] = {}
    db.rows[('dream_users', uid)] = {'score': 0, 'watermark': OLD}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    lease = dream_store.acquire(uid, Caps(), now=NOW, firestore_client=db)
    assert lease is not None
    dream_store.finish(
        uid, lease, {}, success=True, reviewed=['people/a'], cleanup_cursor={'people': 'a'}, firestore_client=db
    )
    review = ('dream_users', uid, 'reviews', dream_history.review_id('people/a'))
    assert db.rows[review]['last_reviewed_at'] == NOW
    assert db.rows[('dream_users', uid)]['last_pass_at'] == NOW
    assert dream_store.acquire(uid, Caps(), now=NOW, firestore_client=db) is None
    lease = dream_store.acquire(uid, Caps(), now=NOW + timedelta(hours=1), firestore_client=db)
    dream_store.finish(
        uid, lease, {}, success=False, reviewed=['people/a'], cleanup_cursor={'people': 'b'}, firestore_client=db
    )
    assert db.rows[review]['last_reviewed_at'] == NOW
    assert db.rows[('dream_users', uid)]['cleanup_cursor'] == {'people': 'a'}


def test_duplicate_seed_preserves_existing_dirty_partner_source(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '0')
    monkeypatch.setattr(dream_history, 'history_page', lambda *args, **kwargs: ['a', 'b'])
    monkeypatch.setattr(dream_history, 'review_states', lambda *args: {})
    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'people'
    rng.choices.return_value = ['people/a']
    dirty = EvidenceRecords({'people/b': {'created_at': OLD, 'name': 'Mira Holloway'}})
    records = cleanup.add_seed(
        'synthetic',
        dirty,
        {'started_at': NOW},
        Caps(),
        [],
        read_record=lambda uid, ref: {'created_at': OLD, 'name': 'Mira Holloway'},
        rng=rng,
    )
    assert records.targets == {'people/a', 'people/b'}
    assert records.target_sources == {'people/a': 'seeded', 'people/b': 'dirty'}


def test_idle_coin_and_empty_selection_stamp_attempt_without_run_history(monkeypatch):
    uid = 'synthetic-idle'
    db = DreamFirestore()
    db.rows[('users', uid)] = {}
    db.rows[('dream_users', uid)] = {'score': 0, 'watermark': OLD}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0.1')
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    rng = Mock()
    rng.random.return_value = 0.9
    assert dream_store.acquire(uid, Caps(), now=NOW, rng=rng, firestore_client=db) is None
    assert db.rows[('dream_users', uid)]['last_attempt_at'] == NOW
    assert not any('dream_runs' in key for key in db.rows)
    assert ('dream_spend', NOW.date().isoformat()) not in db.rows
    rng.random.return_value = 0
    assert dream_store.acquire(uid, Caps(), now=NOW + timedelta(minutes=30), rng=rng, firestore_client=db) is None
    lease = dream_store.acquire(uid, Caps(), now=NOW + timedelta(hours=1), rng=rng, firestore_client=db)
    dream_store.finish(uid, lease, {'reason': 'idle'}, success=True, refund=True, firestore_client=db)
    assert db.rows[('dream_users', uid)]['passes'] == 0
    assert not any('dream_runs' in key for key in db.rows)
    assert (
        dream_store.acquire(uid, Caps(), now=NOW + timedelta(hours=1, minutes=10), rng=rng, firestore_client=db) is None
    )


def test_random_key_queries_are_bounded_and_wrap_without_offsets():
    from tests.support.firestore_shape_recorder import RecordingFirestore

    db = RecordingFirestore()
    db.queue_results([])
    db.queue_results([db.snapshot('users/synthetic/people/first', {})])
    assert dream_history.history_from_key('synthetic', 'people', 'ffffffff', firestore_client=db) == 'first'
    assert len(db.shapes) == 2
    assert all(shape.limit == 1 and shape.offset in (None, 0) for shape in db.shapes)


def test_weighted_cooldown_precedes_hydration_and_seed_errors_keep_dirty(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '0')
    monkeypatch.setattr(dream_history, 'history_page', lambda *a, **k: ['a', 'b'])
    monkeypatch.setattr(dream_history, 'review_states', lambda uid, refs: {'action_items/a': {'last_reviewed_at': NOW}})
    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'action_items'
    rng.choices.return_value = ['action_items/b']
    loaded = []

    def read(uid, ref):
        loaded.append(ref)
        return {'created_at': OLD}

    cleanup.add_seed(
        'synthetic',
        EvidenceRecords(),
        {'started_at': NOW, 'cleanup_selected': True},
        Caps(),
        [],
        read_record=read,
        rng=rng,
    )
    assert loaded == ['action_items/b']
    records = EvidenceRecords({'people/dirty': {'name': 'Synthetic'}})

    def outage(*a, **k):
        raise RuntimeError('synthetic seed outage')

    monkeypatch.setattr(cleanup, 'add_seed', outage)
    assert cleanup.add_seed_safely('synthetic', records, {}, Caps(), [], read_record=read) is records
    assert records.seed_errors == 1 and records.targets == {'people/dirty'}


@pytest.mark.parametrize('source', ['seeded', 'random'])
def test_older_seed_retrieves_context_with_reserved_budget_and_bounded_dirty_settlement(monkeypatch, source):
    uid = 'synthetic-cleanup-budget'
    db = DreamFirestore()
    db.rows[('users', uid)] = {}
    db.rows[('dream_users', uid)] = {'score': 1, 'watermark': OLD}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '1' if source == 'random' else '0')
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    for i in range(35):
        key = f'fragment-{i}'
        db.rows[('dream_users', uid, 'dirty', dream_store.dirty_id('conversations', key))] = {
            'collection': 'conversations',
            'id': key,
            'version': key,
            'last_changed_at': OLD + timedelta(minutes=i),
        }

    real_dirty_refs = dream_store.dirty_refs
    windows = []

    def dirty_refs(owner, **kwargs):
        if kwargs.get('transaction') is None:
            windows.append((kwargs['limit'], kwargs['newest']))
        kwargs.pop('firestore_client', None)
        return real_dirty_refs(owner, firestore_client=db, **kwargs)

    monkeypatch.setattr(dream_store, 'dirty_refs', dirty_refs)
    monkeypatch.setattr(cleanup, 'uniform_ref', lambda *a: 'conversations/older')
    monkeypatch.setattr(dream_history, 'history_page', lambda *a, **k: ['fragment-0', 'older'])
    monkeypatch.setattr(dream_history, 'review_states', lambda *a, **k: {})
    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'conversations'
    rng.choices.return_value = ['conversations/older']
    monkeypatch.setattr(cleanup.random, 'SystemRandom', lambda: rng)
    reads = []
    speech = 'Garden boat planning. ' * 200

    def read(owner, ref, **kwargs):
        reads.append(ref)
        if ref == 'conversations/fragment-0':
            raise dream_reads.DreamTranscriptReadError('Synthetic unreadable transcript')
        if ref.startswith('conversations/fragment-'):
            return None
        return {'created_at': OLD, 'transcript_segments': [{'text': speech}]}

    monkeypatch.setattr(dream_reads, 'read_record', read)
    seen_targets = []

    def candidates(owner, records, *args, **kwargs):
        seen_targets.extend(records.targets)
        return [
            (f'conversations/context-{i}', {'transcript_segments': [{'text': speech}]}, 'semantic') for i in range(4)
        ]

    monkeypatch.setattr(dream_reads, 'context_candidates', candidates)
    lease = dream_store.acquire(uid, Caps(), now=NOW, firestore_client=db)
    diagnostics, unavailable = {}, []
    records, consumed = dream_reads.read_changes(uid, lease, Caps(), diagnostics=diagnostics, unavailable=unavailable)
    assert windows == [(32, False)]
    assert len(unavailable) == 32 and not consumed
    assert records.targets == {'conversations/older'} == set(seen_targets)
    assert records.target_sources == {'conversations/older': source}
    assert len(records) > len(records.targets)
    assert diagnostics['context_budget_counts']['reservation_kept'] == 1
    assert diagnostics['context_budget_counts']['slice_reclaimed'] == 0
    assert dream_prompt.fits_triage(records, Caps()) and dream_context.fits_pass(records, Caps())
    assert len([ref for ref in reads if '/fragment-' in ref]) == 32
    assert 'conversations/fragment-32' not in reads
    dream_store.finish(
        uid,
        lease,
        diagnostics,
        success=True,
        unavailable=unavailable,
        deferred=records.targets,
        seeded=records.targets,
        reviewed=records.targets,
        now=NOW,
        firestore_client=db,
    )
    assert diagnostics['dirty_counts']['permanent_acknowledged'] == 31
    assert dream_store.dirty_count(uid, firestore_client=db) == 4
    state = db.rows[('dream_users', uid, 'reviews', dream_history.review_id('conversations/older'))]
    assert state == {'deferred_until': NOW + timedelta(days=1)}


@pytest.mark.parametrize('targets, pending', [(4, set()), (0, {'action_items/a'})])
def test_seed_cannot_take_reserved_slots_or_pending_dirty_version(monkeypatch, targets, pending):
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '1')
    monkeypatch.setattr(cleanup, 'uniform_ref', lambda *a: 'action_items/a')
    history = Mock(return_value={})
    monkeypatch.setattr(dream_history, 'review_states', history)
    read = Mock(side_effect=AssertionError('seed hydrated a full or pending target set'))
    records = EvidenceRecords({f'conversations/dirty-{i}': {} for i in range(targets)})
    result = cleanup.add_seed(
        'synthetic',
        records,
        {'started_at': NOW, 'cleanup_selected': True},
        Caps(),
        [],
        read_record=read,
        pending_refs=pending,
        rng=random.Random(0),
    )
    assert result is records
    read.assert_not_called()
    history.assert_not_called()


def test_duplicate_pair_cannot_overfill_initial_context_target_slots(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '0')
    monkeypatch.setattr(dream_history, 'history_page', lambda *a, **k: ['a', 'b'])
    monkeypatch.setattr(dream_history, 'review_states', lambda *a: {})
    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'people'
    rng.choices.return_value = ['people/a']
    dirty = EvidenceRecords({f'people/dirty-{i}': {'created_at': OLD, 'name': 'Synthetic'} for i in range(3)})
    result = cleanup.add_seed(
        'synthetic',
        dirty,
        {'started_at': NOW, 'cleanup_selected': True},
        Caps(),
        [],
        read_record=lambda *a: {'created_at': OLD, 'name': 'Mira Holloway'},
        rng=rng,
    )
    assert result is dirty and len(result.targets) == 3
