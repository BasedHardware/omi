"""GET /v1/conversations/{id}/transcripts must skip a partial provider segment doc, not 500.

The route's response_model is ``dict[str, List[TranscriptSegment]]`` (``text`` / ``is_user`` /
``start`` / ``end`` required), but ``get_conversation_transcripts_by_model`` returned the raw
Firestore dicts. #9563 made its sort tolerate a doc missing ``start``, yet that same legacy doc
(or one missing ``is_user``, or with a null ``text``) still failed response validation and
500'd every provider's transcript. The reader now parses each doc through
``database.read_boundary.parse_snapshots``, which skips a malformed doc and keeps the rest.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.conversations as conversations_db
import routers.conversations as conversations_router

PROVIDER_COLLECTIONS = (
    'deepgram_streaming',
    'soniox_streaming',
    'speechmatics_streaming',
    'fal_whisperx',
    'prerecorded',
)


def _segment(text, start):
    return {'text': text, 'is_user': False, 'start': start, 'end': start + 1.0}


def _client(monkeypatch, deepgram_docs):
    streams = {name: [] for name in PROVIDER_COLLECTIONS}
    streams['deepgram_streaming'] = [SimpleNamespace(to_dict=lambda doc=doc: doc) for doc in deepgram_docs]

    fake_db = MagicMock()
    fake_db.document.return_value = fake_db

    def collection(name):
        if name in streams:
            return MagicMock(stream=MagicMock(return_value=streams[name]))
        return fake_db

    fake_db.collection.side_effect = collection
    monkeypatch.setattr(conversations_db, 'db', fake_db)
    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', lambda uid, cid, **_: {'id': cid})

    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[conversations_router.auth.get_current_user_uid] = lambda: 'uid'
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    'partial',
    [
        {'text': 'no start', 'is_user': False, 'end': 2.0},
        {'text': 'no is_user', 'start': 0.5, 'end': 1.0},
        {'text': None, 'is_user': False, 'start': 0.5, 'end': 1.0},
    ],
    ids=['missing-start', 'missing-is_user', 'null-text'],
)
def test_partial_segment_is_skipped_and_the_rest_served(monkeypatch, partial):
    client = _client(monkeypatch, [_segment('second', 2.0), partial, _segment('first', 1.0)])

    response = client.get('/v1/conversations/c1/transcripts')

    assert response.status_code == 200
    body = response.json()
    assert [segment['text'] for segment in body['deepgram']] == ['first', 'second']
    assert body['soniox'] == body['speechmatics'] == body['whisperx'] == body['prerecorded'] == []


def test_valid_segments_are_served_sorted_by_start(monkeypatch):
    client = _client(monkeypatch, [_segment('b', 2.0), _segment('a', 1.0)])

    response = client.get('/v1/conversations/c1/transcripts')

    assert response.status_code == 200
    segments = response.json()['deepgram']
    assert [(s['text'], s['start'], s['end'], s['is_user']) for s in segments] == [
        ('a', 1.0, 2.0, False),
        ('b', 2.0, 3.0, False),
    ]
