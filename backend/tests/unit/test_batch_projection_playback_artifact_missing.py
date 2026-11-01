"""A staged batch object that is gone closes follow-up playback instead of retrying forever."""

from datetime import datetime, timezone
from types import SimpleNamespace

from google.api_core.exceptions import NotFound
import pytest

from database import conversations as conversations_db
from utils.batch_pipeline import projection
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.sync import merge_audio

CAPTURE_AT = 1_790_000_000.0
ITEM = WorkItem(
    segment_id='seg-1',
    owner_id='owner-1',
    capture_at=CAPTURE_AT,
    audio_uri='gs://bucket/owner/audio/seg-1/' + '0' * 32 + '.enc#1',
    duration_seconds=30.0,
    priority=Priority.FRESH,
    unit_kind='capture_span',
    conversation_id='conv-1',
    privacy_generation=0,
)
BINDING = SimpleNamespace(owner_id='owner-1', data_protection_level='standard')
RECEIPT = {'speaker_scope': 'sync:seg-1', 'incoming_segment_count': 1}


class _Doc:
    def __init__(self, row):
        self.row = row

    def get(self):
        return SimpleNamespace(to_dict=lambda: self.row)

    def collection(self, _name):
        return self

    def document(self, _key):
        return self


def _projector(row, fetch_audio):
    projector = projection.Projector.__new__(projection.Projector)
    projector.store = SimpleNamespace(client=SimpleNamespace(collection=lambda _name: _Doc(row)))
    projector.fetch_audio = fetch_audio
    return projector


@pytest.fixture
def row(monkeypatch):
    started = datetime.fromtimestamp(CAPTURE_AT, timezone.utc)
    segments = [{'speaker_id_scope': 'sync:seg-1', 'start': 1.0, 'end': 2.0, 'text': 'x'}]
    monkeypatch.setattr(conversations_db, 'decode_transcript_segments_verified', lambda *_args: segments)
    return {'started_at': started, 'transcript_segments': b'', 'transcript_segments_compressed': False}


def _missing(_item):
    raise NotFound('gone')


def test_missing_staged_object_skips_playback_and_counts(row, monkeypatch, caplog):
    stored = []
    monkeypatch.setattr(merge_audio, 'store_intake_audio', lambda *args: stored.append(args))
    before = projection.ARTIFACT_MISSING.labels(site='playback')._value.get()

    assert _projector(row, _missing).persist_playback(ITEM, BINDING, 'conv-1', RECEIPT) is None

    assert stored == []
    assert projection.ARTIFACT_MISSING.labels(site='playback')._value.get() == before + 1
    assert 'event=batch_artifact_missing site=playback outcome=skipped' in caplog.text
    # The closed log line names no owner, conversation, segment or object.
    assert 'owner-1' not in caplog.text and 'conv-1' not in caplog.text and 'seg-1' not in caplog.text


def test_other_fetch_errors_still_retry(row, monkeypatch):
    monkeypatch.setattr(merge_audio, 'store_intake_audio', lambda *args: pytest.fail('must not store'))

    def flaky(_item):
        raise TimeoutError('transient')

    with pytest.raises(TimeoutError):
        _projector(row, flaky).persist_playback(ITEM, BINDING, 'conv-1', RECEIPT)


def test_present_object_still_stores_playback(row, monkeypatch):
    stored = []
    monkeypatch.setattr(merge_audio, 'store_intake_audio', lambda *args: stored.append(args))

    _projector(row, lambda _item: b'RIFF-wav').persist_playback(ITEM, BINDING, 'conv-1', RECEIPT)

    assert len(stored) == 1 and stored[0][2] == b'RIFF-wav'
