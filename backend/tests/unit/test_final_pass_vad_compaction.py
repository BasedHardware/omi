from types import SimpleNamespace

import pytest

from utils.stt import local_vad as vad
from utils.stt.vad_compaction import compact_speech, transcribe_with_speech_compaction, diarize_with_speech_compaction
from utils.sync import wal_audio_coverage_metrics as coverage_metrics


def pcm(seconds=10):
    return b'\x01\x00' * int(seconds * 16000)


def test_compaction_padding_and_original_word_clocks():
    result = compact_speech(pcm(), [{'start': 1, 'end': 2}, {'start': 7, 'end': 8}])
    assert result.spans == ((0, 11200, 28800), (28800, 107200, 28800))
    assert len(result.pcm) == int(3.6 * 32000)
    words = result.map_words([{'text': 'one', 'timestamp': [0.3, 1]}, {'text': 'two', 'timestamp': [2.1, 2.5]}])
    assert words[0]['timestamp'] == [1, 1.7]
    assert words[1]['timestamp'] == [7, 7.4]


def test_compaction_merges_padding_overlap_and_preserves_tail():
    result = compact_speech(pcm(), [{'start': 1, 'end': 2}, {'start': 2.1, 'end': 10}])
    assert len(result.spans) == 1
    assert result.spans[0][1] == 11200 and result.original_samples == 160000


def test_seam_word_abstains_instead_of_stretching_clock(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'true')
    original = pcm()
    calls = []

    def transcribe(audio):
        calls.append(audio)
        return (
            [{'text': 'boundary', 'timestamp': [1.7, 1.9]}]
            if audio != original
            else [{'text': 'kept', 'timestamp': [1, 2]}]
        )

    result = transcribe_with_speech_compaction(
        original, transcribe, lambda p: [{'start': 1, 'end': 2}, {'start': 7, 'end': 8}]
    )
    assert result == [{'text': 'kept', 'timestamp': [1, 2]}]
    assert len(calls) == 2 and calls[-1] is original


def test_disabled_is_identical_and_never_detects(monkeypatch):
    monkeypatch.delenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', raising=False)
    original = pcm()
    sentinel = object()

    def transcribe(audio):
        assert audio is original
        return sentinel

    assert transcribe_with_speech_compaction(original, transcribe, lambda p: pytest.fail('VAD off')) is sentinel


def test_vad_failure_keeps_original_and_does_not_call_vendor_twice(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'true')
    original, calls = pcm(), []

    def broken(audio):
        raise OSError('unavailable')

    def transcribe(audio):
        calls.append(audio)
        return []

    assert transcribe_with_speech_compaction(original, transcribe, broken) == []
    assert calls == [original]


def test_vad_empty_skips_asr_and_tuple_metadata_preserved(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'true')
    assert transcribe_with_speech_compaction(pcm(), lambda p: pytest.fail('silence'), lambda p: []) == []
    result = transcribe_with_speech_compaction(
        pcm(), lambda p: ([{'text': 'word', 'timestamp': [0.3, 1]}], 'en'), lambda p: [{'start': 1, 'end': 2}]
    )
    assert result == ([{'text': 'word', 'timestamp': [1, 1.7]}], 'en')


def test_stt_failure_is_not_misclassified_as_vad_failure(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'true')

    def broken(audio):
        raise RuntimeError('ASR error')

    with pytest.raises(RuntimeError, match='ASR error'):
        transcribe_with_speech_compaction(pcm(), broken, lambda p: [{'start': 1, 'end': 2}])


def test_diarizer_turn_crossing_seam_splits_on_original_timeline(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'true')
    calls = []
    output = {
        'turns': [{'start': 0, 'end': 3.6, 'speaker': 'S0'}],
        'overlaps': [],
        'provenance': {'backend': 'pyannote'},
    }

    def diarize(audio, **kwargs):
        calls.append(len(audio))
        return SimpleNamespace(model_dump=lambda: dict(output))

    result = diarize_with_speech_compaction(
        pcm(),
        SimpleNamespace(backend='pyannote', diarize=diarize),
        lambda p: [{'start': 1, 'end': 2}, {'start': 7, 'end': 8}],
    )
    assert calls == [int(3.6 * 32000)]
    assert result['turns'] == [{'start': 0.7, 'end': 2.5, 'speaker': 'S0'}, {'start': 6.7, 'end': 8.5, 'speaker': 'S0'}]


def test_diarizer_empty_vad_retains_original_evidence(monkeypatch):
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'true')
    original = pcm()

    def diarize(audio, **kwargs):
        assert audio is original
        return SimpleNamespace(model_dump=lambda: {'original': True})

    assert diarize_with_speech_compaction(
        original, SimpleNamespace(backend='pyannote', diarize=diarize), lambda p: []
    ) == {'original': True}


@pytest.mark.parametrize(
    'segment', [{'start': -1, 'end': 2}, {'start': 1, 'end': float('nan')}, {'start': 1, 'end': 100}]
)
def test_invalid_vad_regions_rejected(segment):
    with pytest.raises(ValueError):
        compact_speech(pcm(), [segment])


def test_abstention_labels_are_bounded(monkeypatch):
    observed = []

    class Counter:
        def labels(self, **labels):
            observed.append(labels)
            return self

        def inc(self):
            pass

    monkeypatch.setattr(coverage_metrics, 'COVERAGE', Counter())
    coverage_metrics.record_coverage_outcome('abstained', 'evidence')
    coverage_metrics.record_coverage_outcome('abstained', 'uid-sensitive-random')
    assert observed == [{'outcome': 'abstained', 'reason': 'evidence'}, {'outcome': 'abstained', 'reason': 'other'}]


def test_offline_detector_keeps_final_partial_window(monkeypatch):
    observed = []

    def detect(samples):
        observed.append(len(samples))
        return [{'start': 0, 'end': len(samples) / 16000, 'duration': len(samples) / 16000}]

    monkeypatch.setattr(vad, 'segments_from_16khz_samples', detect)
    result = vad.offline_pcm_speech_segments(b'\x00\x00' * 513)
    assert observed == [1024]
    assert result == [{'start': 0, 'end': 513 / 16000, 'duration': 513 / 16000}]
