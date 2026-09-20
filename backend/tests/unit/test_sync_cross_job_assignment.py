"""Separate sync workers converge through the production atomic intake seam.

StrictFirestore checks read-before-write semantics. Its serialized runner below
models successful transaction commits, not Firestore contention/retry internals;
real contention still needs emulator verification (HANDOFF.md).
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import threading
from unittest.mock import MagicMock

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.sync.assignment import assign_in_transaction, needs_fragment_review


@pytest.fixture(scope='module', autouse=True)
def load_dependencies():
    # Imports belong to fixture setup, not the fast-unit behavior timing budget.
    from database import conversations
    from models import conversation, conversation_enums, transcript_segment
    from utils.conversations import deterministic_minimum
    from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes
    from tests.unit.test_conversation_discard_revival import _persist


def chunk(key, timestamp, text='A narrated explanation of this chapter.', device='pendant'):
    return {
        'id': key,
        'started_at': datetime.fromtimestamp(timestamp, timezone.utc),
        'finished_at': datetime.fromtimestamp(timestamp + 9.5, timezone.utc),
        'source': 'omi',
        'client_device_id': device,
        'discarded': False,
        'transcript_segments': [{'start': 0.0, 'end': 9.5, 'text': text, 'speaker_id': 0, 'is_user': False}],
    }


def intake(store, incoming, *, candidate_id=None, target_id=None):
    # Two independent clients share only their durable store, never a job lock.
    with store.lock:
        return assign_in_transaction(
            store.transaction(),
            store.collection('users').document('u'),
            incoming,
            candidate_id=candidate_id,
            target_id=target_id,
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda payload: None,
        )


def conversations(store):
    return [value for key, value in store.rows.items() if key[2] == 'conversations' and not value.get('deleted')]


def test_two_jobs_with_stale_empty_lookup_converge():
    store = StrictFirestore()
    barrier = threading.Barrier(2)

    def job(incoming):
        candidate = None  # both lookups happened before either commit
        barrier.wait(timeout=5)
        return intake(store, incoming, candidate_id=candidate)

    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(job, chunk(str(i), 1000 + i * 60)) for i in range(2)]
        results = [job.result(timeout=5) for job in jobs]
    assert len(conversations(store)) == 1
    assert conversations(store)[0]['id'] == '0'
    assert all(result[0]['id'] in {'0', '1'} for result in results)
    assert len(conversations(store)[0]['transcript_segments']) == 2


def test_seventy_minutes_of_identical_narration_is_one_recording():
    store = StrictFirestore()
    for i in range(70):
        intake(store, chunk(str(i), 1000 + 60 * i), candidate_id=None)
    rows = conversations(store)
    assert len(rows) == 1
    assert len(rows[0]['transcript_segments']) == 70
    assert rows[0]['sync_relevance'] == 'keep'
    assert rows[0]['discarded'] is False


def test_reverse_order_retry_and_deleted_target():
    store = StrictFirestore()
    later, _, _ = intake(store, chunk('later', 1060))
    earlier, _, _ = intake(store, chunk('earlier', 1000))
    assert earlier['id'] == 'earlier'
    assert store.rows[('users', 'u', 'conversations', later['id'])]['sync_merged_into'] == earlier['id']
    assert [s['start'] for s in earlier['transcript_segments']] == [0, 60]
    retried, created, survivors = intake(store, chunk('retry', 1060))
    assert not created and not survivors and len(retried['transcript_segments']) == 2
    store.rows[('users', 'u', 'conversations', earlier['id'])]['deleted'] = True
    replacement, created, _ = intake(store, chunk('replacement', 1120), target_id=earlier['id'])
    assert created and replacement['id'] != earlier['id']


def test_gap_and_known_devices_keep_independent_recordings():
    store = StrictFirestore()
    intake(store, chunk('a', 1000))
    intake(store, chunk('b', 1060, device='other'))
    intake(store, chunk('c', 2000))
    assert len(conversations(store)) == 3


@pytest.mark.parametrize('is_user,speaker_id', [(False, 0), (True, 1), (None, 99)])
def test_filler_is_preserved_and_promoted_regardless_of_speakers(is_user, speaker_id):
    store = StrictFirestore()
    short = chunk('filler', 1000, 'Mm-hmm. Ha ha ha.')
    short['transcript_segments'][0].update(is_user=is_user, speaker_id=speaker_id)
    review, _, _ = intake(store, short)
    assert review['sync_relevance'] == 'review'
    assert review['discarded'] is False
    assert review['transcript_segments'][0]['text'] == 'Mm-hmm. Ha ha ha.'
    promoted, created, _ = intake(store, chunk('meaningful', 1060, 'Please call the doctor tomorrow.'))
    assert not created and promoted['id'] == review['id']
    assert promoted['sync_relevance'] == 'keep'


@pytest.mark.parametrize('text', ['Help!', 'Yes', 'No', '嗯，请明天联系我', 'I love you', 'Mm 1234', '1234', ''])
def test_ambiguous_or_meaningful_content_fails_open(text):
    assert not needs_fragment_review(chunk('a', 1000, text)['transcript_segments'])


def test_real_process_segment_two_independent_job_responses(monkeypatch):
    from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
    from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes
    from models import conversation, conversation_enums, transcript_segment
    from utils.conversations import deterministic_minimum

    fakes = _build_pipeline_fakes()
    fakes.update(
        {
            'models.conversation': conversation,
            'models.conversation_enums': conversation_enums,
            'models.transcript_segment': transcript_segment,
            'utils.conversations.deterministic_minimum': deterministic_minimum,
        }
    )
    lifecycle = AutoMockModule('utils.conversations.lifecycle')
    fakes['utils.conversations.lifecycle'] = lifecycle
    bridge = AutoMockModule('utils.sync.bridge')
    bridge.finish_sync_bridges = lambda uid, cid: cid
    fakes['utils.sync.bridge'] = bridge
    with stub_modules(fakes):
        pipeline = load_module_fresh(
            'utils.sync.pipeline', Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py'
        )
        store = StrictFirestore()
        barrier = threading.Barrier(2)
        pipeline.get_syncing_file_temporal_signed_url = lambda path: path
        pipeline.schedule_syncing_temporal_file_deletion = lambda path: None
        pipeline.get_prerecorded_service = lambda language: ('test', None, 'test')
        pipeline.prerecorded = lambda *a, **kw: ([{}], 'en')
        pipeline.postprocess_words = lambda *a: [
            transcript_segment.TranscriptSegment(
                text='This narrated chapter describes our history.',
                start=0,
                end=9.5,
                speaker='SPEAKER_00',
                is_user=False,
            )
        ]
        pipeline.identify_speakers_for_segments = lambda *a: None
        pipeline.get_timestamp_from_path = float
        pipeline.get_wav_duration = lambda path: 60

        def expose_failure(error, **kwargs):
            raise error

        pipeline.failure_from_exception = expose_failure

        def stale_lookup(*args):
            barrier.wait(timeout=5)
            return None

        pipeline.get_closest_conversation_to_timestamps = stale_lookup
        lifecycle.ingest_sync_conversation = lambda uid, incoming, **kw: intake(store, incoming, **kw)
        responses = [{'new_memories': set(), 'updated_memories': set()} for _ in range(2)]
        errors = [[], []]
        with ThreadPoolExecutor(2) as pool:
            jobs = [
                pool.submit(
                    pipeline.process_segment, str(1000 + i * 60), 'u', responses[i], threading.Lock(), errors[i]
                )
                for i in range(2)
            ]
            assert all(job.result(timeout=5) for job in jobs), errors
        assert errors == [[], []]
        assert len(conversations(store)) == 1
        assert len(conversations(store)[0]['transcript_segments']) == 2
        # Responses can name pre-bridge IDs; durable redirects converge to one row.
        assert len(conversations(store)) == 1

        pipeline.conversations_db.get_conversation = lambda *a: {
            'sync_relevance': 'review',
            'transcript_segments': chunk('a', 1000, 'Mm-hmm')['transcript_segments'],
        }
        pipeline.process_conversation = MagicMock()
        pipeline._reprocess_conversation_after_update('u', 'a', 'en')
        pipeline.process_conversation.assert_not_called()

        pipeline._reprocess_conversation_after_update = MagicMock()
        pipeline._reprocess_merged_conversations('u', {'_merged': {'new': 'en', 'old': 'en'}, 'new_memories': {'new'}})
        calls = pipeline._reprocess_conversation_after_update.call_args_list
        assert [tuple(call.args) for call in calls] == [('u', 'new', 'en'), ('u', 'old', 'en')]


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_firestore_adapter_roundtrips_encoded_transcripts(monkeypatch, level):
    from database import conversations as db

    store = StrictFirestore()
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    first = chunk('first', 1000)
    first['data_protection_level'] = level
    second = chunk('second', 1060)
    second['data_protection_level'] = level
    result, created, _ = db.assign_sync_conversation('u', first, firestore_client=store)
    assert created
    result, created, _ = db.assign_sync_conversation('u', second, firestore_client=store)
    assert not created and result['id'] == 'first'
    raw = conversations(store)[0]
    assert isinstance(raw['transcript_segments'], str if level == 'enhanced' else bytes)
    decoded = db._decode_transcript_segments_strict('u', raw['transcript_segments'], True)
    assert len(decoded) == 2
    assert [segment['start'] for segment in decoded] == [0, 60]


def test_stale_processor_cannot_erase_new_chunks_or_remove_search_row(monkeypatch):
    from database import conversations as db
    from tests.unit.test_conversation_discard_revival import _persist

    sync = MagicMock()
    remove = MagicMock()
    monkeypatch.setattr(db, '_sync_conversation_search_index', sync)
    monkeypatch.setattr(db, '_delete_conversation_search_index', remove)
    persisted, ref = _persist(monkeypatch, {'sync_content_revision': 2, 'transcript_segments': ['retained']})
    assert not persisted and ref.written is None
    sync.assert_called_once()
    remove.assert_not_called()
