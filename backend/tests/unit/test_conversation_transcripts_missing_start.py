"""get_conversation_transcripts_by_model must tolerate a segment doc missing 'start'.

GET /v1/conversations/{id}/transcripts sorted each provider's segments by ``x['start']``. A legacy
or partial segment doc missing 'start' raised KeyError and 500'd the whole transcripts response.
The sort now uses ``x.get('start', 0)``. database.conversations is light, so the test drives the
function directly with its db proxy patched to a fake chaining client.
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
    snap.to_dict.return_value = doc
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

    # Missing 'start' sorts as 0 (first); before the fix x['start'] raised KeyError here.
    assert result['deepgram'] == [{'text': 'no-start'}, {'start': 1.0, 'text': 'a'}, {'start': 2.0, 'text': 'b'}]
    # All four provider collections use the same fake stream, so each is sorted the same way.
    assert result['soniox'] == result['deepgram']
    assert result['speechmatics'] == result['deepgram']
    assert result['whisperx'] == result['deepgram']


class _CollectionPath:
    def __init__(self, streams, name=None):
        self._streams = streams
        self._name = name

    def collection(self, name):
        return _CollectionPath(self._streams, name)

    def document(self, _name):
        return self

    def stream(self):
        return iter([_snap(doc) for doc in self._streams.get(self._name, [])])


def test_transcripts_return_prerecorded_segments_sorted_by_start(monkeypatch):
    streams = {
        'deepgram_streaming': [{'start': 4.0, 'text': 'deepgram'}],
        'soniox_streaming': [{'start': 3.0, 'text': 'soniox'}],
        'speechmatics_streaming': [{'start': 2.0, 'text': 'speechmatics'}],
        'fal_whisperx': [{'start': 5.0, 'text': 'legacy'}],
        'prerecorded': [
            {'start': 3.0, 'text': 'later'},
            {'start': 1.0, 'text': 'earlier'},
        ],
    }
    monkeypatch.setattr(conversations_db, 'db', _CollectionPath(streams))

    result = conversations_db.get_conversation_transcripts_by_model('u1', 'c1')

    assert result['prerecorded'] == [
        {'start': 1.0, 'text': 'earlier'},
        {'start': 3.0, 'text': 'later'},
    ]
