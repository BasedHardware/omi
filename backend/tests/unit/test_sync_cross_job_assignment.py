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
        'status': 'completed',
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


@pytest.mark.parametrize('reverse', [False, True])
def test_independent_chunk_speakers_survive_merge_and_retry(reverse):
    store = StrictFirestore()
    chunks = [chunk('a', 1000), chunk('b', 1060)]
    for item in chunks:
        item['transcript_segments'][0].update(speaker='SPEAKER_00', speaker_id_scope='sync:' + item['id'])
    for item in reversed(chunks) if reverse else chunks:
        result, _, _ = intake(store, item)
    by_scope = {s['speaker_id_scope']: s['speaker_id'] for s in result['transcript_segments']}
    assert len(set(by_scope.values())) == 2
    for item in chunks:
        result, _, survivors = intake(store, item)
        assert not survivors
        assert {s['speaker_id_scope']: s['speaker_id'] for s in result['transcript_segments']} == by_scope
    assert all(s['speaker'] == 'SPEAKER_00' for s in result['transcript_segments'])


def test_sync_appended_to_live_target_does_not_reuse_live_speaker_id():
    store = StrictFirestore()
    live = chunk('live', 1000)
    live['transcript_segments'][0].update(speaker='SPEAKER_00', speaker_id=98)
    intake(store, live)
    wal = chunk('wal', 1060)
    wal['transcript_segments'][0].update(speaker='SPEAKER_00', speaker_id_scope='sync:content')
    result, _, _ = intake(store, wal, target_id='live')
    assert [s['speaker_id'] for s in result['transcript_segments']] == [98, 100]


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
    assert conversations(store)[0]['id'] in {'0', '1'}
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
    assert earlier['id'] == later['id'] == 'later'
    assert earlier['sync_merged_from'] == []
    assert ('users', 'u', 'conversations', 'earlier') not in store.rows
    assert not store.rows[('users', 'u', 'conversations', 'later')].get('deleted')
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
    assert review['discarded'] is True
    assert review['transcript_segments'][0]['text'] == 'Mm-hmm. Ha ha ha.'
    promoted, created, _ = intake(store, chunk('meaningful', 1060, 'Please call the doctor tomorrow.'))
    assert not created and promoted['id'] == review['id']
    assert promoted['sync_relevance'] == 'keep'
    assert promoted['discarded'] is False


@pytest.mark.parametrize('text', ['Help!', 'Yes', 'No', '嗯，请明天联系我', 'I love you', 'Mm 1234', '1234', ''])
def test_ambiguous_or_meaningful_content_fails_open(text):
    assert not needs_fragment_review(chunk('a', 1000, text)['transcript_segments'])


@pytest.mark.parametrize('text', ['Help!', 'No', 'Yes', 'Call me', '明天见', '1234'])
def test_subsecond_meaningful_speech_is_kept(text):
    short = chunk('short', 1000, text)
    short['transcript_segments'][0]['end'] = 0.24
    short['finished_at'] = datetime.fromtimestamp(1000.24, timezone.utc)
    result, _, _ = intake(StrictFirestore(), short)
    assert result['sync_relevance'] == 'keep'
    assert result['discarded'] is False


def test_separated_fillers_are_hidden_without_deleting_transcript_or_audio():
    store = StrictFirestore()
    short = chunk('filler', 1000, 'Mm-hmm.')
    short['transcript_segments'][0]['end'] = 0.24
    short['transcript_segments'].append({'start': 65.0, 'end': 65.32, 'text': 'Hmm.', 'speaker_id': 0})
    short['finished_at'] = datetime.fromtimestamp(1065.32, timezone.utc)
    short['audio_files'] = [{'id': 'retained-audio'}]
    result, _, _ = intake(store, short)
    assert result['discarded'] is True
    assert len(result['transcript_segments']) == 2
    assert result['audio_files'] == short['audio_files']
    assert not result.get('deleted')


@pytest.mark.parametrize(
    'curation',
    [
        {'user_title': 'Saved note'},
        {'starred': True},
        {'folder_user_set': True},
        {'has_photos': True},
        {'visibility': 'public'},
        {'sync_relevance_user_kept': True},
    ],
)
def test_curated_filler_is_not_automatically_hidden(curation):
    short = chunk('filler', 1000, 'Mm-hmm.')
    short.update(curation)
    result, _, _ = intake(StrictFirestore(), short)
    assert result['discarded'] is False


def test_explicitly_restored_fragment_stays_kept_when_live_target_gets_more_filler():
    store = StrictFirestore()
    intake(store, chunk('filler', 1000, 'Mm-hmm.'))
    stored = store.rows[('users', 'u', 'conversations', 'filler')]
    stored.update(discarded=False, sync_relevance='keep', sync_relevance_user_kept=True)
    result, _, _ = intake(store, chunk('more', 1060, 'Hmm.'), target_id='filler')
    assert result['discarded'] is False
    assert result['sync_relevance'] == 'keep'
    assert result['sync_relevance_user_kept'] is True


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
        pipeline.identify_speakers_for_segments = lambda *a, **kw: None
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


def test_bridge_allocates_donor_clusters_without_colliding_with_survivor():
    store = StrictFirestore()
    a, b = chunk('a', 1000), chunk('b', 1240)
    for item in [a, b]:
        item['transcript_segments'][0].update(speaker='SPEAKER_00', speaker_id_scope='sync:' + item['id'])
        intake(store, item)
    result, _, _ = intake(store, chunk('bridge', 1120))
    mapped = {
        s.get('speaker_id_scope'): s['speaker_id'] for s in result['transcript_segments'] if s.get('speaker_id_scope')
    }
    assert mapped['sync:a'] != mapped['sync:b']
    replay, _, _ = intake(store, b)
    assert {
        s.get('speaker_id_scope'): s['speaker_id'] for s in replay['transcript_segments'] if s.get('speaker_id_scope')
    } == mapped


def test_labeled_sync_row_receives_later_same_capture_chunk_without_becoming_a_donor():
    store = StrictFirestore()
    saved, _, _ = intake(store, chunk('manual', 1000))
    saved['manual_speaker_assignments'] = {
        'generation': 1,
        'speakers': {'0': {'generation': 1, 'person_id': 'new', 'is_user': False}},
    }
    store.rows[('users', 'u', 'conversations', 'manual')] = saved
    result, created, _ = intake(store, chunk('next', 1060))
    assert not created and result['id'] == 'manual'
    assert len(result['transcript_segments']) == 2
    assert all(segment.get('person_id') == 'new' for segment in result['transcript_segments'])
    assert not store.rows[('users', 'u', 'conversations', 'manual')].get('deleted')
    assert ('users', 'u', 'conversations', 'next') not in store.rows


@pytest.mark.parametrize('explicit', [False, True])
def test_labeled_donor_does_not_extend_or_bridge_survivor(explicit):
    store = StrictFirestore()
    intake(store, chunk('a', 1000))
    intake(store, chunk('b', 1240))
    for cid in ('a', 'b'):
        store.rows[('users', 'u', 'conversations', cid)]['manual_speaker_assignments'] = {
            'segments': {cid: {'generation': 1, 'person_id': cid, 'is_user': False}}
        }
    donor = deepcopy(store.rows[('users', 'u', 'conversations', 'b')])
    result, _, _ = intake(store, chunk('bridge', 1120), target_id='a' if explicit else None)
    assert result['id'] == 'a'
    assert result['finished_at'] == chunk('bridge', 1120)['finished_at']
    assert result['sync_merged_from'] == []
    assert store.rows[('users', 'u', 'conversations', 'b')] == donor


def test_labeled_retry_retarget_is_terminal_without_writes():
    from utils.sync.assignment_errors import SyncAssignmentSuperseded

    store = StrictFirestore()
    intake(store, chunk('a', 1000))
    intake(store, chunk('b', 1240))
    store.rows[('users', 'u', 'conversations', 'a')]['manual_speaker_assignments'] = {'generation': 1}
    before = deepcopy(store.rows)
    with pytest.raises(SyncAssignmentSuperseded, match='manual speaker'):
        intake(store, chunk('a', 1000), target_id='b')
    assert store.rows == before


@pytest.mark.parametrize('donor_start,target_start', [(1000, 1240), (1240, 1000)])
def test_unlabeled_explicit_target_excludes_labeled_donor_extent(donor_start, target_start):
    store = StrictFirestore()
    intake(store, chunk('donor', donor_start))
    intake(store, chunk('target', target_start))
    store.rows[('users', 'u', 'conversations', 'donor')]['manual_speaker_assignments'] = {'generation': 1}
    before = deepcopy(store.rows[('users', 'u', 'conversations', 'donor')])
    result, _, _ = intake(store, chunk('bridge', 1120), target_id='target')
    assert result['id'] == 'target'
    assert result['started_at'] == chunk('expected', min(target_start, 1120))['started_at']
    assert result['finished_at'] == chunk('expected', max(target_start, 1120))['finished_at']
    assert store.rows[('users', 'u', 'conversations', 'donor')] == before
