"""Pooled voice-learning extraction contracts; no speech provider or customer data.

The embedding service, STT and audio storage are fakes; candidate resolution,
interval pooling, purity, fencing, outcome recording and the C2 person fields
are production code.
"""

import asyncio
import logging
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from database import speaker_learning as speaker_learning_db
from database import users
from models.other import Person
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import speaker_identification as teaching
from utils import speaker_sample, speaker_audio
from utils.other import storage, audio_chunks
from tests.unit.fixtures.audio_chunk_storage import memory_bucket
from utils.person_evidence import person_updates_for_assignment
from utils.speaker_learning_policy import TEACHING_MIN_TOTAL_SECONDS

UID = 'account-a'
PERSON = 'person-1'
CONV = 'conv-1'
PERSON_PATH = ('users', UID, 'people', PERSON)
CONV_PATH = ('users', UID, 'conversations', CONV)
STARTED_AT = 1700000000.0
RATE = 16000


def seg(seg_id, start, end, *, speaker_id=0, person_id=PERSON, scope=None, text=None, is_user=False, unplaced=False):
    segment = {
        'id': seg_id,
        'start': start,
        'end': end,
        'speaker_id': speaker_id,
        'person_id': person_id,
        'is_user': is_user,
        'text': text or f'words from {seg_id} that keep going',
    }
    if scope:
        segment['speaker_id_scope'] = scope
    if unplaced:
        segment['audio_alignment'] = 'unplaced'
    return segment


def receipt_segments(ids, *, person_id=PERSON, generation=1, training=True, is_user=False):
    return {
        'segments': {
            seg_id: {
                'person_id': person_id,
                'is_user': is_user,
                'generation': generation,
                'use_for_speech_training': training,
            }
            for seg_id in ids
        },
        'generation': generation,
    }


def conversation(segments, *, receipt=None, audio_files=None, started_at=STARTED_AT, language='en', **extra):
    conv = {
        'started_at': started_at,
        'language': language,
        'transcript_segments': segments,
        'audio_files': [{'chunk_timestamps': [STARTED_AT]}] if audio_files is None else audio_files,
    }
    if receipt:
        conv['manual_speaker_assignments'] = receipt
    conv.update(extra)
    return conv


def pcm_for(seconds):
    return np.full(int(RATE * seconds), 500, dtype=np.int16).tobytes()


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    store.rows[PERSON_PATH] = {'id': PERSON, 'name': 'Synthetic Alex'}
    store.rows[('users', UID)] = {'save_other_voice_profiles': True}
    voice_settings = {'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': True}
    monkeypatch.setattr(users, 'db', store)
    monkeypatch.setattr(users, 'get_person', lambda uid, pid: deepcopy(store.rows.get(('users', uid, 'people', pid))))
    monkeypatch.setattr(users, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(speaker_learning_db, 'get_firestore_client', lambda *a, **k: store)
    monkeypatch.setattr(teaching.voice_profiles_db, 'get_voice_profile_settings', lambda uid: dict(voice_settings))
    monkeypatch.setattr(
        teaching.conversations_db,
        'get_conversation',
        lambda uid, cid: deepcopy(store.rows.get(('users', uid, 'conversations', cid))),
    )
    pcm_seconds = [60.0]
    download_calls = []

    def fake_download(uid, conversation_id, timestamps, **kwargs):
        download_calls.append(list(timestamps))
        return pcm_for(pcm_seconds[0])

    real_merge = storage.download_audio_chunks_and_merge
    monkeypatch.setattr(teaching, 'download_audio_chunks_and_merge', fake_download)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', lambda *a, **k: pcm_for(pcm_seconds[0]))

    def fake_chunks(uid, conversation_id, wanted, sample_rate, **kwargs):
        conv = store.rows.get(CONV_PATH) or {}
        timestamps = sorted(
            {ts for af in conv.get('audio_files', []) for ts in af.get('chunk_timestamps', [])},
            reverse=kwargs.get('newest_first', False),
        )
        for index, ts in enumerate(timestamps):
            following = timestamps[index + 1] if index + 1 < len(timestamps) else None
            if wanted(ts, following):
                download_calls.append([ts])
                yield ts, pcm_for(pcm_seconds[0])

    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', fake_chunks)
    real_listing = storage.list_audio_chunks

    def fake_listing(*args, **kwargs):
        conv = store.rows.get(CONV_PATH) or {}
        timestamps = {ts for af in conv.get('audio_files', []) for ts in af.get('chunk_timestamps', [])}
        return [
            {
                'timestamp': ts,
                'path': f'fake/{ts}.bin',
                'span': {
                    'start': ts,
                    'samples': round(pcm_seconds[0] * RATE),
                    'sample_rate': RATE,
                },
            }
            for ts in sorted(timestamps)
        ]

    monkeypatch.setattr(storage, 'list_audio_chunks', fake_listing)
    vector = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', lambda *a: vector)
    uploads = []
    monkeypatch.setattr(
        teaching,
        'upload_person_speech_sample_from_bytes',
        lambda *args: uploads.append(f'{UID}/people_profiles/{PERSON}/{len(uploads)}.wav') or uploads[-1],
    )
    deleted = []
    monkeypatch.setattr(teaching, 'delete_sample_from_storage', lambda path: deleted.append(path) or True)
    transcripts = {}
    captured = {}

    def fake_prerecorded(audio_bytes, rate, *args, **kwargs):
        if transcripts.get('raise'):
            raise RuntimeError('provider unavailable')
        if 'words' in transcripts:
            return transcripts['words']
        if 'text' in transcripts:
            text = transcripts['text']
        else:
            conv = store.rows.get(CONV_PATH) or {}
            text = ' '.join(
                str(s.get('text') or '') for s in conv.get('transcript_segments', []) if s.get('person_id') == PERSON
            )
        if text is None:
            raise RuntimeError('provider unavailable')
        return [{'text': text, 'speaker': transcripts.get('speaker', 'SPEAKER_00')}]

    monkeypatch.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', fake_prerecorded)
    real_verify = speaker_sample.verify_and_transcribe_sample

    async def recording_verify(wav_bytes, rate, expected_text, language=None):
        captured['expected_text'] = expected_text
        captured['wav_seconds'] = (len(wav_bytes) - 44) / (rate * 2)
        captured['pcm'] = wav_bytes[44:]
        return await real_verify(wav_bytes, rate, expected_text, language=language)

    monkeypatch.setattr(teaching, 'verify_and_transcribe_sample', recording_verify)
    return SimpleNamespace(
        real_listing=real_listing,
        real_merge=real_merge,
        store=store,
        uploads=uploads,
        deleted=deleted,
        transcripts=transcripts,
        captured=captured,
        pcm_seconds=pcm_seconds,
        download_calls=download_calls,
        voice_settings=voice_settings,
    )


def set_conversation(world, conv):
    world.store.rows[CONV_PATH] = conv


def teach(segment_ids=('s1',), **kwargs):
    return asyncio.run(teaching.extract_speaker_samples(UID, PERSON, CONV, list(segment_ids), **kwargs))


def test_pools_separated_clean_clips_and_expected_text_matches_audio(world):
    set_conversation(
        world,
        conversation(
            [
                seg('a', 0.0, 3.0, text='alpha words that keep going on'),
                seg('x', 4.0, 8.0, person_id='other', speaker_id=1),
                seg('b', 10.0, 13.0, text='bravo words that keep going on'),
                seg('c', 20.0, 24.0, text='charlie words that keep going on'),
            ]
        ),
    )
    outcome = teach(('a', 'b', 'c'))
    assert outcome == 'stored'
    saved = world.store.rows[PERSON_PATH]
    assert saved['speech_samples'], '3+3+4s of clean speech pools to the 10s floor'
    assert saved['voice_learning_state'] == 'learned'
    assert saved['voice_learning_outcome'] == 'stored'
    assert saved['voice_speech_seconds'] == pytest.approx(10.0, abs=0.05)
    assert world.captured['wav_seconds'] == pytest.approx(10.0, abs=0.05), 'gaps between clips are never counted'
    assert world.captured['expected_text'] == (
        'alpha words that keep going on bravo words that keep going on ' 'charlie words that keep going on'
    ), 'expected text is chronological contributor text in pooled PCM order'
    assert set(saved['speech_sample_source']['segment_ids']) == {'a', 'b', 'c'}


def test_cross_scope_duplicate_transcript_is_ignored(world):
    scope_a = [seg('a1', 0.0, 6.0, scope='rt'), seg('a2', 10.0, 14.0, scope='rt')]
    scope_b = [
        seg('b1', 0.0, 6.0, speaker_id=3, person_id=None, scope='v2'),
        seg('b2', 10.0, 14.0, speaker_id=3, person_id=None, scope='v2'),
    ]
    set_conversation(world, conversation(scope_a + scope_b))
    outcome = teach(('a1', 'a2', 'b1', 'b2'))
    assert outcome == 'stored'
    assert world.captured['wav_seconds'] == pytest.approx(10.0, abs=0.05), 'overlapping scopes decode shared audio once'
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_speech_seconds'] == pytest.approx(10.0, abs=0.05), 'overlapping wall time counts once'


def test_overlapping_frames_count_once_within_scope(world):
    segments = [seg('a', 0.0, 8.0), seg('b', 4.0, 12.0)]
    set_conversation(world, conversation(segments))
    outcome = teach(('a', 'b'))
    assert outcome == 'stored'
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_speech_seconds'] == pytest.approx(12.0, abs=0.05)


def test_same_scope_foreign_voice_contaminates_and_floors(world, caplog):
    segments = [
        seg('a', 0.0, 6.0),
        seg('intruder', 2.0, 5.0, speaker_id=1, person_id='other'),
        seg('b', 8.0, 11.0),
    ]
    set_conversation(world, conversation(segments))
    with caplog.at_level(logging.INFO, logger='utils.speaker_identification'):
        outcome = teach(('a', 'b'))
    assert outcome == 'contaminated'
    assert not world.uploads
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_learning_state'] == 'pending', 'contamination is a retryable quality failure'
    assert saved['voice_speech_seconds'] == pytest.approx(3.0, abs=0.05)
    outcome_lines = [r.getMessage() for r in caplog.records if 'speaker_voice_learning outcome=' in r.getMessage()]
    assert outcome_lines == ['speaker_voice_learning outcome=contaminated conversation=conv-1']
    assert UID not in outcome_lines[0] and PERSON not in outcome_lines[0]


def test_interleaved_voice_never_joins_across(world):
    segments = [
        seg('a', 0.0, 4.0),
        seg('other', 4.0, 8.0, speaker_id=1, person_id='other'),
        seg('b', 8.0, 12.0),
    ]
    set_conversation(world, conversation(segments))
    outcome = teach(('a', 'b'))
    assert outcome == 'insufficient_speech'


def test_decoded_truncation_is_uncovered(world):
    set_conversation(world, conversation([seg('a', 0.0, 6.0), seg('b', 10.0, 14.0)]))
    world.pcm_seconds[0] = 12.0
    outcome = teach(('a', 'b'))
    assert outcome == 'uncovered_audio'
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_learning_state'] == 'pending'
    assert saved['voice_speech_seconds'] == pytest.approx(6.0)
    assert not world.uploads
    assert 'expected_text' not in world.captured


def test_teaching_verifies_the_exact_positioned_overlap_clip(world, monkeypatch):
    set_conversation(
        world, conversation([seg('a', 0.0, 10.0)], audio_files=[{'chunk_timestamps': [STARTED_AT, STARTED_AT + 4]}])
    )

    pattern = (np.arange(RATE * 6) % 997 + 1).astype(np.int16)

    def overlapping_chunks(*args, **kwargs):
        assert kwargs['newest_first'] is True
        yield STARTED_AT + 4, pattern.tobytes()
        yield STARTED_AT, pcm_for(6)

    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', overlapping_chunks)
    assert teach(('a',)) == 'stored'
    assert world.captured['pcm'] == pcm_for(4) + pattern.tobytes()


def test_pools_three_authoritative_short_chunks(world, monkeypatch):
    offsets = [0.1234, 10.1234, 20.1234]
    set_conversation(
        world,
        conversation(
            [seg(str(i), offset, offset + 3.5) for i, offset in enumerate(offsets)],
            audio_files=[{'chunk_timestamps': [STARTED_AT + offset for offset in offsets]}],
        ),
    )

    def rounded_chunks(*args, **kwargs):
        wanted = args[2]
        for offset in reversed(offsets):
            timestamp = STARTED_AT + offset
            if wanted(timestamp, None):
                yield timestamp, pcm_for(3.5)

    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', rounded_chunks)
    assert teach(('0', '1', '2')) == 'stored'
    assert world.captured['wav_seconds'] == pytest.approx(10.5, abs=0.002)


def test_real_reader_pools_rounded_short_chunks_once(world, memory_bucket, monkeypatch):
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', audio_chunks.iter_audio_chunk_pcm)
    offsets = [0.1234, 10.1234, 20.1234]
    for offset in offsets:
        memory_bucket.add(STARTED_AT + offset, 3.5, uid=UID, conversation_id=CONV)
    set_conversation(
        world,
        conversation(
            [seg(str(i), offset, offset + 3.5) for i, offset in enumerate(offsets)],
            audio_files=[{'chunk_timestamps': [STARTED_AT + offset for offset in offsets]}],
        ),
    )
    assert teach(('0', '1', '2')) == 'stored'
    assert world.captured['wav_seconds'] == pytest.approx(10.5, abs=0.002)
    assert len(memory_bucket.listings) == 1
    assert len(memory_bucket.reads) == 3


@pytest.mark.parametrize('offset', [0.1234, 0.1236])
@pytest.mark.parametrize('chunk_seconds', [10, 60])
def test_rounded_complete_ten_seconds_keeps_teaching_floor(world, memory_bucket, monkeypatch, offset, chunk_seconds):
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', audio_chunks.iter_audio_chunk_pcm)
    data = memory_bucket.add(STARTED_AT + offset, chunk_seconds, uid=UID, conversation_id=CONV)
    set_conversation(
        world, conversation([seg('a', offset, offset + 10)], audio_files=[{'chunk_timestamps': [STARTED_AT + offset]}])
    )
    assert teach(('a',)) == 'stored'
    assert world.captured['pcm'] == data[: 16000 * 10 * 2]


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_real_live_batches_still_teach(world, memory_bucket, monkeypatch, protection):
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', audio_chunks.iter_audio_chunk_pcm)
    parts = [{'timestamp': STARTED_AT + offset, 'data': pcm_for(5)} for offset in (0, 5)]
    storage.upload_audio_chunks_batch(parts, UID, CONV, data_protection_level=protection)
    set_conversation(world, conversation([seg('a', 0, 10)]))
    assert teach(('a',)) == 'stored'
    assert world.captured['pcm'] == pcm_for(10)
    assert len(memory_bucket.listings) == len(memory_bucket.reads) == 1


def test_missing_first_window_keeps_later_sufficient_speech_and_only_its_text(world, monkeypatch):
    set_conversation(
        world,
        conversation(
            [
                seg('missing', 0, 3, text='missing text is excluded'),
                seg('b', 10, 15, text='bravo speech is included here'),
                seg('c', 20, 25, text='charlie speech is also included'),
            ],
            audio_files=[{'chunk_timestamps': [STARTED_AT, STARTED_AT + 10, STARTED_AT + 20]}],
        ),
    )

    def chunks(*args, **kwargs):
        wanted = args[2]
        for offset in (20, 10):
            if wanted(STARTED_AT + offset, None):
                yield STARTED_AT + offset, pcm_for(5)

    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', chunks)
    world.transcripts['text'] = 'bravo speech is included here charlie speech is also included'
    assert teach(('missing', 'b', 'c')) == 'stored'
    assert world.captured['expected_text'] == world.transcripts['text']
    assert world.captured['wav_seconds'] == 10
    assert world.store.rows[PERSON_PATH]['speech_sample_source']['segment_ids'] == ['b', 'c']


def test_missing_audio_cannot_replace_a_previous_voiceprint(world):
    previous = {
        'speech_samples': ['old.wav'],
        'speech_sample_transcripts': ['synthetic words'],
        'speech_samples_version': 3,
        'speaker_embedding': [1.0, 0.0],
        'voice_learning_state': 'learned',
    }
    world.store.rows[PERSON_PATH].update(previous)
    set_conversation(world, conversation([seg('a', 0.0, 10.0)]))
    world.pcm_seconds[0] = 9.0
    assert teach(('a',)) == 'uncovered_audio'
    assert all(world.store.rows[PERSON_PATH][key] == value for key, value in previous.items())
    assert not world.uploads and not world.deleted
    assert 'expected_text' not in world.captured


def test_optout_records_disabled_and_skips_work(world):
    world.voice_settings['save_other_voice_profiles'] = False
    set_conversation(world, conversation([seg('a', 0.0, 20.0)]))
    outcome = teach(('a',))
    assert outcome == 'disabled'
    assert not world.uploads
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_learning_state'] == 'disabled'
    assert saved['voice_learning_outcome'] == 'disabled'


def test_no_audio_records_bounded_outcome(world, caplog):
    set_conversation(world, conversation([seg('a', 0.0, 20.0)], audio_files=[]))
    with caplog.at_level(logging.INFO, logger='utils.speaker_identification'):
        outcome = teach(('a',))
    assert outcome == 'no_audio'
    lines = [r.getMessage() for r in caplog.records if 'speaker_voice_learning outcome=' in r.getMessage()]
    assert lines == ['speaker_voice_learning outcome=no_audio conversation=conv-1']
    assert UID not in lines[0] and 'alpha' not in lines[0]


def test_no_chunks_records_single_outcome(world):
    set_conversation(world, conversation([seg('a', 0.0, 20.0)], audio_files=[{'chunk_timestamps': []}]))
    assert teach(('a',)) == 'no_chunks'


def test_transcription_failure_maps_to_closed_outcome(world):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))
    world.transcripts['text'] = None
    outcome = teach(('a',))
    assert outcome == 'transcription_failed'
    assert world.store.rows[PERSON_PATH]['voice_learning_state'] == 'pending'


def test_prior_ready_state_survives_failed_retry(world):
    world.store.rows[PERSON_PATH].update(
        speech_samples=['old.wav'],
        speech_sample_transcripts=['t'],
        speech_samples_version=3,
        speaker_embedding=[1.0, 0.0, 0.0],
    )
    set_conversation(world, conversation([seg('a', 0.0, 20.0)], audio_files=[]))
    outcome = teach(('a',))
    assert outcome == 'no_audio'
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_learning_state'] == 'learned', 'a still-usable voiceprint keeps learned on failed retry'
    assert saved['speech_samples'] == ['old.wav']


def test_same_person_training_false_reassign_fences_in_flight(world, monkeypatch):
    before = seg('a', 0.0, 20.0)
    set_conversation(world, conversation([before], receipt=receipt_segments(['a'])))
    vector = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)

    def embed(*args):
        new_receipt = {
            'segments': {
                'a': {'person_id': PERSON, 'is_user': False, 'generation': 2, 'use_for_speech_training': False}
            },
            'generation': 2,
        }
        updates, _ = person_updates_for_assignment(
            {PERSON: world.store.rows[PERSON_PATH]},
            [],
            PERSON,
            [before],
            'manual',
            CONV,
            ['a'],
            datetime(2026, 1, 1),
            new_receipt,
            [before],
        )
        world.store.rows[PERSON_PATH].update(updates[PERSON])
        return vector

    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', embed)
    outcome = teach(('a',))
    assert outcome == 'stale_assignment', 'same-person reassign with no earned evidence must still bump the fence'
    assert world.store.rows[PERSON_PATH].get('updated_at') is not None
    assert not world.store.rows[PERSON_PATH].get('speaker_embedding')


def test_correction_during_embedding_fences_publish_and_outcome(world, monkeypatch):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))

    def embed(*args):
        world.store.rows[PERSON_PATH]['updated_at'] = 'later'
        return np.array([[1.0, 0.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr(teaching, 'extract_embedding_from_bytes', embed)
    outcome = teach(('a',))
    assert outcome == 'stale_assignment'
    saved = world.store.rows[PERSON_PATH]
    assert not saved.get('speaker_embedding')
    assert 'voice_learning_state' not in saved, 'the stale outcome write is fenced by updated_at'
    assert world.uploads[-1] in world.deleted


def test_receipt_pools_authorized_segments_beyond_passed_ids(world):
    segments = [
        seg('a', 0.0, 4.0),
        seg('b', 10.0, 14.0),
        seg('c', 20.0, 24.0),
        seg('other', 30.0, 35.0, speaker_id=9, person_id='other'),
    ]
    set_conversation(world, conversation(segments, receipt=receipt_segments(['a', 'b', 'c'])))
    outcome = teach(('a',))
    assert outcome == 'stored'
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_speech_seconds'] == pytest.approx(
        12.0, abs=0.05
    ), 'one authorized anchor pools its receipt-authorized voice group'
    assert set(saved['speech_sample_source']['segment_ids']) == {'a', 'b', 'c'}


def test_receipt_only_trains_its_authorized_segments(world):
    segments = [seg('a', 0.0, 4.0), seg('b', 10.0, 14.0), seg('c', 20.0, 24.0)]
    set_conversation(world, conversation(segments, receipt=receipt_segments(['a'])))
    outcome = teach(('a',))
    assert outcome == 'insufficient_speech', 'labeled-but-unauthorized b/c cannot fill the 10s floor'
    assert not world.uploads


def test_newer_training_false_decision_stays_excluded(world):
    receipt = {
        'segments': {
            'a': {'person_id': PERSON, 'is_user': False, 'generation': 1},
            'b': {'person_id': PERSON, 'is_user': False, 'generation': 2, 'use_for_speech_training': False},
            'c': {'person_id': PERSON, 'is_user': False, 'generation': 1},
        },
        'generation': 2,
    }
    segments = [seg('a', 0.0, 4.0), seg('b', 10.0, 14.0), seg('c', 20.0, 24.0)]
    set_conversation(world, conversation(segments, receipt=receipt))
    outcome = teach(('a', 'b', 'c'))
    assert outcome == 'insufficient_speech', 'the newer use_for_speech_training=False decision wins for b'
    assert not world.uploads


def test_unauthorized_overlapping_voice_rejects_candidate(world):
    segments = [
        seg('a', 0.0, 6.0, text='alpha words that keep going on'),
        seg('a2', 2.0, 5.0, text='alpha words that keep going on'),
        seg('b', 20.0, 26.0, text='bravo words that keep going on'),
    ]
    set_conversation(world, conversation(segments, receipt=receipt_segments(['a', 'b'])))
    outcome = teach(('a', 'b'))
    assert outcome == 'contaminated', 'unauthorized same-voice overlap may not ride along as source audio'
    assert not world.uploads


def test_authorized_overlap_is_source_for_invalidation(world):
    segments = [
        seg('a', 0.0, 6.0, text='alpha words that keep going on'),
        seg('a2', 2.0, 5.0, text='alpha words that keep going on'),
        seg('b', 20.0, 26.0, text='bravo words that keep going on'),
    ]
    set_conversation(world, conversation(segments, receipt=receipt_segments(['a', 'a2', 'b'])))
    outcome = teach(('a', 'b'))
    assert outcome == 'stored'
    saved = world.store.rows[PERSON_PATH]
    assert set(saved['speech_sample_source']['segment_ids']) == {
        'a',
        'a2',
        'b',
    }, 'all actually overlapping authorized segment ids invalidate the taught profile'


def test_training_false_overlap_rejects_candidate(world):
    receipt = {
        'segments': {
            'a': {'person_id': PERSON, 'is_user': False, 'generation': 1},
            'a2': {'person_id': PERSON, 'is_user': False, 'generation': 2, 'use_for_speech_training': False},
            'b': {'person_id': PERSON, 'is_user': False, 'generation': 1},
        },
        'generation': 2,
    }
    segments = [
        seg('a', 0.0, 6.0, text='alpha words that keep going on'),
        seg('a2', 2.0, 5.0, text='alpha words that keep going on'),
        seg('b', 20.0, 26.0, text='bravo words that keep going on'),
    ]
    set_conversation(world, conversation(segments, receipt=receipt))
    outcome = teach(('a', 'b'))
    assert outcome == 'contaminated', 'a winning trainingFalse decision overlapping the clip must suppress it'
    assert not world.uploads


def test_receipt_training_false_excludes_segment(world):
    segments = [seg('a', 0.0, 20.0)]
    receipt = receipt_segments(['a'], training=False)
    set_conversation(world, conversation(segments, receipt=receipt))
    outcome = teach(('a',))
    assert outcome == 'stale_assignment', 'a receipt that no longer authorizes the id must not teach'


def test_absorbed_ids_resolve_from_current_receipt(world):
    segments = [seg('n1', 0.0, 6.0), seg('n2', 10.0, 16.0)]
    receipt = {
        'speakers': {'0': {'person_id': PERSON, 'is_user': False, 'generation': 3, 'use_for_speech_training': True}},
        'segments': {'gone': {'person_id': PERSON, 'is_user': False, 'generation': 2}},
        'generation': 3,
    }
    set_conversation(world, conversation(segments, receipt=receipt))
    outcome = teach(('gone',))
    assert outcome == 'stored'


def test_relabel_loses_authorization(world):
    segments = [seg('a', 0.0, 20.0, person_id='other')]
    set_conversation(world, conversation(segments, receipt=receipt_segments(['a'])))
    outcome = teach(('a',))
    assert outcome == 'stale_assignment'
    assert not world.uploads


def test_unplaced_segments_never_contribute(world):
    segments = [seg('a', 0.0, 20.0, unplaced=True)]
    set_conversation(world, conversation(segments))
    outcome = teach(('a',))
    assert outcome == 'insufficient_speech'
    assert not world.uploads


def test_v2_uncovered_window_is_rejected(world, monkeypatch):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)], audio_timeline_version=2))
    monkeypatch.setattr(teaching, 'is_audio_timeline_v2', lambda conversation: True)
    monkeypatch.setattr(teaching, 'coverage_outcome', lambda conversation, start, end: 'missing')
    outcome = teach(('a',))
    assert outcome == 'uncovered_audio'
    assert not world.uploads


def test_missing_person_records_outcome(world):
    del world.store.rows[PERSON_PATH]
    set_conversation(world, conversation([seg('a', 0.0, 20.0)]))
    assert teach(('a',)) == 'person_missing'


def test_missing_conversation_records_outcome(world):
    assert teach(('a',)) == 'conversation_missing'


def test_error_outcome_is_safe(world, monkeypatch, caplog):
    set_conversation(world, conversation([seg('a', 0.0, 20.0)]))
    monkeypatch.setattr(teaching, 'legacy_speaker_clip_pcm', lambda *a, **k: (_ for _ in ()).throw(ValueError('boom')))
    with caplog.at_level(logging.INFO, logger='utils.speaker_identification'):
        outcome = teach(('a',))
    assert outcome == 'error'
    lines = [r.getMessage() for r in caplog.records if 'speaker_voice_learning outcome=' in r.getMessage()]
    assert lines == ['speaker_voice_learning outcome=error conversation=conv-1']
    assert 'boom' not in lines[0] and UID not in lines[0]


def test_decoded_nine_point_eight_seconds_cannot_fill_a_later_window(world):
    set_conversation(world, conversation([seg('a', 0.0, 6.0), seg('b', 10.0, 14.0)]))
    world.pcm_seconds[0] = 9.8
    outcome = teach(('a', 'b'))
    assert outcome == 'uncovered_audio'
    assert world.store.rows[PERSON_PATH]['voice_learning_state'] == 'pending'
    assert not world.uploads


def test_far_apart_windows_download_only_local_chunks(world):
    late_chunk = STARTED_AT + 7199.0
    conv = conversation(
        [seg('a', 0.0, 6.0), seg('b', 7200.0, 7204.0)],
        audio_files=[{'chunk_timestamps': [STARTED_AT, late_chunk]}],
    )
    set_conversation(world, conv)
    outcome = teach(('a', 'b'))
    assert outcome == 'stored'
    assert world.download_calls == [
        [STARTED_AT],
        [late_chunk],
    ], 'each selected window downloads only its preceding/intersecting chunks'


def test_v2_oversized_trim_result_is_capped_to_planned_window(world, monkeypatch):
    set_conversation(
        world,
        conversation(
            [seg('a', 0.0, 6.0), seg('b', 10.0, 14.0)],
            audio_timeline={'version': 2},
            audio_files=[
                {'chunk_timestamps': [STARTED_AT], 'chunk_spans': [{'start': STARTED_AT, 'end': STARTED_AT + 60}]}
            ],
        ),
    )
    monkeypatch.setattr(teaching, '_trim_pcm_audio', lambda *a: pcm_for(25.0))
    outcome = teach(('a', 'b'))
    assert outcome == 'stored'
    assert world.captured['wav_seconds'] == pytest.approx(
        10.0, abs=0.05
    ), 'a decoder returning extra audio cannot push the pooled sample past the planned windows'


def test_embedding_exception_maps_to_embedding_failed(world, monkeypatch):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))
    monkeypatch.setattr(
        teaching, 'extract_embedding_from_bytes', lambda *a: (_ for _ in ()).throw(RuntimeError('embed down'))
    )
    outcome = teach(('a',))
    assert outcome == 'embedding_failed'
    assert world.store.rows[PERSON_PATH]['voice_learning_state'] == 'pending'


def test_cleanup_failure_keeps_stored_outcome(world, monkeypatch, caplog):
    world.store.rows[PERSON_PATH].update(
        speech_samples=['old.wav'],
        speech_sample_transcripts=['t'],
        speech_samples_version=3,
        speaker_embedding=[1.0, 0.0, 0.0],
    )
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))
    monkeypatch.setattr(
        teaching, 'delete_sample_from_storage', lambda path: (_ for _ in ()).throw(RuntimeError('private path leak'))
    )
    with caplog.at_level(logging.WARNING, logger='utils.speaker_identification'):
        outcome = teach(('a',))
    assert outcome == 'stored'
    saved = world.store.rows[PERSON_PATH]
    assert saved['voice_learning_state'] == 'learned'
    warnings = [r.getMessage() for r in caplog.records if 'cleanup failed' in r.getMessage()]
    assert warnings and 'private path leak' not in warnings[0]


def test_multi_speaker_clip_rejected_by_real_gate(world):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))
    world.transcripts['words'] = [
        {'text': 'hello world this', 'speaker': 'SPEAKER_00'},
        {'text': 'is mixed audio', 'speaker': 'SPEAKER_01'},
    ]
    assert teach(('a',)) == 'multi_speaker'


def test_insufficient_words_clip_rejected_by_real_gate(world):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))
    world.transcripts['words'] = [{'text': 'hi', 'speaker': 'SPEAKER_00'}]
    assert teach(('a',)) == 'insufficient_words'


def test_text_mismatch_clip_rejected_by_real_gate(world):
    set_conversation(world, conversation([seg('a', 0.0, 12.0)]))
    world.transcripts['text'] = 'completely unrelated spoken words entirely different content'
    assert teach(('a',)) == 'text_mismatch'


def test_same_scope_foreign_voice_rejects_before_verification(world):
    set_conversation(
        world,
        conversation(
            [
                seg('a', 0.0, 6.0),
                seg('intruder', 2.0, 5.0, speaker_id=1, person_id='other'),
                seg('b', 10.0, 16.0),
            ]
        ),
    )
    outcome = teach(('a', 'b'))
    assert outcome == 'contaminated'
    assert 'wav_seconds' not in world.captured, 'verification must not run once a candidate is rejected'


def test_model_derives_learning_state_from_readiness():
    ready_fields = {
        'id': 'p1',
        'name': 'Alex',
        'speaker_embedding': [1.0, 0.0],
        'speech_samples': ['a.wav'],
        'speech_samples_version': 3,
    }
    assert (
        Person(**ready_fields, voice_learning_state='pending').voice_learning_state == 'learned'
    ), 'a ready voiceprint is learned even while a pending write was recorded'
    assert Person(**ready_fields, voice_learning_state='disabled').voice_learning_state == 'disabled'
    assert (
        Person(
            id='p1', name='Alex', voice_learning_state='learned', voice_learning_outcome='stored'
        ).voice_learning_state
        == 'unknown'
    ), 'a learned claim with no usable print and no live durable job stays unknown'
    assert Person(id='p1', name='Alex', voice_learning_state='learned').voice_learning_state == 'unknown'


@pytest.mark.parametrize('enhanced', [False, True])
def test_rounded_two_chunk_exact_floor_teaches_main_samples(world, memory_bucket, monkeypatch, enhanced):
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    monkeypatch.setattr(speaker_audio, 'iter_audio_chunk_pcm', audio_chunks.iter_audio_chunk_pcm)
    offset = 0.1234
    start = STARTED_AT + offset
    second_start = start + 64003 / RATE
    first = memory_bucket.add(start, 64003 / RATE, enhanced=enhanced, uid=UID, conversation_id=CONV)
    second = memory_bucket.add(second_start, 95997 / RATE, enhanced=enhanced, uid=UID, conversation_id=CONV)
    set_conversation(
        world, conversation([seg('a', offset, offset + 10)], audio_files=[{'chunk_timestamps': [start, second_start]}])
    )
    assert teach(('a',)) == 'stored'
    assert world.captured['pcm'] == first + second
    assert world.captured['wav_seconds'] == 10
