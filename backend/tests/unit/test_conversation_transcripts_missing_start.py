"""get_conversation_transcripts_by_model must tolerate a segment doc missing 'start'.

GET /v1/conversations/{id}/transcripts sorted each provider's segments by ``x['start']``. A legacy
or partial segment doc missing 'start' raised KeyError and 500'd the whole transcripts response.
The sort now uses ``x.get('start', 0)``. Migrated to the WP2 storage port: the test injects a
FakeDocumentStore with the provider subcollections seeded.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

import database.conversations as conversations_db
from tests.store_fakes import FakeDocumentStore


def test_transcripts_tolerate_segment_missing_start(monkeypatch):
    # Each provider has a good doc plus a legacy doc missing 'start'; the sort must not KeyError.
    docs = [{'start': 2.0, 'text': 'b'}, {'text': 'no-start'}, {'start': 1.0, 'text': 'a'}]
    store = FakeDocumentStore()
    base = 'users/u1/conversations/c1'
    for model in ('deepgram_streaming', 'soniox_streaming', 'speechmatics_streaming', 'fal_whisperx'):
        for i, doc in enumerate(docs):
            store.set(f'{base}/{model}/seg{i}', doc)
    monkeypatch.setattr(conversations_db, '_store', lambda: store)

    result = conversations_db.get_conversation_transcripts_by_model('u1', 'c1')

    # Missing 'start' sorts as 0 (first); before the fix x['start'] raised KeyError here.
    assert result['deepgram'] == [{'text': 'no-start'}, {'start': 1.0, 'text': 'a'}, {'start': 2.0, 'text': 'b'}]
    assert result['soniox'] == result['deepgram']
    assert result['speechmatics'] == result['deepgram']
    assert result['whisperx'] == result['deepgram']
