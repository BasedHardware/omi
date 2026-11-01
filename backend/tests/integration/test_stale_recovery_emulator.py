"""Synthetic reconnect recovery through the real Firestore SDK and controller.

Run via Firebase emulators:exec, with BACKEND_UNIT_TEST_FILE_LIST pointing to
this file and BACKEND_PYTEST_MARK_EXPR='' (test.sh otherwise omits integration).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from urllib.parse import urlparse
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import _client, conversation_finalization_jobs as jobs
from database import stale_conversation_recovery as recovery
from utils.conversations import lifecycle
from routers.listen import conversations as live

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 22, 4, tzinfo=timezone.utc)


@pytest.fixture
def world():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    db = firestore.Client(project='demo-p54', credentials=AnonymousCredentials())
    uid = f'p54-{uuid.uuid4().hex}'
    user = db.collection('users').document(uid)
    yield db, uid, user
    db.close()


def seed(user, count=25):
    rows = user.collection('conversations')
    for index in range(count):
        rows.document(f'poison-{index:02}').set(
            {'status': 'in_progress', 'discarded': True, 'finished_at': NOW - timedelta(days=30, minutes=index)}
        )
    return rows


def page(db, uid, *, now=NOW):
    return recovery.get_stale_recovery_page(uid, cutoff=now - timedelta(hours=1), now=now, firestore_client=db)


def test_newest_first_pages_past_poison_then_wraps_with_backoff(world):
    db, uid, user = world
    seed(user)
    first = page(db, uid)
    assert [r['id'] for r in first] == [f'poison-{i:02}' for i in range(10)]
    assert page(db, uid, now=NOW + timedelta(seconds=59)) == []
    second = page(db, uid, now=NOW + timedelta(minutes=1))
    assert [r['id'] for r in second] == [f'poison-{i:02}' for i in range(10, 20)]
    third = page(db, uid, now=NOW + timedelta(minutes=2))
    assert [r['id'] for r in third] == [f'poison-{i:02}' for i in range(20, 25)]
    assert page(db, uid, now=NOW + timedelta(minutes=3)) == first


def test_value_cursor_survives_deleted_row_and_equal_clocks(world):
    db, uid, user = world
    rows = seed(user, 12)
    for doc in rows.stream():
        doc.reference.update({'finished_at': NOW - timedelta(days=30)})
    first = page(db, uid)
    rows.document(first[-1]['id']).delete()
    second = page(db, uid, now=NOW + timedelta(minutes=1))
    assert len(second) == 2
    assert not ({r['id'] for r in first} & {r['id'] for r in second})


def test_concurrent_reconnects_only_claim_one_page(world):
    db, uid, user = world
    seed(user)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(lambda _: page(db, uid), range(4)))
    assert sorted(map(len, pages)) == [0, 0, 0, 10]


async def test_todays_orphan_finalizes_despite_old_discarded_head(world, monkeypatch):
    db, uid, user = world
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(live, 'get_byok_keys', lambda: {})
    monkeypatch.setattr(lifecycle, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(live.conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    rows = seed(user, 25)
    rows.document('today').set(
        {
            'status': 'in_progress',
            'finished_at': NOW - timedelta(hours=2),
            'transcript_segments': [{'text': 'synthetic'}],
            'has_content': True,
            'has_photos': False,
            'source': 'omi',
        }
    )
    rows.document('active').set({'status': 'in_progress', 'finished_at': NOW})
    finalized = []

    async def call(fn, *args, **kwargs):
        if fn is recovery.get_stale_recovery_page:
            return fn(*args, **kwargs, now=NOW, firestore_client=db)
        if fn is live.conversations_db.get_conversation:
            return rows.document(args[1]).get().to_dict()
        if fn is lifecycle.request_finalization:
            return fn(*args, **kwargs, firestore_client=db)
        raise AssertionError(fn.__name__)

    async def worker(cid, job_id, generation):
        # Replace paid providers/fanout only. Admission, lease, completion and
        # replay fences use the real lifecycle/database transactions.
        claim = jobs.claim_finalization_job(job_id, generation, firestore_client=db)
        assert claim['status'] == 'claimed'
        assert lifecycle.complete(uid, cid)
        epoch = claim['lease_epoch']
        assert jobs.claim_finalization_fanout(job_id, generation, epoch, firestore_client=db)['status'] == 'claimed'
        assert jobs.mark_finalization_fanout_completed(job_id, generation, epoch, firestore_client=db)
        assert jobs.mark_finalization_completed(job_id, generation, epoch, firestore_client=db)
        finalized.append(cid)

    host = SimpleNamespace(
        request=SimpleNamespace(uid=uid),
        state=SimpleNamespace(current_conversation_id='active'),
        persistence=SimpleNamespace(call=call),
        client_kind='ios',
        request_conversation_processing=worker,
        spawn=lambda coro, **_: coro.close(),
    )
    controller = live.LiveConversationController(host, clock=lambda: NOW)
    await controller.recover_stale_in_progress()
    assert finalized == ['today']
    job_id = rows.document('today').get().to_dict()['finalization_job_id']
    assert jobs.get_finalization_job(job_id, firestore_client=db)['status'] == 'completed'
    assert rows.document('today').get().to_dict()['status'] == 'completed'
    assert sum(doc.to_dict().get('discarded', False) for doc in rows.stream()) == 25
    assert rows.document('active').get().to_dict()['status'] == 'in_progress'


def test_account_deletion_started_after_scan_cannot_recreate_cursor(world, monkeypatch):
    db, uid, user = world
    seed(user)
    claim = recovery._claim_page_txn

    def deletion_wins(*args, **kwargs):
        db.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})
        return claim(*args, **kwargs)

    monkeypatch.setattr(recovery, '_claim_page_txn', deletion_wins)
    attempted = page(db, uid)
    assert not user.collection('conversation_recovery_state').document('stale_in_progress').get().exists
    assert attempted == []


def test_default_recovery_client_uses_customer_plane_not_compute_plane(world, monkeypatch):
    db, uid, user = world
    seed(user, 1)
    compute = firestore.Client(project='demo-p54-compute', credentials=AnonymousCredentials())
    try:
        compute_user = compute.collection('users').document(uid)
        compute_user.collection('conversations').document('wrong-plane').set(
            {'status': 'in_progress', 'finished_at': NOW - timedelta(days=30)}
        )
        monkeypatch.setattr(_client, '_firestore_client', compute)
        monkeypatch.setattr(_client, '_data_plane_firestore_client', db)
        selected = recovery.get_stale_recovery_page(uid, cutoff=NOW - timedelta(hours=1), now=NOW)
        assert selected == [{'id': 'poison-00'}]
        assert user.collection('conversation_recovery_state').document('stale_in_progress').get().exists
        assert not compute_user.collection('conversation_recovery_state').document('stale_in_progress').get().exists
    finally:
        compute.close()


@pytest.mark.parametrize('mode', ['serve', 'shadow'])
def test_head_probe_sees_a_fresh_orphan_without_losing_tail_progress(world, monkeypatch, mode):
    db, uid, user = world
    monkeypatch.setenv('LIFECYCLE_V2_MODE', mode)
    rows = seed(user, 35)
    page(db, uid)
    second = page(db, uid, now=NOW + timedelta(minutes=1))
    state = user.collection('conversation_recovery_state').document('stale_in_progress')
    tail_cursor = state.get().to_dict()['cursor']
    rows.document('fresh-orphan').set({'status': 'in_progress', 'finished_at': NOW - timedelta(hours=2)})
    third = page(db, uid, now=NOW + timedelta(minutes=2))
    if mode == 'serve':
        assert third[0]['id'] == 'fresh-orphan'
        assert state.get().to_dict()['cursor'] == tail_cursor
        following = page(db, uid, now=NOW + timedelta(minutes=3))
        assert following[0]['id'] == 'poison-20'
    else:
        assert third[0]['id'] == 'poison-20'
        assert not ({r['id'] for r in second} & {r['id'] for r in third})
