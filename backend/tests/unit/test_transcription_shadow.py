"""Hermetic tests for stored-chunk timing and shadow admission."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
import wave
import pytest

from models.transcript_segment import TranscriptSegment
from utils.conversations import transcription_shadow as shadow
from utils.conversations import finalizer, final_pass_pyannote


def test_finalizer_starts_shadow_only_for_enabled_admission(monkeypatch):
    calls = []
    monkeypatch.setattr(shadow, 'maybe_start_shadow', lambda uid, conversation: calls.append((uid, conversation)))
    conversation = SimpleNamespace(id='synthetic')
    monkeypatch.delenv('TRANSCRIPTION_SHADOW_ENABLED', raising=False)
    finalizer._maybe_start_shadow('synthetic-uid', conversation)
    assert calls == []

    monkeypatch.setenv('TRANSCRIPTION_SHADOW_ENABLED', 'true')
    finalizer._maybe_start_shadow('synthetic-uid', conversation)
    assert calls == [('synthetic-uid', conversation)]

    monkeypatch.setenv('TRANSCRIPTION_SHADOW_KILL_SWITCH', 'true')
    finalizer._maybe_start_shadow('synthetic-uid', conversation)
    assert calls == [('synthetic-uid', conversation)]


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
    chunks = [(100.0, b'\x01\x00' * (10 * 16000)), (107.0, b'\x01\x00' * (10 * 16000))]
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
        started_at=datetime.fromtimestamp(85, timezone.utc),
        finished_at=datetime.fromtimestamp(120, timezone.utc),
        transcript_segments=[],
    )
    passed, audio = shadow._make_pass('synthetic', conversation, deadline=float('inf'), reserved_seconds=20)
    assert [round(s.start, 3) for s in passed] == [2.0, 12.0]
    assert [round(s.end, 3) for s in passed] == [3.0, 13.0]
    assert audio == {
        'coverage': 0.85,
        'tail_gap_seconds': 3.0,
        'audio_seconds': 17.0,
        'audio_origin_offset_seconds': 15.0,
    }
    assert all(s.speaker_id_scope.startswith('sync:shadow:') for s in passed)


def test_probe_audio_is_posted_as_two_speech_windows_not_long_silence(monkeypatch):
    """A synthetic two-send audio sample exercises silence splitting, not the eight-send qualification probe."""
    fixture = Path(__file__).resolve().parents[2] / 'testing/release_fixtures/transcription-release-probe.wav'
    with wave.open(str(fixture), 'rb') as handle:
        phrase = handle.readframes(handle.getnframes())
    sentence = 'He began a confused complaint against the wizard who had vanished behind the curtain on the left.'
    assert len(shadow._words(sentence)) == 17
    rate = 32000
    # A representative 60 s upload followed by a 2.4 s batch overlapping
    # the last 3 s. Both probe utterances lie before that boundary.
    pcm = bytearray(624 * rate // 10)
    pcm[rate : rate + len(phrase)] = phrase
    pcm[14 * rate : 14 * rate + len(phrase)] = phrase
    chunks = [(100.0, bytes(pcm[: 60 * rate])), (157.0, bytes(pcm[57 * rate :]))]
    monkeypatch.setattr(
        shadow, 'iter_audio_chunk_pcm', lambda _uid, _cid, wanted: ((t, p) for t, p in chunks if wanted(t, None))
    )
    monkeypatch.setattr(shadow, 'build_person_embeddings_cache', lambda _uid: {})
    monkeypatch.setattr(shadow, 'identify_speakers_for_segments', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(shadow, 'speaker_embedding_configured', lambda: False)
    posted = []

    def fake_parakeet(part, **_kwargs):
        posted.append(len(part) / rate)
        # A complete fixture in a long mostly silent POST can be repeated by
        # TDT. The fake makes that failure deterministic without a GPU.
        positions = []
        found = part.find(phrase)
        while found >= 0:
            positions.append(found)
            found = part.find(phrase, found + len(phrase))
        count = len(positions)
        if len(part) / rate > 20:
            count *= 2
        return [
            {
                'timestamp': [
                    float(positions[index % len(positions)] / rate),
                    float(positions[index % len(positions)] / rate + 4.9),
                ],
                'speaker': 'SPEAKER_00',
                'text': sentence,
            }
            for index in range(count)
        ]

    monkeypatch.setattr(shadow, 'parakeet_prerecorded_from_bytes', fake_parakeet)
    conversation = SimpleNamespace(
        id='probe',
        language='en',
        audio_files=[SimpleNamespace(chunk_timestamps=[100.0, 157.0])],
        started_at=datetime.fromtimestamp(100, timezone.utc),
        finished_at=datetime.fromtimestamp(162.4, timezone.utc),
        transcript_segments=[],
    )
    passed, audio = shadow._make_pass('probe', conversation, deadline=float('inf'), reserved_seconds=63)
    assert len(posted) == 2
    assert max(posted) < 6
    assert [round(segment.start, 1) for segment in passed] == [1.0, 14.0]
    assert sum(len(shadow._words(segment.text)) for segment in passed) == 34
    assert audio == {
        'coverage': 1.0,
        'tail_gap_seconds': 0.0,
        'audio_seconds': 62.4,
        'audio_origin_offset_seconds': 0.0,
    }


def test_forced_window_keeps_utterance_that_crosses_cut(monkeypatch):
    fixture = Path(__file__).resolve().parents[2] / 'testing/release_fixtures/transcription-release-probe.wav'
    with wave.open(str(fixture), 'rb') as handle:
        phrase = handle.readframes(handle.getnframes())
    rate = 32000
    pcm = bytearray(b'\x01\x00' * (100 * 16000))
    pcm[88 * rate : 88 * rate + len(phrase)] = phrase
    monkeypatch.setattr(shadow, 'iter_audio_chunk_pcm', lambda *_args: iter([(100.0, bytes(pcm))]))
    monkeypatch.setattr(shadow, 'build_person_embeddings_cache', lambda _uid: {})
    monkeypatch.setattr(shadow, 'identify_speakers_for_segments', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(shadow, 'speaker_embedding_configured', lambda: False)
    posted = []

    def fake_parakeet(part, **_kwargs):
        posted.append(len(part) / rate)
        onset = part.find(phrase)
        return (
            [{'timestamp': [onset / rate, onset / rate + 4.9], 'speaker': 'SPEAKER_00', 'text': 'fixture'}]
            if onset >= 0
            else []
        )

    monkeypatch.setattr(shadow, 'parakeet_prerecorded_from_bytes', fake_parakeet)
    conversation = SimpleNamespace(
        id='synthetic',
        language='en',
        audio_files=[SimpleNamespace(chunk_timestamps=[100.0])],
        finished_at=datetime.fromtimestamp(200, timezone.utc),
        transcript_segments=[],
    )
    passed, audio = shadow._make_pass('synthetic', conversation, deadline=float('inf'), reserved_seconds=100)
    assert posted == [90.0, 20.0]
    assert len(passed) == 1
    assert round(passed[0].start, 1) == 88.0
    assert audio['audio_seconds'] == 100


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
        transcript_segments=[live],
        audio_timeline=SimpleNamespace(version=2),
        structured=SimpleNamespace(model_dump=lambda: {'source_segment_ids': ['old']}),
    )
    result = shadow._compare(
        conversation, [passed], {'coverage': 1.0, 'tail_gap_seconds': 0.0, 'audio_seconds': 2.0}, {}
    )
    assert result['word_distance'] == 0
    assert result['live_owner_seconds'] == result['pass_owner_seconds'] == 2
    assert result['remap_safe']
    assert result['audio_timeline_v2'] is True
    assert 'Synthetic private words' not in repr(result)


def test_comparison_counts_competing_repeated_phrase_and_blocks_source_ref():
    phrase = 'the repeated synthetic phrase in this test'
    live = TranscriptSegment(id='live', text=phrase, start=2, end=6, is_user=False)
    passed = [
        TranscriptSegment(id=f'pass-{i}', text=phrase, start=17 + 5 * i, end=21 + 5 * i, is_user=False)
        for i in range(8)
    ]
    conversation = SimpleNamespace(
        transcript_segments=[live],
        audio_timeline=SimpleNamespace(version=2),
        structured=SimpleNamespace(model_dump=lambda: {'source_segment_ids': ['live']}),
    )
    result = shadow._compare(conversation, passed, {'coverage': 1.0, 'tail_gap_seconds': 0.0}, {})
    assert result['remap_ambiguous_count'] == 1
    assert result['remap_success_rate'] == 0
    assert result['remap_safe'] is False
    assert phrase not in repr(result)


def test_comparison_prometheus_metrics_use_only_closed_outcome_and_safety_labels(monkeypatch):
    observed = []

    class Metric:
        def __init__(self, name):
            self.name = name

        def labels(self, **labels):
            observed.append((self.name, labels))
            return self

        def observe(self, value):
            observed.append((self.name, value))

        def inc(self):
            observed.append((self.name, 'increment'))

    for name in ('SHADOW_WORD_DISTANCE', 'SHADOW_OWNER_DELTA', 'SHADOW_REMAP_SUCCESS', 'SHADOW_REMAP_SAFE'):
        monkeypatch.setattr(shadow, name, Metric(name))
    shadow._record_comparison_metrics(
        {
            'word_distance': 0.2,
            'live_owner_seconds': 8,
            'pass_owner_seconds': 6,
            'remap_success_rate': 0.75,
            'remap_safe': False,
        },
        'ok',
    )
    assert ('SHADOW_OWNER_DELTA', 0.25) in observed
    assert ('SHADOW_REMAP_SAFE', {'outcome': 'ok', 'safe': 'false'}) in observed
    assert all('uid' not in labels for _, labels in observed if isinstance(labels, dict))


def test_duplicate_reservation_never_writes_or_counts_result(monkeypatch):
    conversation = SimpleNamespace(audio_files=[SimpleNamespace(duration=10, chunk_timestamps=[100])])
    monkeypatch.setattr(
        shadow.conversations_db,
        'get_conversation',
        lambda *_args: {'synthetic': True, 'record_lane_owner': 'legacy_final_pass_v1'},
    )
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


def test_zero_budget_still_checks_existing_reservation(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS', '0')
    calls = []

    def eval_reservation(*args):
        calls.append(args)
        return 2  # Existing same-day reservation wins over the zero cap.

    monkeypatch.setattr(shadow.redis_client, 'eval', eval_reservation)
    assert shadow._reserve_budget('synthetic-conversation', 10) == 'duplicate'
    assert len(calls) == 1
    assert calls[0][-1] == 0


def test_result_write_is_fenced_by_account_deletion_intent(monkeypatch):
    client = MagicMock()
    user = MagicMock()
    parent = user.collection.return_value.document.return_value
    marker = MagicMock()
    client.collection.side_effect = lambda name: {
        'users': SimpleNamespace(document=lambda _uid: user),
        'account_deletions': SimpleNamespace(document=lambda _uid: marker),
    }[name]
    transaction = client.transaction.return_value
    monkeypatch.setattr(shadow, 'db', client)
    monkeypatch.setattr(shadow.firestore, 'transactional', lambda fn: fn)
    marker.get.return_value.exists = True

    shadow._store_result('synthetic-uid', 'synthetic-conversation', {'outcome': 'ok'})

    marker.get.assert_called_once_with(transaction=transaction)
    parent.get.assert_not_called()
    transaction.set.assert_not_called()

    marker.get.return_value.exists = False
    parent.get.return_value.exists = True
    parent.get.return_value.to_dict.return_value = {}
    shadow._store_result('synthetic-uid', 'synthetic-conversation', {'outcome': 'ok'})
    parent.get.assert_called_once_with(transaction=transaction)
    transaction.set.assert_called_once_with(parent.collection.return_value.document.return_value, {'outcome': 'ok'})


def test_flag_off_output_is_byte_identical_to_legacy(monkeypatch):
    """Fixture executed from origin/main e2edc7c15ca (not this PR's code).

    Capture uses synthetic PCM, ASR, cache and a fixed segment UUID; only the
    provider seams are mocked. The real main _make_pass generated the fixture.
    """
    import json
    from uuid import UUID
    from models import transcript_segment

    monkeypatch.setattr(transcript_segment.uuid, 'uuid4', lambda: UUID(int=1))
    monkeypatch.setattr(shadow, 'iter_audio_chunk_pcm', lambda *_a: iter([(100.0, b'\x01\x00' * 160000)]))
    monkeypatch.setattr(shadow, 'build_person_embeddings_cache', lambda _: {})
    monkeypatch.setattr(shadow, 'identify_speakers_for_segments', lambda *_a, **_kw: None)
    monkeypatch.setattr(shadow, 'speaker_embedding_configured', lambda: False)
    monkeypatch.setattr(
        final_pass_pyannote, 'run_final_pass', lambda *_a, **_kw: pytest.fail('flag-off calls diarizer')
    )
    monkeypatch.setitem(sys.modules, 'utils.conversations.final_pass_pyannote', None)
    monkeypatch.setattr(
        shadow,
        'parakeet_prerecorded_from_bytes',
        lambda *_a, **_kw: [{'timestamp': [2.0, 3.0], 'speaker': 'SPEAKER_00', 'text': 'synthetic'}],
    )

    def run():
        conversation = SimpleNamespace(
            id='fixture',
            language='en',
            audio_files=[SimpleNamespace(chunk_timestamps=[100.0])],
            started_at=None,
            finished_at=None,
            transcript_segments=[],
        )
        segments, audio = shadow._make_pass('fixture', conversation, deadline=float('inf'), reserved_seconds=10)
        return json.dumps({'segments': [s.model_dump() for s in segments], 'audio': audio}, sort_keys=True)

    monkeypatch.delenv('TRANSCRIPTION_FINAL_PASS_DIARIZER', raising=False)
    absent = run()
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_DIARIZER', 'legacy')
    explicit = run()
    expected = (Path(__file__).parent / 'fixtures' / 'transcription_shadow_main.json').read_bytes().rstrip(b'\n')
    assert absent.encode() == expected
    assert explicit.encode() == expected


def test_v2_audio_collection_and_duplicate_trim_stay_on_pcm16_sample_boundaries(monkeypatch):
    base = 100.123
    chunks = [(base, b'\x01\x00' * 160000), (base + 9.001, b'\x01\x00' * 160000)]
    assert int((base + 10 - chunks[1][0]) * 32000) % 2 == 1  # Legacy float truncation can split a sample.
    monkeypatch.setattr(shadow, 'iter_audio_chunk_pcm', lambda *_a: iter(chunks))
    monkeypatch.setattr(shadow, 'build_person_embeddings_cache', lambda _: {})
    monkeypatch.setattr(shadow, 'identify_speakers_for_segments', lambda *_a, **_kw: None)
    monkeypatch.setattr(shadow, 'speaker_embedding_configured', lambda: False)

    def transcribe(part, **_kw):
        assert len(part) % 2 == 0
        return [{'timestamp': [0, 1], 'text': 'synthetic', 'speaker': 'SPEAKER_00'}]

    monkeypatch.setattr(shadow, 'parakeet_prerecorded_from_bytes', transcribe)
    captured = []

    def final(pcm, *_a, **_kw):
        captured.append(pcm)
        return None, {'outcome': 'skipped_single'}

    monkeypatch.setattr(final_pass_pyannote, 'run_final_pass', final)
    conversation = SimpleNamespace(
        id='fixture',
        language='en',
        audio_files=[SimpleNamespace(chunk_timestamps=[t for t, _ in chunks])],
        started_at=None,
        finished_at=None,
        transcript_segments=[],
    )
    shadow._make_pass('fixture', conversation, deadline=float('inf'), reserved_seconds=20, final_result={})
    assert len(captured) == 1 and len(captured[0]) % 2 == 0
    assert captured[0][1::2] == b'\x00' * (len(captured[0]) // 2)
