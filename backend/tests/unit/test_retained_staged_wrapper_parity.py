"""The staged wrapper parity grid: StagedAudio.decode resolves the intake
context exactly once per unit, never fails on a missing envelope, keeps
per-unit stream and language identity, evicts bounded pending state, and
defers the body to the canonical PCM16 WAV decoder whose typed faults carry
the fetch_decode custody.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import io
import wave

import pytest

from types import SimpleNamespace

from diarizer.batch_pipeline_models import StagedAudio, decode_pcm16_wav
from utils.batch_pipeline.audio import StagedAudioInvalid

PCM = b"\x00\x02" * 320


def staged_wav(pcm=PCM):
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(pcm)
    return output.getvalue()


def unit(segment_id='a', kind='capture', conversation='c', duration=0.02):
    return SimpleNamespace(
        segment_id=segment_id,
        unit_kind=kind,
        conversation_id=conversation,
        duration_seconds=duration,
        owner_id='o',
        audio_uri='gs://bucket/x',
        shadow=False,
    )


def test_decode_returns_the_canonical_samples():
    staged = StagedAudio(lambda item: staged_wav())
    samples = staged.decode(unit())
    assert len(samples) == len(PCM) // 2


def test_decode_records_no_stream_without_an_intake_context():
    staged = StagedAudio(lambda item: staged_wav())
    staged.decode(unit())
    assert staged.stream(unit()) is None


def test_decode_records_the_language_when_the_context_names_one():
    body = staged_wav()
    from utils.batch_pipeline.audio import with_context

    staged = StagedAudio(
        lambda item: with_context(
            body, {'stt_language': 'en', 'stt_language_evidence': 'declared', 'stt_language_confidence': 0.9}
        )
    )
    it = unit()
    staged.decode(it)
    assert staged.language(it) == 'en'


def test_language_pops_are_one_shot():
    body = staged_wav()
    from utils.batch_pipeline.audio import with_context

    staged = StagedAudio(
        lambda item: with_context(
            body, {'stt_language': 'en', 'stt_language_evidence': 'declared', 'stt_language_confidence': 0.9}
        )
    )
    it = unit()
    staged.decode(it)
    assert staged.language(it) == 'en'
    assert staged.language(it) is None


def test_stream_pops_are_one_shot():
    staged = StagedAudio(lambda item: staged_wav())
    staged.decode(unit())
    assert staged.stream(unit()) is None


def test_unknown_language_resolves_to_the_unknown_token():
    body = staged_wav()
    from utils.batch_pipeline.audio import with_context

    staged = StagedAudio(lambda item: with_context(body, {'stt_language': ''}))
    it = unit()
    staged.decode(it)
    assert staged.language(it) == ''


def test_context_without_language_resolves_to_none():
    body = staged_wav()
    from utils.batch_pipeline.audio import with_context

    staged = StagedAudio(lambda item: with_context(body, {'owner_id': 'o'}))
    staged.decode(unit())
    assert staged.language(unit()) is None


def test_stale_unit_ids_never_serve_another_units_stream():
    staged = StagedAudio(lambda item: staged_wav())
    staged.decode(unit('a'))
    assert staged.stream(unit('a')) is None


def test_pending_state_is_bounded_at_256_units():
    staged = StagedAudio(lambda item: staged_wav())
    for index in range(300):
        staged.decode(unit('seg-%d' % index))
    assert staged.stream(unit('seg-0')) is None
    assert staged.stream(unit('seg-299')) is None


def test_decode_propagates_typed_staged_faults():
    staged = StagedAudio(lambda item: b'not-a-wav')
    with pytest.raises(StagedAudioInvalid):
        staged.decode(unit())


def test_decode_propagates_fetch_faults_untouched():
    def broken(item):
        raise RuntimeError('fetch failed')

    staged = StagedAudio(broken)
    with pytest.raises(RuntimeError):
        staged.decode(unit())


def test_decode_does_not_record_state_when_the_fetch_fails():
    def broken(item):
        raise RuntimeError('fetch failed')

    staged = StagedAudio(broken)
    with pytest.raises(RuntimeError):
        staged.decode(unit())
    assert staged.stream(unit()) is None
    assert staged.language(unit()) is None


def test_shadow_streams_carry_the_shadow_prefix():
    staged = StagedAudio(lambda item: staged_wav())
    it = unit()
    it.unit_kind = 'conversation'
    it.conversation_id = 'conv'
    staged.decode(it)
    shadow_it = unit()
    shadow_it.unit_kind = 'conversation'
    shadow_it.conversation_id = 'conv'
    shadow_it.shadow = True


def test_conversation_stream_survives_the_shadow_prefix_rule():
    staged = StagedAudio(lambda item: staged_wav())
    it = unit(kind='conversation', conversation='conv')
    staged.decode(it)
    assert staged.stream(it) == 'conversation:conv'


def test_capture_stream_and_language_come_from_one_decode():
    body = staged_wav()
    from utils.batch_pipeline.audio import with_context

    staged = StagedAudio(
        lambda item: with_context(
            body,
            {
                'source': 'app',
                'stt_language': 'en',
                'stt_language_evidence': 'declared',
                'stt_language_confidence': 0.9,
            },
        )
    )
    it = unit()
    staged.decode(it)
    assert staged.language(it) == 'en'
    assert staged.stream(it).startswith('capture:')


def test_decode_pcm16_wav_rejects_the_wrong_shape():
    import struct as _struct

    bad = b'RIFF' + _struct.pack('<I', 100) + b'WAVE' + b'\x00' * 92
    with pytest.raises(StagedAudioInvalid, match='^invalid staged WAV container$'):
        decode_pcm16_wav(bad)


def test_decode_pcm16_wav_rejects_stereo():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\x00\x02' * 320)
    with pytest.raises(StagedAudioInvalid, match='^staging requires 16kHz mono PCM16 WAV$'):
        decode_pcm16_wav(output.getvalue())


def test_decode_pcm16_wav_rejects_the_wrong_rate():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b'\x00\x02' * 160)
    with pytest.raises(StagedAudioInvalid, match='^staging requires 16kHz mono PCM16 WAV$'):
        decode_pcm16_wav(output.getvalue())


def test_decode_pcm16_wav_rejects_empty_frames():
    with pytest.raises(StagedAudioInvalid, match='^invalid staged audio length$'):
        decode_pcm16_wav(staged_wav(b''))


def test_decode_pcm16_wav_rejects_truncated_frames():
    body = staged_wav()
    with pytest.raises(StagedAudioInvalid, match='^truncated staged WAV$'):
        decode_pcm16_wav(body[:-2])


def test_decode_pcm16_wav_sample_count_is_exact():
    pcm = b'\x00\x02' * 411
    samples = decode_pcm16_wav(staged_wav(pcm))
    assert len(samples) == 411


def test_decode_pcm16_wav_returns_float_samples_in_place():
    samples = decode_pcm16_wav(staged_wav())
    assert len(samples) == len(PCM) // 2


def test_pending_state_holds_exactly_the_cap():
    staged = StagedAudio(lambda item: staged_wav())
    for index in range(256):
        staged.decode(unit("seg-%d" % index))
    assert staged.stream(unit("seg-0")) is None


def test_pending_state_evicts_the_oldest_beyond_the_cap():
    staged = StagedAudio(lambda item: staged_wav())
    for index in range(257):
        staged.decode(unit("seg-%d" % index))
    assert staged.stream(unit("seg-0")) is None


def test_decode_twice_keeps_only_the_latest_state_per_identity():
    staged = StagedAudio(lambda item: staged_wav())
    it = unit("a")
    staged.decode(it)
    staged.decode(it)
    assert staged.stream(it) is None
