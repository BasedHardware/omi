"""Real Firestore SDK cursor/query verification; loopback emulator only.

FIRESTORE_EMULATOR_HOST=127.0.0.1:18539 PYTHONPATH=backend \
  backend/.venv/bin/python -m pytest backend/tests/integration/test_direct_transcript_search_emulator.py -q
"""

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import transcript_search as store
from utils.other.list_budget import ListReadBudget

pytestmark = pytest.mark.integration


@pytest.fixture
def owner():
    assert os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:'))
    client = firestore.Client(project='demo-omi-transcript-recall', credentials=AnonymousCredentials())
    uid = 'transcript-qa-' + uuid4().hex
    collection = client.collection('users').document(uid).collection('conversations')
    try:
        yield client, uid, collection
    finally:
        for doc in collection.stream():
            doc.reference.delete()
        client.close()


def test_real_sdk_tied_cursor_resumes_after_deleted_bookmark_and_ignores_newer_arrival(owner):
    client, uid, collection = owner
    stamp = datetime(2026, 10, 27, tzinfo=timezone.utc)
    batch = client.batch()
    for i in range(55):
        batch.set(
            collection.document(f'c{i:03}'),
            {
                'id': f'c{i:03}',
                'created_at': stamp,
                'discarded': False,
                'is_locked': False,
                'transcript_segments': [
                    {'text': 'The invoice was 47 dollars.', 'is_user': False, 'start': 0, 'end': 3}
                ],
            },
        )
    batch.commit()

    def read(cursor=None, **bounds):
        return store.read_transcript_search_page(
            uid,
            'invoice',
            cursor=cursor,
            firestore_client=client,
            budget=ListReadBudget.for_request(None, route='qa', seconds=6, max_documents=50),
            **bounds,
        )

    first = read()
    assert [entry.conversation['id'] for entry in first.rows] == [f'c{i:03}' for i in range(54, 4, -1)]
    assert not first.exhausted
    collection.document('c005').delete()
    collection.document('new').set({'created_at': stamp + timedelta(seconds=1), 'discarded': False})
    rest = read(first.rows[-1].cursor)
    assert [entry.conversation['id'] for entry in rest.rows] == [f'c{i:03}' for i in range(4, -1, -1)]
    assert rest.exhausted
    assert not read(start_date=stamp + timedelta(days=1)).rows
