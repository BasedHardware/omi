"""Read budget for one real conversation-list request on the Firestore emulator."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import _client
from models.conversation import Conversation
from models.structured import Structured
from routers import conversations as conversations_router
from testing.firestore_read_budget import delta_reads, read_budget, request_read_trace, snapshot_reads

pytestmark = pytest.mark.integration

_PAGE_LIMIT = 100


def _seed_conversations(client, uid: str) -> None:
    user = client.collection('users').document(uid)
    conversations = user.collection('conversations')
    projection_rows = user.collection('conversation_list_rows')
    batch = client.batch()
    for index in range(_PAGE_LIMIT):
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(minutes=index)
        conversation = Conversation(
            id=f'conversation-{index:03}',
            created_at=created_at,
            started_at=None,
            finished_at=None,
            structured=Structured(title=f'Synthetic notes {index}', overview=''),
            status='completed',
            discarded=False,
        ).model_dump(mode='python')
        batch.set(conversations.document(conversation['id']), conversation)
        batch.set(
            projection_rows.document(conversation['id']),
            {'conversation_id': conversation['id'], 'created_at': created_at, 'deleted': False},
        )
    batch.set(user.collection('list_serving_versions').document('conversations'), {'version': '0' * 32})
    batch.commit(timeout=30)


def test_conversation_list_page_read_budget(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('requires a dedicated loopback Firestore emulator')
    assert urlsplit(f'http://{host}').hostname in {'127.0.0.1', 'localhost', '::1'}

    client = firestore.Client(project=f'demo-read-budget-page-{uuid4().hex[:8]}', credentials=AnonymousCredentials())
    uid = f'synthetic-read-budget-{uuid4().hex}'
    monkeypatch.setattr(_client, '_firestore_client', client)
    _seed_conversations(client, uid)

    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[conversations_router.auth.get_current_user_uid] = lambda: uid
    with TestClient(app) as http:
        before = snapshot_reads()
        with request_read_trace() as trace:
            response = http.get('/v1/conversations', params={'limit': _PAGE_LIMIT})
        delta = delta_reads(before)

    assert response.status_code == 200, response.text
    assert len(response.json()) == _PAGE_LIMIT
    assert trace.reads > 0, 'read-budget harness bug: conversation request recorded zero Firestore reads'
    assert delta.reads > 0, 'read-budget harness bug: counter delta recorded zero Firestore reads'

    budget, _ = read_budget('conversation_list_page')
    fixed_overhead_budget = budget - _PAGE_LIMIT
    # First-run measurement: 100 reads = 100 page documents + 0 fixed overhead;
    # therefore K = ceil(0 * 1.20) = 0. Re-measure before adding overhead headroom.
    print(
        f'conversation_list_page: measured={trace.reads:g} reads/page '
        f'(limit={_PAGE_LIMIT}, overhead={trace.reads - _PAGE_LIMIT:g}, budget={budget})'
    )
    assert fixed_overhead_budget >= 0
    assert trace.reads <= _PAGE_LIMIT + fixed_overhead_budget, (
        f'conversation_list_page: measured {trace.reads:g} Firestore reads exceeds budget '
        f'{_PAGE_LIMIT + fixed_overhead_budget} per page_at_limit_100; caller deltas={delta.by_caller}'
    )
    client.close()
