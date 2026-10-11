"""Synthetic older-data recall, sampling and cooldown contracts."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import random

from config.dream_agent import Caps
from database import dream_history, dream_store
from tests.support.dream_firestore import DreamFirestore
from utils import dream_cleanup as cleanup
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


def test_uniform_sample_includes_every_collection_and_rank(monkeypatch):
    counts = dict(zip(dream_history.COLLECTIONS, [2, 1, 3, 2]))
    monkeypatch.setattr(dream_history, 'history_count', lambda uid, col: counts[col])
    monkeypatch.setattr(dream_history, 'history_at_rank', lambda uid, col, rank: str(rank))
    refs = []
    for rank in range(8):
        rng = Mock()
        rng.randrange.return_value = rank
        refs.append(cleanup.uniform_ref('synthetic', rng))
    assert refs == [
        'conversations/0',
        'conversations/1',
        'action_items/0',
        'people/0',
        'people/1',
        'people/2',
        'memory_items/0',
        'memory_items/1',
    ]


def test_seed_duplicate_operands_and_context_roles(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '0')
    monkeypatch.setattr(dream_history, 'history_page', lambda *args, **kwargs: ['a', 'b'])
    monkeypatch.setattr(dream_history, 'last_reviewed', lambda *args: {})
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
    combined = add_context(records, [('screen/context', {'text': 'synthetic'})], Caps())
    assert combined.targets == records.targets
    assert combined.target_sources == records.target_sources
    assert combined.cleanup_cursor == {'people': 'b'}


def test_random_seed_rejected_without_resampling_and_budget_defers(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '1')
    pick = Mock(return_value='action_items/a')
    monkeypatch.setattr(cleanup, 'uniform_ref', pick)
    monkeypatch.setattr(dream_history, 'last_reviewed', lambda *args: {'action_items/a': NOW})
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
    monkeypatch.setattr(dream_history, 'last_reviewed', lambda *args: {})
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
    db.rows[('dream_users', uid)] = {'score': 0, 'last_pass_at': OLD}
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
