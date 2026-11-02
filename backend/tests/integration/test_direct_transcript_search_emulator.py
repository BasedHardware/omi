"""Real Firestore SDK cursor/query verification; loopback emulator only.

FIRESTORE_EMULATOR_HOST=127.0.0.1:18539 PYTHONPATH=backend \
  backend/.venv/bin/python -m pytest backend/tests/integration/test_direct_transcript_search_emulator.py -q
"""

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
import pytest

from database import conversations, review_store, transcript_search as store
from database.firestore_retry import FIRESTORE_NO_RETRY
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
        for doc in client.collection('users').document(uid).collection('transcript_corrections').stream():
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


@pytest.mark.parametrize('exact', [False, True], ids=['scan', 'exact'])
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_real_sdk_projects_encrypted_corrections_with_the_original_read_budget(owner, monkeypatch, exact, level):
    client, uid, collection = owner
    stamp = datetime(2026, 10, 27, tzinfo=timezone.utc)
    captured = {
        'id': 'corrected',
        'created_at': stamp,
        'discarded': False,
        'data_protection_level': level,
        'has_transcript_corrections': True,
        'transcript_segments': [dict(id='s1', text='The invoice was 47 dollars.', start=0, end=3, is_user=False)],
    }
    collection.document('corrected').set(conversations.encode_conversation_for_write(uid, captured, level))
    client.collection('users').document(uid).collection('transcript_corrections').document('corrected').set(
        review_store.encode_doc(
            uid,
            {
                'source': [
                    dict(
                        undone=False,
                        segment_index=0,
                        segment_id='s1',
                        start=0,
                        kind='transcript',
                        before='The invoice was 47 dollars.',
                        after='The invoice was 83 dollars.',
                    )
                ]
            },
        )
    )
    real_get = DocumentReference.get
    calls = []

    def observed_get(ref, *args, **kwargs):
        if ref.path == f'users/{uid}/transcript_corrections/corrected':
            calls.append(kwargs)
        return real_get(ref, *args, **kwargs)

    monkeypatch.setattr(DocumentReference, 'get', observed_get)
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(review_store, 'client', lambda: client)
    budget = ListReadBudget.for_request(None, route='qa', seconds=4, max_documents=50)
    if exact:
        result = conversations.get_conversations_by_id_without_photos(uid, ['corrected'], read_budget=budget)
    else:
        page = store.read_transcript_search_page(uid, 'invoice', firestore_client=client, budget=budget)
        assert page.exhausted
        result = [entry.conversation for entry in page.rows]
    assert result[0]['transcript_segments'][0]['text'] == 'The invoice was 83 dollars.'
    assert result[0]['transcript_segments'][0]['original_text'] == 'The invoice was 47 dollars.'
    assert len(calls) == 1 and 0 < calls[0]['timeout'] < 4
    assert calls[0]['retry'] is FIRESTORE_NO_RETRY
    assert budget.docs_scanned == 2
