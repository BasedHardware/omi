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


def test_queued_close_after_reconcile_read_keeps_home_legacy_until_recapture(db, monkeypatch):
    from concurrent.futures import Future
    from unittest.mock import Mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import episodes
    from routers import episodes as api
    from utils.episodes.log import capture, reads, reconcile, worker
    from utils.other import endpoints

    client, uid = db
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '100')
    monkeypatch.setenv('EPISODES_RECORDED_TIME_ENABLED', 'off')
    root = store.root(client, uid)
    store.owner_ref(client, uid).set(
        dict(cursor=0, next_seq=0, home_version=1, backfill_complete=True, home_rows_ready=True)
    )
    ref = root.collection('episodes').document('e')
    ref.set(
        episodes.seal(
            uid, dict(id='e', status='live', state_version=1, started_at=NOW, last_activity_at=NOW, conversation_ids=[])
        )
    )
    store.invalidate(uid, firestore_client=client)
    queued = []
    monkeypatch.setattr(capture, 'submit', lambda fn: queued.append(fn) or Future())
    monkeypatch.setattr(worker, 'wake', lambda *a: None)
    original = reconcile.snapshot

    def snapshot_then_close(*args):
        snapshot = original(*args)
        assert episodes.close_episode(uid, 'e', 'user', closed_at=NOW, firestore_client=client)['status'] == 'closed'
        assert len(queued) == 1
        assert store.state(uid, firestore_client=client)['next_seq'] == 0
        return snapshot

    monkeypatch.setattr(reconcile, 'snapshot', snapshot_then_close)
    at = datetime.now(timezone.utc)
    assert worker.drain(uid, firestore_client=client, now=at) == 'lost_lease'
    assert store.state(uid, firestore_client=client)['capture_dirty']
    assert not root.collection('episode_views').document('e').get().exists

    # Actual Home routing remains on legacy at 100% reads during the queue gap.
    monkeypatch.setattr(api, '_admitted', lambda *a: True)
    ready = reads.ready
    monkeypatch.setattr(reads, 'ready', lambda uid: ready(uid, firestore_client=client))
    legacy, log = Mock(return_value=([], None)), Mock(return_value=([], [], None))
    monkeypatch.setattr(api.home_read, 'list_episode_window', legacy)
    monkeypatch.setattr(api.home_read, 'project_episodes', lambda *a: [])
    monkeypatch.setattr(reads, 'list_window', log)
    monkeypatch.setattr(worker, 'sample_read', lambda *a: None)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[endpoints.get_current_user_uid] = lambda: uid
    http = TestClient(app)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    assert http.get('/v1/episodes', params=params).status_code == 200
    assert legacy.called and not log.called
    queued.pop()()
    assert store.state(uid, firestore_client=client)['next_seq'] == 1
    assert ready(uid, firestore_client=client) is None  # Delivery alone cannot clear the gap.
    monkeypatch.setattr(reconcile, 'snapshot', original)
    assert worker.drain(uid, firestore_client=client, now=at + timedelta(minutes=11)) == 'drained'
    assert not store.state(uid, firestore_client=client).get('capture_dirty')
    assert episodes.unseal(uid, root.collection('episode_views').document('e').get().to_dict())['status'] == 'closed'
    legacy.reset_mock()
    assert http.get('/v1/episodes', params=params).status_code == 200
    assert log.called and not legacy.called


@pytest.mark.parametrize('change', ['edit', 'insert', 'delete', 'archive'])
def test_reconcile_source_proof_rejects_all_committed_source_changes(db, change):
    from utils.episodes.log import reconcile

    client, uid = db
    root = store.root(client, uid)
    link = root.collection('episode_links').document('c')
    link.set({'episode_id': 'e'})
    receipt = root.collection('episode_segment_receipts').document('c')
    receipt.set({'ids': ['head'], 'shards': 1})
    archive = receipt.collection('s').document('0')
    archive.set({'ids': ['archived']})
    store.invalidate(uid, firestore_client=client)
    at = datetime.now(timezone.utc)
    claimed = store.claim(uid, firestore_client=client, now=at)
    fold, removed_views, removed_links, proof = reconcile.snapshot(uid, client)
    assert set(fold.receipts['c']) == {'head', 'archived'}
    if change == 'edit':
        link.update({'episode_id': 'new'})
    elif change == 'insert':
        root.collection('episode_links').document('new').set({'episode_id': 'new'})
    elif change == 'delete':
        link.delete()
    else:
        archive.update({'ids': ['new']})
    with pytest.raises(store.LostLease, match='source_changed'):
        store.publish(
            uid,
            claimed,
            0,
            fold.checkpoint(),
            {},
            {},
            firestore_client=client,
            now=at,
            repaired=True,
            removed_views=removed_views,
            removed_links=removed_links,
            source_versions=proof,
        )
    assert store.state(uid, firestore_client=client)['capture_dirty']
    assert not root.collection('episode_log_checkpoint').document('fold').get().exists


@pytest.mark.parametrize('writer', ['assignment', 'smart_merge'])
def test_queued_member_writer_after_repair_read_rejects_publish_and_home_uses_legacy(db, monkeypatch, writer):
    from concurrent.futures import Future
    from unittest.mock import Mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import episodes, smart_merge
    from routers import episodes as api
    from utils.episodes import home_read
    from utils.episodes.log import capture, reads, reconcile, worker
    from utils.other import endpoints
    from utils.sync.assignment import assign_in_transaction

    client, uid = db
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '100')
    monkeypatch.setenv('EPISODES_RECORDED_TIME_ENABLED', 'off')
    monkeypatch.setenv('CONVERSATION_SMART_MERGE_FLATTEN_ENABLED', 'off')
    monkeypatch.setattr(worker, 'wake', lambda *a: None)
    root = store.root(client, uid)
    store.owner_ref(client, uid).set(
        dict(cursor=0, next_seq=0, home_version=1, backfill_complete=True, home_rows_ready=True)
    )
    root.collection('episodes').document('e').set(
        episodes.seal(
            uid,
            dict(
                id='e',
                status='closed',
                close_reason='user',
                state_version=1,
                started_at=NOW,
                last_activity_at=NOW + timedelta(minutes=2),
                conversation_ids=['c', 'd'],
            ),
        )
    )
    for cid, minute in [('c', 0), ('d', 1)]:
        root.collection('conversations').document(cid).set(
            dict(
                id=cid,
                status='completed',
                discarded=False,
                source='omi',
                data_protection_level='standard',
                created_at=NOW + timedelta(minutes=minute),
                started_at=NOW + timedelta(minutes=minute),
                finished_at=NOW + timedelta(minutes=minute + 1),
                structured={'title': f'before {cid}'},
                transcript_segments=[],
            )
        )
    store.invalidate(uid, firestore_client=client)
    queued = []
    monkeypatch.setattr(capture, 'submit', lambda fn: queued.append(fn) or Future())
    original = home_read.read_members

    def read_then_commit(*args, **kwargs):
        members = original(*args, **kwargs)
        assert kwargs['source_versions'][root.collection('conversations').document('c').path]
        prior = store.state(uid, firestore_client=client)
        if writer == 'assignment':
            incoming = dict(
                id='chunk',
                source='omi',
                data_protection_level='standard',
                status='completed',
                discarded=False,
                started_at=NOW + timedelta(minutes=2),
                finished_at=NOW + timedelta(minutes=3),
                transcript_segments=[dict(id='s', text='Synthetic appended speech', start=0.0, end=60.0, speaker_id=0)],
            )

            @firestore.transactional
            def assign(transaction):
                return assign_in_transaction(
                    transaction,
                    root,
                    incoming,
                    target_id='c',
                    decode=lambda row: row,
                    encode=lambda row: row,
                    invalidate=lambda row: None,
                )

            result, created, _ = assign(client.transaction())
            assert result['id'] == 'c' and not created
        else:

            def plan(*args):
                return (
                    None,
                    {'structured': {'title': 'after smart merge'}, 'smart_merge': {'role': 'survivor', 'revision': 1}},
                    {'deleted': True, 'sync_merged_into': 'c'},
                    {},
                )

            result = smart_merge.absorb_conversation(
                uid,
                'c',
                'd',
                expected_revision=0,
                plan=plan,
                firestore_client=client,
            )
            assert result.outcome == 'absorbed'
        assert len(queued) == 1
        assert store.state(uid, firestore_client=client) == prior  # No owner watermark change.
        return members

    monkeypatch.setattr(home_read, 'read_members', read_then_commit)
    at = datetime.now(timezone.utc)
    assert worker.drain(uid, firestore_client=client, now=at) == 'lost_lease'
    assert store.state(uid, firestore_client=client)['capture_dirty']
    assert not root.collection('episode_views').document('e').get().exists
    assert not root.collection('episode_log_checkpoint').document('fold').get().exists
    monkeypatch.setattr(home_read, 'read_members', original)
    # Exercise actual Home routing at full admission while member_refresh is queued.
    monkeypatch.setattr(api, '_admitted', lambda *a: True)
    ready = reads.ready
    monkeypatch.setattr(reads, 'ready', lambda uid: ready(uid, firestore_client=client))
    legacy, log = Mock(return_value=([], None)), Mock(return_value=([], [], None))
    monkeypatch.setattr(api.home_read, 'list_episode_window', legacy)
    monkeypatch.setattr(api.home_read, 'project_episodes', lambda *a: [])
    monkeypatch.setattr(reads, 'list_window', log)
    monkeypatch.setattr(worker, 'sample_read', lambda *a: None)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[endpoints.get_current_user_uid] = lambda: uid
    http = TestClient(app)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    assert http.get('/v1/episodes', params=params).status_code == 200
    assert legacy.called and not log.called
    queued.pop()()
    assert store.state(uid, firestore_client=client)['next_seq'] == 1
    assert ready(uid, firestore_client=client) is None
    assert worker.drain(uid, firestore_client=client, now=at + timedelta(minutes=11)) == 'drained'
    assert not store.state(uid, firestore_client=client).get('capture_dirty')
    legacy.reset_mock()
    assert http.get('/v1/episodes', params=params).status_code == 200
    assert log.called and not legacy.called


@pytest.mark.parametrize('change', ['edit', 'delete', 'create_missing', 'hidden_policy'])
def test_repair_member_versions_reject_direct_writes_without_capture(db, change):
    from utils.episodes.log import reconcile

    client, uid = db
    root = store.root(client, uid)
    member = root.collection('conversations').document('c')
    if change != 'create_missing':
        member.set({'structured': {'title': 'before'}, 'deleted': change == 'hidden_policy'})
    store.invalidate(uid, firestore_client=client)
    at = datetime.now(timezone.utc)
    claimed = store.claim(uid, firestore_client=client, now=at)
    fold, removed_views, removed_links, proof = reconcile.snapshot(uid, client)
    reconcile.read_members(uid, [{'conversation_ids': ['c']}], client, proof)
    if change == 'delete':
        member.delete()
    elif change == 'create_missing':
        member.set({'structured': {'title': 'created'}})
    else:
        member.update({'structured.title': 'after', 'deleted': False})
    with pytest.raises(store.LostLease, match='source_changed'):
        store.publish(
            uid,
            claimed,
            0,
            fold.checkpoint(),
            {},
            {},
            firestore_client=client,
            now=at,
            repaired=True,
            removed_views=removed_views,
            removed_links=removed_links,
            source_versions=proof,
        )
    assert store.state(uid, firestore_client=client)['capture_dirty']
    assert not root.collection('episode_log_checkpoint').document('fold').get().exists
