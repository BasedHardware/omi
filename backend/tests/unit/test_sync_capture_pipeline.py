"""Real VAD export and process_segment keep decoded capture coverage."""

from pathlib import Path
import threading
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import intake, conversations
from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes
from utils.sync.capture import CaptureSegments


@pytest.fixture
def pipeline():
    from models import conversation, conversation_enums, transcript_segment
    from pydub import AudioSegment
    from utils.conversations import deterministic_minimum

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
def test_vad_exports_coverage_and_quiet_capture_is_persisted_without_stt(pipeline, tmp_path, quiet):
    module, store = pipeline
    original = tmp_path / '1700000000.wav'
    module.AudioSegment.silent(duration=70000).export(original, format='wav')
    module.vad_is_empty = lambda *a, **kw: [] if quiet else [{'start': 20, 'end': 23}]
    paths = CaptureSegments()
    module.retrieve_vad_segments(str(original), paths, [])
    path = next(iter(paths))
    assert paths.windows[path] == (1700000000, 1700000070)
    assert (path in paths.silent) == quiet
    response = {'new_memories': set(), 'updated_memories': set()}
    errors = []
    outcome = {}
    assert module.process_segment(
        path,
        'u',
        response,
        threading.Lock(),
        errors,
        capture_window=paths.windows[path],
        capture_only=quiet,
        deferred_outcome=outcome,
    )
    assert errors == []
    row = conversations(store)[0]
    assert row['finished_at'].timestamp() == 1700000070
    assert row['started_at'].timestamp() == 1700000000
    if quiet:
        module.prerecorded.assert_not_called()
        assert row['sync_relevance'] == 'review'
        assert outcome['outcome'].value == 'expected_silence'
        assert not response.get('_merged')
    else:
        assert row['transcript_segments'][0]['start'] == 20
        assert outcome['outcome'].value == 'success'
