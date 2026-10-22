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

from database import stale_conversation_recovery as recovery
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


async def test_todays_orphan_finalizes_despite_old_discarded_head(world):
    db, uid, user = world
    rows = seed(user, 25)
    rows.document('today').set(
        {
            'status': 'in_progress',
            'finished_at': NOW - timedelta(hours=2),
            'transcript_segments': [{'text': 'synthetic'}],
        }
    )
    rows.document('active').set({'status': 'in_progress', 'finished_at': NOW})
    finalized = []

    async def call(fn, *args, **kwargs):
        if fn is recovery.get_stale_recovery_page:
            return fn(*args, **kwargs, now=NOW, firestore_client=db)
        if fn is live.conversations_db.get_conversation:
            return rows.document(args[1]).get().to_dict()
        raise AssertionError(fn.__name__)

    host = SimpleNamespace(
        request=SimpleNamespace(uid=uid),
        state=SimpleNamespace(current_conversation_id='active'),
        persistence=SimpleNamespace(call=call),
    )
    controller = live.LiveConversationController(host, clock=lambda: NOW)

    async def finalize(cid):
        finalized.append(cid)
        rows.document(cid).update({'status': 'completed'})
        return True

    controller.schedule_finalization = finalize
    await controller.recover_stale_in_progress()
    assert finalized == ['today']
    assert rows.document('today').get().to_dict()['status'] == 'completed'
    assert sum(doc.to_dict().get('discarded', False) for doc in rows.stream()) == 25
    assert rows.document('active').get().to_dict()['status'] == 'in_progress'
