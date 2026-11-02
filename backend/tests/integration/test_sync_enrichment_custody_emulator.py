"""Real atomic donor transfer, privacy fences, lost ACK and contention replay."""

from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import Mock

from google.cloud.firestore_v1.document import DocumentReference
import pytest

from tests.integration.test_sync_reprocess_emulator import store, loopback_only_network  # noqa: F401
from utils.sync import reprocess

pytestmark = pytest.mark.integration


@pytest.fixture
def custody(store, monkeypatch):
    client, uid, tasks = store
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    monkeypatch.setattr(reprocess, '_wake_exists', lambda _: False)
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'enhanced'})
    canonical = user.collection('conversations').document('canonical')
    canonical.set({'id': 'canonical', 'owner_uid': uid, 'status': 'completed'})
    yield client, uid, tasks, user


def admit(custody, name, *, now=0):
    client, uid, _, user = custody
    user.collection('conversations').document(name).set(
        {'id': name, 'owner_uid': uid, 'deleted': True, 'sync_merged_into': 'canonical'}
    )
    reprocess.mark(uid, name, 'en', now=now)
    key = reprocess.key(uid, name)
    return key, client.collection(reprocess.COLLECTION).document(key).get().to_dict()['task_token']


def redirect(*_):
    reprocess.summary_delivery.PROCESS_CONTEXT.get()['redirect_to'] = 'canonical'


def test_merged_donor_atomically_coalesces_earliest_deadline_and_replay(custody, monkeypatch):
    client, uid, tasks, _ = custody
    donor, token = admit(custody, 'donor')
    reprocess.mark(uid, 'canonical', 'en', now=30)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    assert reprocess.run(donor, token, redirect, now=120) == 'redirected'
    assert not client.collection(reprocess.COLLECTION).document(donor).get().exists
    target = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical'))
    row = target.get().to_dict()
    assert row['first_pending_at'] == 0 and row['summary_deadline_at'] == row['due_at'] == 120
    assert row['version'] == 2 and not row['summary_seen']
    assert reprocess.run(donor, token, Mock(side_effect=AssertionError()), now=121) == 'stale'
    process = Mock(return_value={'structured': {'overview': 'Synthetic summary committed through normal callback'}})
    assert reprocess.run(target.id, row['task_token'], process, now=121) == 'processed'
    process.assert_called_once_with(uid, 'canonical', 'en')
    assert target.get().to_dict()['summary_seen']


def test_lost_enqueue_reply_after_transfer_cannot_lose_or_duplicate_custody(custody, monkeypatch):
    client, uid, _, _ = custody
    donor, token = admit(custody, 'donor')
    monkeypatch.setattr(reprocess, '_enqueue', Mock(side_effect=RuntimeError('synthetic lost ACK')))
    with pytest.raises(RuntimeError):
        reprocess.run(donor, token, redirect, now=120)
    target = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical'))
    before = target.get().to_dict()
    assert before['summary_deadline_at'] == 120
    assert not client.collection(reprocess.COLLECTION).document(donor).get().exists
    assert reprocess.run(donor, token, Mock(side_effect=AssertionError()), now=121) == 'stale'
    assert target.get().to_dict() == before
    enqueue = Mock()
    monkeypatch.setattr(reprocess, '_enqueue', enqueue)
    assert reprocess.sweep(now=122)['error'] == 0
    assert enqueue.call_count >= 1
    assert target.get().to_dict()['summary_deadline_at'] == 120


def test_transfer_preserves_active_canonical_lease_and_publication_owner(custody):
    client, uid, _, _ = custody
    donor, token = admit(custody, 'donor')
    reprocess.mark(uid, 'canonical', 'en', now=0)
    target = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical'))
    original = target.get().to_dict()

    def in_flight(*_):
        before = target.get().to_dict()
        assert reprocess.run(donor, token, redirect, now=121) == 'redirected'
        after = target.get().to_dict()
        assert after['owner'] == before['owner'] and after['lease_until'] == before['lease_until']
        assert after['task_token'] == before['task_token']
        assert after['version'] == before['version'] + 1
        assert reprocess.run(target.id, original['task_token'], Mock(side_effect=AssertionError()), now=122) == 'busy'
        return {'structured': {'overview': 'Synthetic normal callback receipt'}}

    assert reprocess.run(target.id, original['task_token'], in_flight, now=120) == 'processed'


@pytest.mark.parametrize('canonical_accept', [-120, -60])
def test_transfer_never_extends_existing_deadline_including_zero(custody, canonical_accept):
    client, uid, _, _ = custody
    donor, token = admit(custody, 'donor')
    reprocess.mark(uid, 'canonical', 'en', now=canonical_accept)
    assert reprocess.run(donor, token, redirect, now=120) == 'redirected'
    row = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical')).get().to_dict()
    assert row['summary_deadline_at'] == row['due_at'] == canonical_accept + 120
    assert row['first_pending_at'] == canonical_accept


def test_transfer_keeps_committed_canonical_summary_receipt(custody):
    client, uid, _, _ = custody
    reprocess.mark(uid, 'canonical', 'en', now=0)
    target = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical'))
    token = target.get().to_dict()['task_token']
    reprocess.run(target.id, token, lambda *_: {'structured': {'overview': 'Synthetic committed summary'}}, now=120)
    assert target.get().to_dict()['summary_seen']
    donor, token = admit(custody, 'donor', now=121)
    assert reprocess.run(donor, token, redirect, now=241) == 'redirected'
    row = target.get().to_dict()
    assert row['summary_seen'] and row['conversation_id'] == 'canonical'
    assert not row['dormant']  # Trailing content update is still owed.
    assert row['summary_deadline_at'] <= 241


def test_real_transaction_conflict_retries_without_duplicate_transfer(custody, monkeypatch):
    client, uid, _, _ = custody
    donors = [admit(custody, 'donor-' + str(i), now=i) for i in range(2)]
    target_path = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical')).path
    original_get = DocumentReference.get
    barrier = threading.Barrier(2)
    local = threading.local()
    reads = []

    def get(reference, *args, **kwargs):
        result = original_get(reference, *args, **kwargs)
        if reference.path == target_path and kwargs.get('transaction') is not None:
            reads.append(1)
            if not getattr(local, 'waited', False):
                local.waited = True
                barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(DocumentReference, 'get', get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: reprocess.run(*pair, redirect, now=122), donors))
    assert results == ['redirected', 'redirected']
    assert len(reads) >= 3  # Both read the same generation; one real commit retried.
    row = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical')).get().to_dict()
    assert row['version'] == 2 and row['first_pending_at'] == 0 and row['summary_deadline_at'] == 120
    assert all(not client.collection(reprocess.COLLECTION).document(key).get().exists for key, _ in donors)


def test_user_deletion_dominates_server_merge_redirect(custody):
    client, uid, _, user = custody
    donor, token = admit(custody, 'donor')
    user.collection('deleted_conversations').document('canonical').set({'deleted': True})
    assert reprocess.run(donor, token, redirect, now=120) == 'redirected'
    assert not client.collection(reprocess.COLLECTION).document(donor).get().exists
    assert not client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical')).get().exists


def test_redirect_cannot_reset_canonical_terminal_empty_output_budget(custody):
    client, uid, _, _ = custody
    donor, token = admit(custody, 'donor')
    reprocess.mark(uid, 'canonical', 'en', now=30)
    target = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical'))
    target.update(
        {
            'summary_empty_failures': 3,
            'summary_blocked_reason': 'empty_output_exhausted',
            'dormant': True,
            'due_at': None,
        }
    )
    assert reprocess.run(donor, token, redirect, now=120) == 'redirected'
    row = target.get().to_dict()
    assert row['summary_empty_failures'] == 3 and row['summary_blocked_reason'] == 'empty_output_exhausted'
    assert row['dormant'] and row['summary_deadline_at'] == 120


def test_invalid_canonical_owner_never_receives_transferred_debt(custody):
    client, uid, _, user = custody
    donor, token = admit(custody, 'donor')
    user.collection('conversations').document('canonical').update({'owner_uid': 'different-synthetic-owner'})
    with pytest.raises(reprocess.FirstSummaryCallbackPending):
        reprocess.run(donor, token, redirect, now=120)
    assert client.collection(reprocess.COLLECTION).document(donor).get().to_dict()['summary_deadline_at'] == 120
    assert not client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'canonical')).get().exists


def test_completed_receipt_old_wake_acks_without_null_owner_privacy_error(custody, monkeypatch):
    from utils.batch_pipeline import enrichment

    client, uid, _, _ = custody
    reprocess.mark(uid, 'canonical', 'en', now=0)
    key = reprocess.key(uid, 'canonical')
    token = client.collection(reprocess.COLLECTION).document(key).get().to_dict()['task_token']
    reprocess.run(key, token, lambda *_: {'structured': {'overview': 'Synthetic committed summary'}}, now=120)
    row = client.collection(reprocess.COLLECTION).document(key).get().to_dict()
    assert row['dormant'] and row['uid'] is None
    monkeypatch.setattr(enrichment, 'get_firestore_client', lambda: client)
    assert enrichment.run_enrichment(key, token, now=121, process=Mock(side_effect=AssertionError())) == 'stale'


def test_watchdog_cursor_reaches_exhausted_wake_beyond_valid_prefix(custody, monkeypatch):
    client, uid, _, _ = custody
    cursor = client.collection('sync_reprocess_scan').document('cursor')
    cursor.delete()
    refs = []
    for index in range(6):
        document_id = f'{index:064x}'
        ref = client.collection(reprocess.COLLECTION).document(document_id)
        ref.set(
            {
                'document_id': document_id,
                'uid': uid,
                'conversation_id': 'scan-' + str(index),
                'language': 'en',
                'version': 1,
                'task_token': 'a' * 32,
                'due_at': 100000,
                'task_due_at': 100000,
                'first_pending_at': 0,
                'summary_deadline_at': 120,
                'dispatch': reprocess._dispatch_binding(),
            }
        )
        refs.append(ref)
    monkeypatch.setattr(reprocess, '_wake_exists', lambda row: row['document_id'] != refs[-1].id)
    try:
        assert reprocess.sweep(now=100001, limit=2) == {'repaired': 0, 'error': 0}
        assert reprocess.sweep(now=100001, limit=2) == {'repaired': 0, 'error': 0}
        assert reprocess.sweep(now=100001, limit=2) == {'repaired': 1, 'error': 0}
        row = refs[-1].get().to_dict()
        assert row['task_token'] != 'a' * 32 and row['summary_deadline_at'] == 120
        assert all(ref.get().to_dict()['task_token'] == 'a' * 32 for ref in refs[:-1])
    finally:
        for ref in refs:
            ref.delete()
        cursor.delete()


def test_loopback_http_acks_redirect_deferred_busy_and_real_deletion(custody, monkeypatch):
    """Real router, callback, adapter and Firestore; only auth/codec/queue leaves replaced."""
    import socket
    import time

    from fastapi import FastAPI, Header, HTTPException
    import httpx
    import uvicorn
    from routers import sync as router
    from utils.batch_pipeline import enrichment
    from utils.sync import pipeline

    client, uid, tasks, user = custody
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_PIPELINE_NAMESPACE', 'prod')
    monkeypatch.setattr(enrichment, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(pipeline.conversations_db, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(
        pipeline.conversations_db,
        'get_conversation',
        lambda owner, cid: client.collection('users')
        .document(owner)
        .collection('conversations')
        .document(cid)
        .get()
        .to_dict(),
    )
    monkeypatch.setattr(router.uid_sequencer, 'production_fence_mode', lambda: None)

    async def authenticate(authorization: str = Header('')):
        if authorization != 'Bearer local-emulator-task':
            raise HTTPException(status_code=403)
        return 0

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.verify_cloud_tasks_oidc] = authenticate
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=f'http://127.0.0.1:{port}') as http:

            def post(key, token):
                return http.post(
                    '/v2/sync-jobs/run',
                    json={'kind': 'sync_reprocess', 'key': key, 'task_token': token},
                    headers={'Authorization': 'Bearer local-emulator-task'},
                )

            donor, token = admit(custody, 'http-donor')
            response = post(donor, token)
            assert response.status_code == 200 and response.json() == {'status': 'redirected'}
            assert not client.collection(reprocess.COLLECTION).document(donor).get().exists
            assert post(donor, token).json() == {'status': 'stale'}
            user.collection('conversations').document('open').set({'sync_live_target': True, 'status': 'in_progress'})
            accepted = time.time() - 121
            reprocess.mark(uid, 'open', 'en', now=accepted)
            key, token = reprocess.key(uid, 'open'), tasks[-1]['task_token']
            response = post(key, token)
            assert response.status_code == 200 and response.json() == {'status': 'deferred'}
            ref = client.collection(reprocess.COLLECTION).document(key)
            pending = ref.get().to_dict()
            assert pending['summary_deadline_at'] == accepted + 120
            assert pending['deferred_reason'] == 'open_live_target' and pending['due_at'] > time.time()
            ref.update({'lease_until': time.time() + 120, 'owner': 'synthetic-active-owner'})
            response = post(key, pending['task_token'])
            assert response.status_code == 200 and response.json() == {'status': 'busy'}
            user.collection('conversations').document('deleted').set({'deleted': True})
            reprocess.mark(uid, 'deleted', 'en', now=accepted)
            key, token = reprocess.key(uid, 'deleted'), tasks[-1]['task_token']
            response = post(key, token)
            assert response.status_code == 200 and response.json() == {'status': 'superseded'}
            assert not client.collection(reprocess.COLLECTION).document(key).get().exists
            user.collection('conversations').document('cycle').set({'deleted': True, 'sync_merged_into': 'cycle'})
            reprocess.mark(uid, 'cycle', 'en', now=accepted)
            key, token = reprocess.key(uid, 'cycle'), tasks[-1]['task_token']
            response = post(key, token)
            assert response.status_code == 200 and response.json() == {'status': 'deferred'}
            assert (
                client.collection(reprocess.COLLECTION).document(key).get().to_dict()['summary_deadline_at']
                == accepted + 120
            )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
