from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace
import numpy as np
import pytest
import io
import wave

# torch is an optional dependency
import sys
sys.modules['torch'] = MagicMock()

from diarizer.batch_pipeline_models import (
    ParakeetWords,
    pin_parakeet_decoding,
    assert_eager_decoding,
    PyannoteDiarizer,
    PyannoteVAD,
    StagedAudio,
    _finite_number,
    _valid_self_lid_context,
    stt_language,
    decode_pcm16_wav,
    create_local_worker
)
from config.batch_pipeline_providers import ProviderConfig
from dataclasses import replace

def test_parakeet_words_transcribe_batch():
    model = Mock()
    hypotheses = [
        SimpleNamespace(
            text='hello world',
            timestamp={'word': [{'word': 'hello', 'start': 0.1, 'end': 0.5}, {'word': 'world', 'start': 0.6, 'end': 1.0}]}
        ),
        SimpleNamespace(
            text='',
            timestamp={'word': []}
        )
    ]
    model.transcribe.return_value = hypotheses

    words = ParakeetWords(model)
    samples = [np.zeros(16000), np.zeros(16000)]
    result = words.transcribe_batch(samples)

    assert len(result) == 2
    assert result[0] == [{'word': 'hello', 'timestamp': [0.1, 0.5]}, {'word': 'world', 'timestamp': [0.6, 1.0]}]
    assert result[1] == []
    model.transcribe.assert_called_once_with(
        samples,
        batch_size=2,
        timestamps=True,
        return_hypotheses=True,
        num_workers=0,
        verbose=False
    )

def test_parakeet_words_transcribe_batch_missing_word_clocks(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    model = Mock()
    hypotheses = [
        SimpleNamespace(
            text='hello world',
            timestamp={'word': []} # Text but no words
        )
    ]
    model.transcribe.return_value = hypotheses

    words = ParakeetWords(model)
    samples = [np.zeros(16000)]
    with pytest.raises(ValueError, match="Parakeet returned text without word clocks"):
        words.transcribe_batch(samples)

def test_parakeet_words_recover_empty():
    model = Mock()
    # Mocking single retry output
    hypotheses = [
        SimpleNamespace(
            text='hello world',
            timestamp={'word': [{'word': 'hello', 'start': 2.1, 'end': 2.5}, {'word': 'world', 'start': 2.6, 'end': 3.0}]}
        )
    ]
    model.transcribe.return_value = hypotheses

    words = ParakeetWords(model)
    samples = np.zeros(16000 * 2) # 2 seconds

    # 2 seconds left padding, 4 seconds right padding -> total 8 seconds
    # Word 'hello' at 2.1-2.5 will map to 0.1-0.5

    result = words.recover_empty(samples, max_padded_seconds=120)
    assert len(result) == 2
    assert result[0]['word'] == 'hello'
    assert result[0]['timestamp'][0] == pytest.approx(0.1)
    assert result[0]['timestamp'][1] == pytest.approx(0.5)
    assert result[1]['word'] == 'world'
    assert result[1]['timestamp'][0] == pytest.approx(0.6)
    assert result[1]['timestamp'][1] == pytest.approx(1.0)

def test_parakeet_words_recover_empty_oversize():
    model = Mock()
    words = ParakeetWords(model)
    samples = np.zeros(16000 * 10) # 10 seconds, padded would be 10 + 2 + 2 = 14
    result = words.recover_empty(samples, max_padded_seconds=10) # max is 10, so won't fit
    assert result is None
    model.transcribe.assert_not_called()

def test_parakeet_words_recover_empty_before_dispatch_fails():
    model = Mock()
    words = ParakeetWords(model)
    samples = np.zeros(16000 * 2)

    # Return false from before_dispatch
    result = words.recover_empty(samples, max_padded_seconds=120, before_dispatch=lambda: False)
    assert result is None
    model.transcribe.assert_not_called()

def test_parakeet_words_recover_empty_after_dispatch_called():
    model = Mock()
    model.transcribe.return_value = [
        SimpleNamespace(text='', timestamp={'word': []})
    ]
    words = ParakeetWords(model)
    samples = np.zeros(16000 * 2)

    after_dispatch = Mock()
    words.recover_empty(samples, max_padded_seconds=120, after_dispatch=after_dispatch)
    after_dispatch.assert_called_once_with(8.0) # 2 + 2 + max(2, 8-2-2) = 2 + 2 + 4 = 8

def test_pin_parakeet_decoding():
    model = MagicMock()
    model.cfg.decoding = MagicMock()
    model.decoding.decoding.decoding_computer.allow_cuda_graphs = False
    model.decoding.decoding.decoding_computer.full_graph = None
    pin_parakeet_decoding(model)
    model.change_decoding_strategy.assert_called_once()
    model.decoding.decoding.disable_cuda_graphs.assert_called_once()

def test_assert_eager_decoding_fails():
    model = MagicMock()
    model.decoding.decoding.decoding_computer.allow_cuda_graphs = True
    with pytest.raises(RuntimeError, match="worker CUDA graph policy violated"):
        assert_eager_decoding(model)

    model.decoding.decoding.decoding_computer.allow_cuda_graphs = False
    model.decoding.decoding.decoding_computer.full_graph = "something"
    with pytest.raises(RuntimeError, match="worker CUDA graph policy violated"):
        assert_eager_decoding(model)

def test_pyannote_diarizer():
    model = Mock()
    model.return_value = MagicMock()
    model.return_value.itertracks.return_value = []

    diarizer = PyannoteDiarizer(model)
    samples = np.zeros(16000)

    # Mock leaf_timings
    with patch('diarizer.batch_pipeline_models.leaf_timings') as leaf_timings:
        leaf_timings.active.return_value = MagicMock()
        leaf_timings.embedding_hook.return_value = MagicMock()
        result = diarizer(samples)
    assert result == {'turns': [], 'overlaps': [], 'backend': 'pyannote'}

def test_pyannote_vad():
    model = Mock()
    timeline_mock = MagicMock()
    support_mock = [SimpleNamespace(start=0.1, end=0.5)]
    timeline_mock.support.return_value = support_mock
    model.return_value.get_timeline.return_value = timeline_mock

    vad = PyannoteVAD(model)
    samples = np.zeros(16000)
    result = vad(samples)

    assert result == [(0.1, 0.5)]

def test_decode_pcm16_wav():
    # Valid
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(np.zeros(16000, dtype='<i2').tobytes())

    result = decode_pcm16_wav(buf.getvalue())
    assert len(result) == 16000
    assert result.dtype == np.float32

def test_decode_pcm16_wav_invalid_format():
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as f:
        f.setnchannels(2) # Invalid channels
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(np.zeros(32000, dtype='<i2').tobytes())

    with pytest.raises(ValueError, match="staging requires 16kHz mono PCM16 WAV"):
        decode_pcm16_wav(buf.getvalue())

def test_decode_pcm16_wav_empty():
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        # Empty

    with pytest.raises(ValueError, match="invalid staged audio length"):
        decode_pcm16_wav(buf.getvalue())

def test_finite_number():
    assert _finite_number(1) == True
    assert _finite_number(1.5) == True
    assert _finite_number(True) == False
    assert _finite_number("1") == False
    assert _finite_number(float('inf')) == False
    assert _finite_number(float('nan')) == False

def test_staged_audio():
    fetch_audio = Mock()
    fetch_audio.return_value = b'test_audio_body'

    with patch('diarizer.batch_pipeline_models.decode_pcm16_wav') as decode_mock:
        decode_mock.return_value = np.zeros(16000)
        staged = StagedAudio(fetch_audio)

        item = MagicMock()
        item.segment_id = 'test_segment'
        item.duration_seconds = 1.0
        item.owner_id = 'test_owner'
        item.shadow = False

        result = staged.decode(item)

        assert result is decode_mock.return_value
        fetch_audio.assert_called_once_with(item)
        assert staged.stream(item) is None

def test_staged_audio_max_pending():
    fetch_audio = Mock(return_value=b'test')
    with patch('diarizer.batch_pipeline_models.decode_pcm16_wav') as decode_mock:
        decode_mock.return_value = np.zeros(16000)
        staged = StagedAudio(fetch_audio)

        # Add max + 1 items
        for i in range(staged.MAX_PENDING + 1):
            item = MagicMock()
            item.segment_id = f'test_segment_{i}'
            item.duration_seconds = 1.0
            item.owner_id = 'test_owner'
            item.shadow = False
            staged.decode(item)

        assert len(staged._streams) == staged.MAX_PENDING
        assert len(staged._languages) == staged.MAX_PENDING
        assert 'test_segment_0' not in staged._streams
        assert 'test_segment_0' not in staged._languages

def test_staged_audio_shadow_stream():
    fetch_audio = Mock(return_value=b'test')
    with patch('diarizer.batch_pipeline_models.decode_pcm16_wav') as decode_mock, \
         patch('diarizer.batch_pipeline_models.capture_stream') as stream_mock:
        decode_mock.return_value = np.zeros(16000)
        stream_mock.return_value = 'original_stream'

        staged = StagedAudio(fetch_audio)

        item = MagicMock()
        item.segment_id = 'test_segment'
        item.duration_seconds = 1.0
        item.owner_id = 'test_owner'
        item.shadow = True

        staged.decode(item)
        assert staged.stream(item) == 'shadow:original_stream'

def test_staged_audio_language():
    fetch_audio = Mock(return_value=b'test')
    with patch('diarizer.batch_pipeline_models.decode_pcm16_wav') as decode_mock, \
         patch('diarizer.batch_pipeline_models.stt_language') as lang_mock:
        decode_mock.return_value = np.zeros(16000)
        lang_mock.return_value = 'en'

        staged = StagedAudio(fetch_audio)

        item = MagicMock()
        item.segment_id = 'test_segment'
        item.duration_seconds = 1.0
        item.owner_id = 'test_owner'

        staged.decode(item)
        assert staged.language(item) == 'en'
        assert staged.language(item) is None # popped

def test_stt_language_not_dict():
    assert stt_language(None) is None
    assert stt_language("not_a_dict") is None

def test_stt_language_missing_key():
    assert stt_language({}) is None

def test_stt_language_invalid_value():
    assert stt_language({'stt_language': 123}) is None

def test_stt_language_supported_audio_lid_valid():
    context = {
        'stt_language': 'en',
        'stt_language_evidence': 'audio_lid',
        'stt_language_confidence': 0.9
    }
    assert stt_language(context, duration_seconds=10.0) == 'en'

def test_stt_language_supported_audio_lid_low_confidence():
    context = {
        'stt_language': 'en',
        'stt_language_evidence': 'audio_lid',
        'stt_language_confidence': 0.1
    }
    assert stt_language(context, duration_seconds=10.0) is None

def test_stt_language_supported_declared():
    context = {
        'stt_language': 'en',
        'stt_language_evidence': 'declared',
        'stt_language_confidence': 1.0
    }
    assert stt_language(context, duration_seconds=10.0) == 'en'

def test_stt_language_unsupported_evidence():
    context = {
        'stt_language': 'en',
        'stt_language_evidence': 'something_else',
        'stt_language_confidence': 0.9
    }
    assert stt_language(context, duration_seconds=10.0) is None

def test_valid_self_lid_context_invalid_version():
    context = {'version': 2} # Should be INTAKE_CONTEXT_VERSION (1)
    assert _valid_self_lid_context(context, duration_seconds=10.0, expected_owner_id='owner1', expected_segment_id='seg1') == False

def test_valid_self_lid_context_missing_fields():
    context = {'version': 1, 'owner_id': 'owner1', 'segment_id': 'seg1'}
    # missing source, job_id, content_id, stt_language_probe_seconds
    assert _valid_self_lid_context(context, duration_seconds=10.0, expected_owner_id='owner1', expected_segment_id='seg1') == False

def test_valid_self_lid_context_valid():
    context = {
        'version': 1,
        'owner_id': 'owner1',
        'segment_id': 'seg1',
        'source': 'test',
        'job_id': 'job1',
        'content_id': 'content1',
        'stt_language_probe_seconds': 10.0
    }
    assert _valid_self_lid_context(context, duration_seconds=10.0, expected_owner_id='owner1', expected_segment_id='seg1') == True

def test_stt_language_self_lid_valid():
    context = {
        'version': 1,
        'owner_id': 'owner1',
        'segment_id': 'seg1',
        'source': 'test',
        'job_id': 'job1',
        'content_id': 'content1',
        'stt_language_probe_seconds': 10.0,
        'stt_language': 'es',
        'stt_language_evidence': 'self_lid',
        'stt_language_confidence': 0.99
    }
    assert stt_language(context, duration_seconds=10.0, expected_owner_id='owner1', expected_segment_id='seg1') == 'es'

def test_stt_language_self_lid_invalid_context():
    context = {
        'version': 2, # invalid version
        'owner_id': 'owner1',
        'segment_id': 'seg1',
        'source': 'test',
        'job_id': 'job1',
        'content_id': 'content1',
        'stt_language_probe_seconds': 10.0,
        'stt_language': 'es',
        'stt_language_evidence': 'self_lid',
        'stt_language_confidence': 0.99
    }
    assert stt_language(context, duration_seconds=10.0, expected_owner_id='owner1', expected_segment_id='seg1') is None

def test_stt_language_self_lid_invalid_language_format():
    context = {
        'version': 1,
        'owner_id': 'owner1',
        'segment_id': 'seg1',
        'source': 'test',
        'job_id': 'job1',
        'content_id': 'content1',
        'stt_language_probe_seconds': 10.0,
        'stt_language': 'e', # too short
        'stt_language_evidence': 'self_lid',
        'stt_language_confidence': 0.99
    }
    assert stt_language(context, duration_seconds=10.0, expected_owner_id='owner1', expected_segment_id='seg1') is None

def test_create_local_worker():
    fetch_audio = Mock()
    persist_result = Mock()
    vad_model = Mock()
    parakeet_model = MagicMock()
    parakeet_model.cfg.decoding = MagicMock()
    parakeet_model.decoding.decoding.decoding_computer.allow_cuda_graphs = False
    parakeet_model.decoding.decoding.decoding_computer.full_graph = None

    pyannote_model = Mock()

    with patch('diarizer.batch_pipeline_models.provider_config') as pc_mock:
        pc = replace(ProviderConfig(), pool_kind='dedicated_batch')

        pc_mock.return_value = pc

        worker = create_local_worker(
            fetch_audio=fetch_audio,
            persist_result=persist_result,
            vad_model=vad_model,
            parakeet_model=parakeet_model,
            pyannote_model=pyannote_model
        )

        assert worker is not None
        assert pc_mock.called

def test_create_local_worker_invalid_pool_kind():
    with patch('diarizer.batch_pipeline_models.provider_config') as pc_mock:
        pc = replace(ProviderConfig(), pool_kind='shared_live', max_unit_seconds=100, max_padded_seconds=120)

        pc_mock.return_value = pc

        with pytest.raises(ValueError, match="local model chain requires dedicated batch GPU"):
            create_local_worker(
                fetch_audio=Mock(),
                persist_result=Mock(),
                vad_model=Mock(),
                parakeet_model=Mock(),
                pyannote_model=Mock()
            )
