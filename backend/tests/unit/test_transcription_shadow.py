"""Hermetic tests for stored-chunk timing and shadow admission."""

from datetime import datetime, timezone
from types import SimpleNamespace

from models.transcript_segment import TranscriptSegment
from utils.conversations import transcription_shadow as shadow


def test_shadow_requires_opt_in_stored_audio_and_budget(monkeypatch):
    conversation = SimpleNamespace(private_cloud_sync_enabled=True, discarded=False, uses_custom_stt=False)
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_PERCENT', '0')
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_UID_ALLOWLIST', 'test-user')
    assert shadow._enabled('test-user', conversation)
    assert not shadow._enabled('other-user', conversation)
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_KILL_SWITCH', 'true')
    assert not shadow._enabled('test-user', conversation)
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_KILL_SWITCH', 'false')
    conversation.private_cloud_sync_enabled = False
    assert not shadow._enabled('test-user', conversation)


def test_pass_uses_each_blob_clock_and_restores_first_word_offset(monkeypatch):
    chunks = [(100.0, bytes(10 * 32000)), (107.0, bytes(10 * 32000))]
    monkeypatch.setattr(
        shadow, 'iter_audio_chunk_pcm', lambda _uid, _cid, wanted: ((t, p) for t, p in chunks if wanted(t, None))
    )
    monkeypatch.setattr(shadow, 'build_person_embeddings_cache', lambda _uid: {})
    monkeypatch.setattr(shadow, 'identify_speakers_for_segments', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(shadow, 'speaker_embedding_configured', lambda: False)
    monkeypatch.setattr(
        shadow,
        'parakeet_prerecorded_from_bytes',
        lambda *_args, **_kwargs: [{'timestamp': [2.0, 3.0], 'speaker': 'SPEAKER_00', 'text': 'hello'}],
    )
    conversation = SimpleNamespace(
        id='synthetic',
        language='en',
        audio_files=[SimpleNamespace(chunk_timestamps=[100.0, 107.0])],
        finished_at=datetime.fromtimestamp(120, timezone.utc),
        transcript_segments=[],
    )
    passed, audio = shadow._make_pass('synthetic', conversation, deadline=float('inf'), reserved_seconds=20)
    assert [round(s.start, 3) for s in passed] == [2.0, 12.0]
    assert [round(s.end, 3) for s in passed] == [3.0, 13.0]
    assert audio == {'coverage': 0.85, 'tail_gap_seconds': 3.0, 'audio_seconds': 17.0}
    assert all(s.speaker_id_scope.startswith('sync:shadow:') for s in passed)


def test_decoded_audio_cannot_exceed_reserved_budget(monkeypatch):
    monkeypatch.setattr(shadow, 'iter_audio_chunk_pcm', lambda *_args: iter([(100.0, bytes(3 * 32000))]))
    monkeypatch.setattr(shadow, 'build_person_embeddings_cache', lambda _uid: {})
    monkeypatch.setattr(shadow, '_reserve_budget', lambda *_args: 'budget_exhausted')
    conversation = SimpleNamespace(id='synthetic', audio_files=[SimpleNamespace(chunk_timestamps=[100.0])])
    try:
        shadow._make_pass('synthetic', conversation, deadline=float('inf'), reserved_seconds=2)
    except shadow._BudgetExceeded:
        pass
    else:
        raise AssertionError('provider call should be blocked by audio-hours reservation')


def test_comparison_persists_only_bounded_scalars_and_detects_owner_parity():
    live = TranscriptSegment(id='old', text='Synthetic private words', start=0, end=2, is_user=True)
    passed = TranscriptSegment(id='new', text='Synthetic private words', start=0, end=2, is_user=True)
    conversation = SimpleNamespace(
        transcript_segments=[live], structured=SimpleNamespace(model_dump=lambda: {'source_segment_ids': ['old']})
    )
    result = shadow._compare(
        conversation, [passed], {'coverage': 1.0, 'tail_gap_seconds': 0.0, 'audio_seconds': 2.0}, {}
    )
    assert result['word_distance'] == 0
    assert result['live_owner_seconds'] == result['pass_owner_seconds'] == 2
    assert result['remap_safe']
    assert 'Synthetic private words' not in repr(result)


def test_duplicate_reservation_never_writes_or_counts_result(monkeypatch):
    conversation = SimpleNamespace(audio_files=[SimpleNamespace(duration=10, chunk_timestamps=[100])])
    monkeypatch.setattr(shadow.conversations_db, 'get_conversation', lambda *_args: {'synthetic': True})
    monkeypatch.setattr(shadow, 'deserialize_conversation', lambda _raw: conversation)
    monkeypatch.setattr(shadow, '_enabled', lambda *_args: True)
    monkeypatch.setattr(shadow, '_reserve_budget', lambda *_args: 'duplicate')
    writes = []
    monkeypatch.setattr(shadow, '_store_result', lambda *_args: writes.append(_args))
    monkeypatch.setattr(
        shadow.SHADOW_OUTCOMES, 'labels', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('counted'))
    )
    shadow._run_shadow('synthetic-uid', 'synthetic-conversation')
    assert writes == []


def test_budget_reservation_distinguishes_duplicate_from_exhaustion(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS', '1')
    for code, expected in ((0, 'budget_exhausted'), (1, 'reserved'), (2, 'duplicate')):
        monkeypatch.setattr(shadow.redis_client, 'eval', lambda *_args, code=code: code)
        assert shadow._reserve_budget('synthetic-conversation', 10) == expected
