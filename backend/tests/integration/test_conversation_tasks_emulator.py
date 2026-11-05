"""Production task-filter database queries against an isolated local emulator.

FIRESTORE_EMULATOR_HOST=127.0.0.1:8798 GCLOUD_PROJECT=demo-fs-p1 \
  .venv/bin/python -m pytest tests/integration/test_conversation_tasks_emulator.py
"""

import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import conversation_task_links as links
from models.conversation import Conversation
from models.conversation_tasks import TaskConversationPageRequest
from models.structured import Structured
from utils.conversations.task_filter import task_conversation_page
from utils.other.list_budget import ListReadBudget


@pytest.fixture
def store(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('requires a dedicated loopback Firestore emulator')
    assert urlsplit('http://' + host).hostname in {'127.0.0.1', 'localhost', '::1'}
    assert os.getenv('GCLOUD_PROJECT') == 'demo-fs-p1'
    client = firestore.Client(project='demo-fs-p1', credentials=AnonymousCredentials())
    uid = 'task-filter-' + uuid4().hex
    monkeypatch.setattr(links, 'get_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(links, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-local-task-filter-key')
    yield client, uid
    # Only the synthetic namespace owned by this fixture is ever removed.
    for family in ('action_items', 'conversations'):
        for doc in client.collection('users').document(uid).collection(family).stream():
            doc.reference.delete()
    client.close()


def budget():
    return ListReadBudget(deadline_monotonic=time.monotonic() + 20, max_documents=5000)


def seed(client, uid, count=105):
    user = client.collection('users').document(uid)
    batch = client.batch()
    for i in range(count):
        data = Conversation(
            id=f'c{i:03}',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(minutes=i),
            started_at=None,
            finished_at=None,
            structured=Structured(title=f'Notes {i}', overview=''),
            status='completed',
            discarded=False,
        ).model_dump(mode='python')
        data.update(folder_id='work' if i % 2 == 0 else 'personal', starred=i % 2 == 0)
        batch.set(user.collection('conversations').document(data['id']), data)
    for i in (0, 54, 55, 104):
        batch.set(
            user.collection('action_items').document(f't{i}'),
            {
                'conversation_id': f'c{i:03}',
                'completed': True,
                'deleted': False,
                'description': 'Private task text must never appear in badges',
            },
        )
    batch.commit(timeout=20)
    return user


@pytest.mark.asyncio
async def test_real_query_order_bookmarks_and_sparse_filter_combinations(store):
    client, uid = store
    seed(client, uid)
    collected = []
    request = TaskConversationPageRequest(
        limit=1,
        folder_id='work',
        starred=True,
        start_date=datetime(2025, 12, 31, 22, 15, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    for _ in range(8):
        work = budget()

        async def browse(after, scope):
            return links.browse_candidate_page(uid, request, after=after, scope=scope, budget=work)

        async def presence(ids):
            return links.linked_task_presence(uid, ids, budget=work)

        async def search(page):
            raise AssertionError('browse must not use search')

        page = await task_conversation_page(
            uid, request, budget=work, browse_page=browse, presence=presence, search_page=search
        )
        collected.extend(row['id'] for row in page['items'])
        for row in page['items']:
            Conversation.model_validate(row)
        if page['next_cursor'] is None:
            break
        request = request.model_copy(update={'cursor': page['next_cursor']})
    else:
        pytest.fail('cursor did not terminate')
    assert collected == ['c000', 'c054', 'c104']


def test_real_membership_follows_delete_relink_lock_and_duplicate_task_rows(store):
    client, uid = store
    user = seed(client, uid)
    ids = ['c000', 'c001', 'c054', 'c055', 'c104', 'foreign']

    def read():
        return links.visible_task_presence(uid, ids, budget=budget())

    assert read() == {cid: cid in {'c000', 'c054', 'c055', 'c104'} for cid in ids}
    user.collection('action_items').document('t0').update({'deleted': True})
    user.collection('action_items').document('t54').update({'conversation_id': 'c001'})
    user.collection('conversations').document('c055').update({'is_locked': True})
    user.collection('conversations').document('c104').update({'deleted': True})
    assert read() == {cid: cid == 'c001' for cid in ids}
    user.collection('action_items').document('duplicate').set({'conversation_id': 'c001', 'deleted': False})
    assert read()['c001'] is True
    assert 'Private task' not in str(read())


@pytest.mark.asyncio
async def test_production_http_routes_validate_scope_and_redact_task_contents(store):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from routers.conversation_tasks import router

    client, uid = store
    seed(client, uid)
    app = FastAPI()
    app.include_router(router)
    # Only authentication is replaced, with this fixture's synthetic namespace.
    # The production route, budget, codec, task join and serialization all run.
    for route in app.routes:
        if hasattr(route, 'dependant'):
            for dependency in route.dependant.dependencies:
                app.dependency_overrides[dependency.call] = lambda: uid
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        presence = await http.post(
            '/v1/conversations/task-presence', json={'conversation_ids': ['c000', 'c001', 'unknown']}
        )
        assert presence.status_code == 200, presence.text
        assert presence.json() == {'presence': {'c000': True, 'c001': False, 'unknown': False}}
        page = await http.post('/v1/conversations/with-tasks/page', json={'limit': 2})
        assert page.status_code == 200, page.text
        assert [row['id'] for row in page.json()['items']] == ['c000', 'c054']
        assert 'Private task text' not in page.text
        cursor = page.json()['next_cursor']
        changed = await http.post(
            '/v1/conversations/with-tasks/page', json={'limit': 2, 'cursor': cursor, 'starred': True}
        )
        assert changed.status_code == 400
        invalid = await http.post('/v1/conversations/task-presence', json={'conversation_ids': ['../other']})
        assert invalid.status_code == 422
