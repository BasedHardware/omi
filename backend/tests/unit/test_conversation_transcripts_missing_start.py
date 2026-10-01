"""get_conversation_transcripts_by_model must tolerate a segment doc missing 'start'.

GET /v1/conversations/{id}/transcripts sorted each provider's segments by ``x['start']``. A legacy
or partial segment doc missing 'start' raised KeyError and 500'd the whole transcripts response.
Each doc is now parsed at the read boundary, which skips such a doc. database.conversations is
light, so the test drives the function directly with its db proxy patched to a fake chaining client.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

from unittest.mock import MagicMock

import database.conversations as conversations_db


def _snap(doc):
    snap = MagicMock()
    # Fill the other required TranscriptSegment fields so only the fields under test decide validity.
    snap.to_dict.return_value = {'is_user': False, 'end': 9.0, **doc}
    return snap


def test_transcripts_tolerate_segment_missing_start(monkeypatch):
    # deepgram has a good doc plus a legacy doc missing 'start'; the sort must not KeyError.
    docs = [_snap({'start': 2.0, 'text': 'b'}), _snap({'text': 'no-start'}), _snap({'start': 1.0, 'text': 'a'})]
    fake_db = MagicMock()
    fake_db.collection.return_value = fake_db
    fake_db.document.return_value = fake_db
    fake_db.stream.return_value = docs
    monkeypatch.setattr(conversations_db, 'db', fake_db)

    result = conversations_db.get_conversation_transcripts_by_model('u1', 'c1')

    # The doc missing 'start' is skipped; before the fix x['start'] raised KeyError here.
    assert [s.text for s in result['deepgram']] == ['a', 'b']
    # All four provider collections use the same fake stream, so each is sorted the same way.
    for provider in ('soniox', 'speechmatics', 'whisperx'):
        assert [s.text for s in result[provider]] == ['a', 'b']


def test_transcripts_return_prerecorded_distinct_and_sorted(monkeypatch):
    # Each provider collection gets its own stream; prerecorded must be read from its own
    # collection, returned under its own key, and sorted independently.
    prerecorded_docs = [
        _snap({'start': 3.0, 'text': 'third'}),
        _snap({'start': 1.0, 'text': 'first'}),
        _snap({'start': 2.0, 'text': 'second'}),
    ]
    deepgram_docs = [_snap({'start': 0.5, 'text': 'deepgram'})]
    streams = {
        'prerecorded': prerecorded_docs,
        'deepgram_streaming': deepgram_docs,
        'soniox_streaming': [],
        'speechmatics_streaming': [],
        'fal_whisperx': [],
    }

    fake_db = MagicMock()
    fake_db.document.return_value = fake_db

    def fake_collection(name):
        if name in streams:
            ref = MagicMock()
            ref.stream.return_value = streams[name]
            return ref
        return fake_db

    fake_db.collection.side_effect = fake_collection
    monkeypatch.setattr(conversations_db, 'db', fake_db)

    result = conversations_db.get_conversation_transcripts_by_model('u1', 'c1')

    assert [s.text for s in result['prerecorded']] == ['first', 'second', 'third']
    assert [s.text for s in result['deepgram']] == ['deepgram']
    # prerecorded must not bleed into the legacy keys.
    assert result['whisperx'] == []
    assert result['soniox'] == []
    assert result['speechmatics'] == []
