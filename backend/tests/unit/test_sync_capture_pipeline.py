"""Real VAD export and process_segment preserve speech extents; silence creates nothing."""

from pathlib import Path
import threading
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import intake, conversations
from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes
from utils.sync.capture import chunk_identity


@pytest.fixture
def pipeline():
    from models import conversation, conversation_enums, transcript_segment
    from pydub import AudioSegment
    from utils.conversations import deterministic_minimum
    from utils.sync import bridge as real_bridge

    fakes = _build_pipeline_fakes()
    lifecycle = AutoMockModule('utils.conversations.lifecycle')
    bridge = AutoMockModule('utils.sync.bridge')
    bridge.finish_sync_bridges = lambda uid, cid: cid
    fakes.update(
        {
            'models.conversation': conversation,
            'models.conversation_enums': conversation_enums,
            'models.transcript_segment': transcript_segment,
            'utils.conversations.deterministic_minimum': deterministic_minimum,
            'utils.conversations.lifecycle': lifecycle,
            'utils.sync.bridge': bridge,
        }
    )
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.sync.pipeline', Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py'
        )
        module.real_bridge = real_bridge
        module.AudioSegment = AudioSegment
        module.get_timestamp_from_path = lambda path: float(Path(path).stem)
        module.get_syncing_file_temporal_signed_url = lambda path: path
        module.schedule_syncing_temporal_file_deletion = lambda path: None
        module.get_prerecorded_service = lambda language: ('test', None, 'test')
        module.identify_speakers_for_segments = lambda *a: None
        module.get_closest_conversation_to_timestamps = lambda *a: None
        module.prerecorded = MagicMock(return_value=([{}], 'en'))
        module.postprocess_words = lambda *a: [
            transcript_segment.TranscriptSegment(text='Keep the capture.', start=0, end=3, is_user=False)
        ]
        store = StrictFirestore()
        lifecycle.ingest_sync_conversation = lambda uid, row, **kw: intake(store, row, **kw)
        yield module, store


@pytest.mark.parametrize('quiet', [False, True])
def test_vad_preserves_speech_origin_and_exports_nothing_for_silence(pipeline, tmp_path, quiet):
    module, store = pipeline
    original = tmp_path / '1700000000.wav'
    module.AudioSegment.silent(duration=70000).export(original, format='wav')
    module.vad_is_empty = lambda *a, **kw: [] if quiet else [{'start': 20, 'end': 23}]
    paths = set()
    module.retrieve_vad_segments(str(original), paths, [])
    if quiet:
        assert paths == set() and not conversations(store)
        module.prerecorded.assert_not_called()
        assert list(tmp_path.iterdir()) == [original]
        return
    path = next(iter(paths))
    assert Path(path).stem == '1700000020.0'
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert module.process_segment(path, 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
    assert errors == []
    row = conversations(store)[0]
    assert row['finished_at'].timestamp() == 1700000023
    assert row['started_at'].timestamp() == 1700000020
    assert row['transcript_segments'][0]['start'] == 0
    assert row['id'] == chunk_identity('u', 'omi', None, False, 1700000020)
    assert outcome['outcome'].value == 'success'


@pytest.mark.parametrize('empty_words', [True, False])
def test_empty_transcription_creates_nothing_and_cannot_bridge(pipeline, empty_words):
    module, store = pipeline
    if empty_words:
        module.prerecorded.return_value = ([], 'en')
    else:
        module.postprocess_words = lambda *a: []
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment('1700000000.wav', 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
        is False
    )
    assert not store.rows and not errors
    assert response == {'new_memories': set(), 'updated_memories': set()}
    assert outcome['outcome'].value == 'expected_silence' and not outcome['retryable']


def test_bridge_finishes_once_at_process_segment_completion(pipeline, monkeypatch):
    module, store = pipeline
    bridge = module.real_bridge
    module.finish_sync_segment = bridge.finish_sync_segment
    finish = MagicMock(side_effect=lambda uid, cid, **kw: cid)
    monkeypatch.setattr(bridge, 'finish_sync_bridges', finish)
    response = {'new_memories': set(), 'updated_memories': set()}
    for timestamp in (1000, 1240, 1120):
        assert module.process_segment(f'{timestamp}.wav', 'u', response, threading.Lock(), [])
    assert len(conversations(store)) == 1
    finish.assert_called_once_with('u', conversations(store)[0]['id'], audio_source_id=None)


@pytest.mark.parametrize('condition', ['anchor_deleted', 'lineage_deleted', 'user_managed', 'provenance', 'cycle'])
def test_assignment_outcomes_through_process_segment(pipeline, condition):
    from copy import deepcopy
    from tests.unit.test_sync_cross_job_assignment import chunk

    module, store = pipeline
    cid = chunk_identity('u', 'omi', None, False, 1000)
    row = chunk(cid, 1000, device=None)
    row['sync_content_revision'] = 1
    target = None
    if condition == 'anchor_deleted':
        row['deleted'] = True
    elif condition == 'lineage_deleted':
        row.update(deleted=True, sync_merged_into='survivor')
        store.rows[('users', 'u', 'conversations', 'survivor')] = dict(row, id='survivor', sync_merged_into=None)
    elif condition == 'user_managed':
        row['user_title'] = 'Preserve my edit'
    elif condition == 'cycle':
        row.update(deleted=True, sync_merged_into=cid)
    else:
        row = chunk('live', 1000, device='another-device')
        cid = target = 'live'
    store.rows[('users', 'u', 'conversations', cid)] = row
    before = deepcopy(store.rows)
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment(
            '1000.wav', 'u', response, threading.Lock(), errors, target_conversation_id=target, deferred_outcome=outcome
        )
        is False
    )
    assert store.rows == before
    assert response == {'new_memories': set(), 'updated_memories': set()}
    if condition in ('provenance', 'cycle'):
        assert errors == ['stt_upstream_error']
        assert outcome['outcome'].value == 'upstream_error' and outcome['retryable']
    else:
        assert errors == []
        assert outcome['outcome'].value == 'success' and not outcome['retryable']
