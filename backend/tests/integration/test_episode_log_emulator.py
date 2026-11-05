"""Real atomic rollback and concurrent leases. Loopback emulator only, never cloud."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import episode_log as store

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch):
    from concurrent.futures import Future
    from utils.episodes.log import capture

    def immediate(fn):
        future = Future()
        future.set_result(fn())
        return future

    monkeypatch.setattr(capture, 'submit', immediate)
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('Requires a loopback Firestore emulator; no cloud fallback')
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    client = firestore.Client(project='demo-episode-log', credentials=AnonymousCredentials())
    return client, 'episode-log-' + uuid4().hex


def test_abort_after_staging_publishes_neither_fact_nor_legacy_mutation(db):
    client, uid = db
    legacy = store.root(client, uid).collection('episodes').document('e')
    legacy.set({'title': 'before'})

    @firestore.transactional
    def doomed(transaction):
        capture = store.prepare(transaction, client, uid)
        legacy.get(transaction=transaction)
        transaction.update(legacy, {'title': 'after'})
        capture.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], now=NOW)
        raise RuntimeError('synthetic process death before commit')

    with pytest.raises(RuntimeError, match='synthetic process death'):
        doomed(client.transaction())
    assert legacy.get().to_dict() == {'title': 'before'}
    assert list(store.root(client, uid).collection('episode_facts').stream()) == []
    assert store.state(uid, firestore_client=client) == {}


def test_competing_claims_one_epoch_and_stale_publication_is_atomic(db):
    client, uid = db
    store.append(uid, 'key', [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client, now=NOW)

    def take(_):
        return store.claim(uid, firestore_client=client, now=NOW + timedelta(minutes=3))

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(take, range(4)))
    winners = [claim for claim in claims if claim]
    assert len(winners) == 1
    stale = winners[0]
    current = store.claim(uid, firestore_client=client, now=NOW + timedelta(minutes=14))
    assert current['epoch'] == stale['epoch'] + 1
    with pytest.raises(store.LostLease):
        store.publish(
            uid, stale, 1, {}, {'e': {'title': 'stale'}}, {}, firestore_client=client, now=NOW + timedelta(minutes=14)
        )
    assert not store.root(client, uid).collection('episode_views').document('e').get().exists
    assert store.state(uid, firestore_client=client).get('cursor', 0) == 0


def test_bounded_fact_page_has_contiguous_arrival_order_and_dedupes(db):
    client, uid = db
    for key in ('z', 'a', 'm'):
        store.append(
            uid, key, [{'kind': 'member_refresh', 'cid': key, 'payload': {}}], firestore_client=client, now=NOW
        )
    assert store.append(uid, 'a', [], firestore_client=client, now=NOW) is None
    page = store.fact_page(uid, 0, 3, limit=2, firestore_client=client)
    assert [row['key'] for row in page] == ['z', 'a']
    events, cursor = store.read_batch(
        uid, {'state': store.state(uid, firestore_client=client)}, firestore_client=client
    )
    assert [event['cid'] for event in events] == ['z', 'a', 'm'] and cursor == 3


def test_fixed_window_fact_capture_uses_real_transactional_batch_get(db):
    from database import episodes, episode_timeline
    from utils.episodes.timeline import choose_recorded_episode
    from utils.episodes.log.fold import Fold

    client, uid = db
    root = store.root(client, uid)
    fixed = {
        'id': 'fixed',
        'status': 'closed',
        'close_reason': 'user',
        'started_at': NOW,
        'last_activity_at': NOW + timedelta(minutes=10),
        'recorded_end': NOW + timedelta(minutes=10),
        'closed_at': NOW + timedelta(minutes=10),
        'conversation_ids': [],
        'state_version': 1,
    }
    root.collection('episodes').document('fixed').set(episodes.seal(uid, fixed))
    neighbor = dict(
        fixed,
        id='neighbor',
        started_at=NOW - timedelta(minutes=20),
        last_activity_at=NOW - timedelta(minutes=10),
        recorded_end=NOW - timedelta(minutes=10),
        closed_at=NOW - timedelta(minutes=10),
        conversation_ids=['neighbor-member'],
        member_activity={'neighbor-member': NOW - timedelta(minutes=10)},
    )
    root.collection('episodes').document('neighbor').set(episodes.seal(uid, neighbor))
    result = episode_timeline.attach_recorded(
        uid,
        'c',
        'omi',
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=2),
        choose=choose_recorded_episode,
        new_episode={},
        firestore_client=client,
    )
    state = store.state(uid, firestore_client=client)
    facts, cursor = store.read_batch(uid, {'state': state}, firestore_client=client)
    fold = Fold(uid)
    for fact in facts:
        fold.apply(fact)
    assert cursor == state['next_seq'] and result['id'] == 'fixed'
    assert fold.rows()['fixed']['conversation_ids'] == result['conversation_ids'] == ['c']
    assert fold.rows()['neighbor']['conversation_ids'] == ['neighbor-member']
    assert fold.rows()['neighbor']['member_activity'] == neighbor['member_activity']


def test_accepted_deletion_fences_a_previously_claimed_worker(db):
    client, uid = db
    store.append(
        uid, 'before', [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client, now=NOW
    )
    claim = store.claim(uid, firestore_client=client, now=NOW + timedelta(minutes=3))
    client.collection('account_deletions').document(uid).set({'wipe_status': 'pending_deletion'})
    with pytest.raises(store.LostLease, match='account_deletion_fenced'):
        store.publish(
            uid,
            claim,
            1,
            {},
            {'e': {'title': 'must not resurrect'}},
            {},
            firestore_client=client,
            now=NOW + timedelta(minutes=4),
        )
    assert not store.root(client, uid).collection('episode_views').document('e').get().exists
    assert store.append(uid, 'late', [], firestore_client=client) is None


@pytest.mark.parametrize('failure', ['capture', 'oversize'])
def test_post_commit_capture_failure_preserves_real_composer_write_and_response(db, monkeypatch, failure):
    from database import episodes

    client, uid = db
    ref = store.root(client, uid).collection('episodes').document('e')
    ref.set(
        episodes.seal(
            uid,
            {
                'id': 'e',
                'state_version': 1,
                'status': 'closed',
                'close_reason': 'user',
                'started_at': NOW,
                'last_activity_at': NOW,
                'conversation_ids': [],
                'title': 'before',
            },
        )
    )
    updates = {'title': 'after'}
    if failure == 'capture':

        def unavailable(*args, **kwargs):
            assert episodes.unseal(uid, ref.get().to_dict())['title'] == 'after'
            raise RuntimeError('synthetic capture outage')

        monkeypatch.setattr(store, 'append', unavailable)
    else:
        updates['parallel_content_spans'] = {f'c{i}': {'start': NOW, 'end': NOW} for i in range(1000)}
    response = episodes.update_episode(uid, 'e', expected_version=1, updates=updates, firestore_client=client)
    committed = episodes.unseal(uid, ref.get().to_dict())
    assert response['title'] == committed['title'] == 'after'
    assert response['state_version'] == committed['state_version'] == 2
    assert list(store.root(client, uid).collection('episode_facts').stream()) == []
    assert store.state(uid, firestore_client=client)['capture_dirty']


def test_caught_up_owner_is_absent_from_real_due_query(db):
    client, uid = db
    store.append(uid, 'fact', [], firestore_client=client, now=NOW)
    claimed = store.claim(uid, firestore_client=client, now=NOW + timedelta(minutes=3))
    store.publish(uid, claimed, 1, {}, {}, {}, firestore_client=client, now=NOW + timedelta(minutes=4))
    due = store.due_owners(NOW + timedelta(days=10), firestore_client=client, limit=10000)
    assert uid not in {owner for owner, _ in due}


@pytest.mark.parametrize('tombstone', [False, True])
def test_conversation_erasure_cannot_leave_content_in_real_facts(db, tombstone):
    from utils.encryption import decrypt

    client, uid = db
    root = store.root(client, uid)
    ref = root.collection('conversations').document('c')
    secret = 'synthetic private conversation text'
    ref.set({'title': secret})
    store.append(
        uid,
        'speech',
        [
            {
                'kind': 'baseline',
                'payload': {
                    'row': {
                        'id': 'e',
                        'title': secret,
                        'bullets': [secret],
                        'content': secret,
                        'composed_notes': secret,
                        'conversation_ids': ['c'],
                    }
                },
            }
        ],
        firestore_client=client,
        now=NOW,
    )

    @firestore.transactional
    def erase(transaction):
        capture = store.prepare_member_change(transaction, root)
        if tombstone:
            transaction.update(ref, {'deleted': True, 'title': None})
        else:
            transaction.delete(ref)
        store.member_changed(capture, ['c'])

    erase(client.transaction())
    facts = list(root.collection('episode_facts').stream())
    assert len(facts) == 2
    for snapshot in facts:
        fact = snapshot.to_dict()
        assert secret not in decrypt(fact['payload'], uid)
        assert fact['expires_at'] == fact['recorded_at'] + timedelta(days=1)


@pytest.mark.parametrize('failure', ['capture', 'policy_entry', 'policy_refresh', 'overflow'])
def test_dropped_work_real_reconcile_restores_home_and_removes_stale_views(db, monkeypatch, failure):
    from database import episodes
    from utils.episodes.log import capture, reads, worker
    from utils.episodes.log.policy import home_policy_write
    from unittest.mock import Mock

    client, uid = db
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '100')
    root = store.root(client, uid)
    root.collection('episode_log_state').document('owner').set(
        {'cursor': 0, 'next_seq': 0, 'home_version': 1, 'backfill_complete': True, 'home_rows_ready': True}
    )
    fixed = dict(
        id='e',
        status='closed',
        close_reason='user',
        state_version=1,
        started_at=NOW,
        last_activity_at=NOW + timedelta(minutes=10),
        closed_at=NOW + timedelta(minutes=10),
        recorded_end=NOW + timedelta(minutes=10),
        conversation_ids=['c'],
        member_activity={'c': NOW + timedelta(minutes=10)},
    )
    root.collection('episodes').document('e').set(episodes.seal(uid, dict(fixed, title='Synthetic private title')))
    root.collection('conversations').document('c').set(
        dict(
            status='completed',
            started_at=NOW,
            finished_at=NOW + timedelta(minutes=10),
            discarded=False,
            structured={'title': 'Current member', 'emoji': '🗒️'},
        )
    )
    root.collection('episode_views').document('removed').set({'id': 'removed'})
    root.collection('episode_view_links').document('removed').set({'episode_id': 'removed'})
    assert reads.ready(uid, firestore_client=client)
    if failure == 'capture':
        with monkeypatch.context() as local:
            local.setattr(store, 'append', Mock(side_effect=RuntimeError('synthetic capture failure')))
            intent = capture.DeferredCapture(client, uid)
            intent.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}])
            intent.flush()
    elif failure == 'overflow':
        with monkeypatch.context() as local:
            local.setattr(capture, 'submit', Mock(side_effect=RuntimeError('queue full')))
            capture.dispatch(lambda: None, uid=uid, client=client)
    else:
        barrier = store.policy_barrier

        def fail_barrier(*args, **kwargs):
            if kwargs['entering'] == (failure == 'policy_entry'):
                raise RuntimeError('synthetic barrier failure')
            return barrier(*args, **kwargs)

        with monkeypatch.context() as local:
            local.setattr(store, 'policy_barrier', fail_barrier)

            @home_policy_write(firestore_client=lambda: client)
            def edit(uid, conversation_id):
                return 'committed'

            assert edit(uid, 'c') == 'committed'
    assert store.state(uid, firestore_client=client)['capture_dirty']
    assert reads.ready(uid, firestore_client=client) is None
    monkeypatch.setattr(worker, 'wake', lambda *a: None)
    # Failed release retains its entry barrier until the existing recovery deadline.
    at = datetime.now(timezone.utc) + timedelta(minutes=26)
    assert worker.drain(uid, firestore_client=client, now=at) == 'drained'
    assert not store.state(uid, firestore_client=client).get('capture_dirty')
    assert reads.ready(uid, firestore_client=client, now=at)
    assert not root.collection('episode_views').document('removed').get().exists
    assert not root.collection('episode_view_links').document('removed').get().exists
    _, homes, _ = reads.list_window(uid, NOW, NOW + timedelta(hours=1), firestore_client=client)
    assert homes[0]['members'][0]['id'] == 'c'
    assert homes[0]['members'][0]['title'] == 'Current member'
    from utils.episodes.log.codec import dumps

    assert 'Synthetic private title' not in dumps(store.checkpoint(uid, firestore_client=client))
