import pytest
from unittest.mock import AsyncMock, MagicMock

import utils.speaker_identification as speaker_identification
from utils.other import storage as storage_utils


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_missing_audio_metadata_is_retryable_instead_of_false_success(monkeypatch):
    monkeypatch.setattr(speaker_identification, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(speaker_identification.users_db, 'get_person', lambda _uid, _person_id: {})
    monkeypatch.setattr(
        speaker_identification.users_db,
        'get_person_speech_samples_count',
        lambda _uid, _person_id: 0,
    )
    monkeypatch.setattr(
        speaker_identification.conversations_db,
        'get_conversation',
        lambda _uid, _conversation_id: {
            'started_at': 1.0,
            'transcript_segments': [{'id': 'segment-1', 'start': 0.0, 'end': 10.0}],
            'audio_files': [],
        },
    )

    result = await speaker_identification.extract_speaker_samples(
        uid='uid-1',
        person_id='person-1',
        conversation_id='conversation-1',
        segment_ids=['segment-1'],
    )

    assert result.status == 'retryable'
    assert result.reason == 'audio_files_not_ready'


@pytest.mark.anyio
async def test_missing_requested_segment_is_retryable_instead_of_false_success(monkeypatch):
    monkeypatch.setattr(speaker_identification, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(speaker_identification.users_db, 'get_person', lambda _uid, _person_id: {})
    monkeypatch.setattr(
        speaker_identification.users_db,
        'get_person_speech_samples_count',
        lambda _uid, _person_id: 0,
    )
    monkeypatch.setattr(
        speaker_identification.conversations_db,
        'get_conversation',
        lambda _uid, _conversation_id: {
            'started_at': 1.0,
            'transcript_segments': [],
            'audio_files': [{'chunk_timestamps': [1.0]}],
        },
    )

    result = await speaker_identification.extract_speaker_samples(
        uid='uid-1',
        person_id='person-1',
        conversation_id='conversation-1',
        segment_ids=['segment-not-persisted-yet'],
    )

    assert result.status == 'retryable'
    assert result.reason == 'transcript_segments_not_ready'


@pytest.mark.anyio
async def test_unhandled_extraction_error_is_retryable_instead_of_false_success(monkeypatch):
    monkeypatch.setattr(speaker_identification, 'run_blocking', _inline_run_blocking)

    def fail(_uid, _person_id):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(speaker_identification.users_db, 'get_person', fail)

    result = await speaker_identification.extract_speaker_samples(
        uid='uid-1',
        person_id='person-1',
        conversation_id='conversation-1',
        segment_ids=['segment-1'],
    )

    assert result.status == 'retryable'
    assert result.reason == 'extraction_failed'


@pytest.mark.anyio
async def test_missing_person_is_retryable_before_upload_side_effects(monkeypatch):
    monkeypatch.setattr(speaker_identification, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(speaker_identification.users_db, 'get_person', lambda _uid, _person_id: None)
    get_conversation = MagicMock()
    upload_sample = MagicMock()
    monkeypatch.setattr(speaker_identification.conversations_db, 'get_conversation', get_conversation)
    monkeypatch.setattr(speaker_identification, 'upload_person_speech_sample_from_bytes', upload_sample)

    result = await speaker_identification.extract_speaker_samples(
        uid='uid-1',
        person_id='person-1',
        conversation_id='conversation-1',
        segment_ids=['segment-1'],
    )

    assert result.status == 'retryable'
    assert result.reason == 'person_not_ready'
    get_conversation.assert_not_called()
    upload_sample.assert_not_called()


@pytest.mark.anyio
async def test_sample_append_enforces_the_single_sample_limit_transactionally(monkeypatch):
    monkeypatch.setattr(speaker_identification, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(speaker_identification.users_db, 'get_person', lambda _uid, _person_id: {})
    monkeypatch.setattr(
        speaker_identification.users_db,
        'get_person_speech_samples_count',
        lambda _uid, _person_id: 0,
    )
    monkeypatch.setattr(
        speaker_identification.conversations_db,
        'get_conversation',
        lambda _uid, _conversation_id: {
            'started_at': 1_000.0,
            'transcript_segments': [
                {
                    'id': 'segment-1',
                    'start': 0.0,
                    'end': 10.0,
                    'text': 'hello there',
                    'speaker_id': 1,
                }
            ],
            'audio_files': [{'chunk_timestamps': [1_000.0]}],
        },
    )
    monkeypatch.setattr(
        speaker_identification,
        'download_audio_chunks_and_merge',
        lambda *_args, **_kwargs: b'audio',
    )
    monkeypatch.setattr(
        speaker_identification,
        '_trim_pcm_audio',
        lambda *_args, **_kwargs: b'\x00\x00' * (16_000 * 10),
    )
    monkeypatch.setattr(
        speaker_identification,
        'verify_and_transcribe_sample',
        AsyncMock(return_value=('hello there', True, '')),
    )
    upload_sample = MagicMock(return_value='users/uid-1/people/person-1/sample.pcm')
    monkeypatch.setattr(speaker_identification, 'upload_person_speech_sample_from_bytes', upload_sample)
    add_sample = MagicMock(return_value=True)
    monkeypatch.setattr(speaker_identification.users_db, 'add_person_speech_sample', add_sample)
    monkeypatch.setattr(
        speaker_identification,
        'extract_embedding_from_bytes',
        MagicMock(side_effect=RuntimeError('embedding unavailable')),
    )

    result = await speaker_identification.extract_speaker_samples(
        uid='uid-1',
        person_id='person-1',
        conversation_id='conversation-1',
        segment_ids=['segment-1'],
        sample_rate=16_000,
        delivery_id='delivery-1',
    )

    assert result.status == 'stored'
    upload_sample.assert_called_once_with(
        b'\x00\x00' * (16_000 * 10),
        'uid-1',
        'person-1',
        16_000,
        'speaker-sample\0uid-1\0person-1\0delivery-1',
    )
    add_sample.assert_called_once_with(
        'uid-1',
        'person-1',
        'users/uid-1/people/person-1/sample.pcm',
        transcript='hello there',
        max_samples=1,
    )


def test_speech_sample_upload_reuses_one_hashed_object_for_a_stable_delivery(monkeypatch):
    uploaded_paths = []

    class FakeBlob:
        def __init__(self, path):
            self.path = path

        def upload_from_string(self, _payload, *, content_type):
            assert content_type == 'audio/wav'
            uploaded_paths.append(self.path)

    class FakeBucket:
        def blob(self, path):
            return FakeBlob(path)

    monkeypatch.setattr(storage_utils, '_get_speech_profiles_bucket', lambda **_kwargs: FakeBucket())

    stable_key = 'speaker-sample\0uid-1\0person-1\0delivery-1'
    first = storage_utils.upload_person_speech_sample_from_bytes(
        b'\x00\x00',
        'uid-1',
        'person-1',
        deduplication_key=stable_key,
    )
    replay = storage_utils.upload_person_speech_sample_from_bytes(
        b'\x00\x00',
        'uid-1',
        'person-1',
        deduplication_key=stable_key,
    )
    another = storage_utils.upload_person_speech_sample_from_bytes(
        b'\x00\x00',
        'uid-1',
        'person-1',
        deduplication_key='speaker-sample\0uid-1\0person-1\0delivery-2',
    )
    legacy_first = storage_utils.upload_person_speech_sample_from_bytes(b'\x00\x00', 'uid-1', 'person-1')
    legacy_second = storage_utils.upload_person_speech_sample_from_bytes(b'\x00\x00', 'uid-1', 'person-1')

    assert first == replay, 'one logical speaker delivery must overwrite one stable GCS object'
    assert another != first
    assert legacy_first != legacy_second
    assert uploaded_paths == [first, replay, another, legacy_first, legacy_second]
