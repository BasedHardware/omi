"""Synthetic lossless uploads and fenced failover; no vendor or customer reads."""

import io
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row  # noqa: F401
from tests.unit.test_batch_pipeline_second_provider import second_setup, WORDS
from tests.unit.test_prerecorded_vendor_fail_fast import install_http, stt_reply
from utils.batch_pipeline import recovery_recognizers as recognizers
from utils.batch_pipeline import quarantine_recovery as dispatcher
from utils.stt.modulate_batch import wav_duration_seconds


@pytest.mark.parametrize('cap', [160044, 160043])
def test_upload_boundary_preserves_pcm_duration_and_wav_below_cap(monkeypatch, cap):
    pcm = np.tile(np.array([-32768, -3, 0, 1, 32767], dtype='<i2'), 16000).tobytes()
    wav = recognizers.canonical_wav(pcm)
    assert len(wav) == 160044
    monkeypatch.setattr(recognizers, 'MODULATE_SAFE_UPLOAD_BYTES', cap)
    output = recognizers.recovery_audio(pcm)
    if cap == len(wav):
        assert output == wav
    else:
        assert output.startswith(b'fLaC') and len(output) <= cap
    samples, rate = sf.read(io.BytesIO(output), dtype='int16')
    assert rate == 16000 and samples.tobytes() == pcm
    assert wav_duration_seconds(output) == 5


@pytest.mark.parametrize('answer,expected', [(WORDS, 'recovered'), ([], 'failed_held')])
@pytest.mark.parametrize('safety_net', ['true', 'false'])
def test_modulate_error_falls_through_without_fabricating_empty_receipt(
    setup, monkeypatch, legacy_dependencies, answer, expected, safety_net
):
    client, binding, artifacts, modulate, soniox, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=Mock(return_value=(answer, 'fr'))
    )
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety_net)
    modulate.side_effect = TimeoutError('synthetic private failure')
    assert recovery.recover('bad', binding.owner_id) == expected
    modulate.assert_called_once()
    soniox.assert_called_once()
    receipts = row(client)['recovery']['recognizers']
    assert receipts['modulate']['outcome'] == 'error'
    assert receipts['modulate']['word_count'] is None
    assert receipts['soniox']['outcome'] == ('words' if answer else 'empty')
    assert row(client)['audio_uri'] == 'gs://synthetic/audio'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    soniox.assert_called_once()
    if not answer:
        artifacts.persist_recovery_result.assert_not_called()
        assert row(client)['recovery']['failure']['reason'] == 'provider_failed'


@pytest.mark.parametrize('blocked', ['route', 'allowance', 'privacy'])
def test_modulate_error_keeps_existing_soniox_guards(setup, monkeypatch, legacy_dependencies, blocked):
    client, binding, artifacts, modulate, soniox, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    modulate.side_effect = TimeoutError()
    if blocked == 'route':
        monkeypatch.setenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', 'false')
    elif blocked == 'allowance':
        monkeypatch.setattr(dispatcher, 'sync_allowed', lambda *a, **kw: len(a) < 3)
    else:
        from database.batch_pipeline_privacy import privacy_owner_key

        def revoke(*args, **kwargs):
            client.rows[('batch_pipeline_privacy', privacy_owner_key(binding.owner_id))] = {'generation': 1}
            raise TimeoutError()

        modulate.side_effect = revoke
    assert recovery.recover('bad', binding.owner_id) == ('cancelled' if blocked == 'privacy' else 'failed_held')
    soniox.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()


def test_large_upload_uses_one_flac_call_with_original_word_clocks(setup, monkeypatch, legacy_dependencies):
    client, binding, artifacts, modulate, soniox, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr(recognizers, 'MODULATE_SAFE_UPLOAD_BYTES', 10000)
    modulate.return_value = (WORDS, 'fr')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    modulate.assert_called_once()
    assert modulate.call_args.args[0].startswith(b'fLaC')
    assert modulate.call_args.kwargs['attempts'] == 2
    soniox.assert_not_called()
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['words'][0]['timestamp'] == [1, 2]
    assert payload['audio_seconds'] == 5 and payload['speech_seconds'] == 5


def test_incompressible_upload_skips_modulate_and_uses_guarded_soniox(setup, monkeypatch, legacy_dependencies):
    client, binding, artifacts, modulate, soniox, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=Mock(return_value=(WORDS, 'fr'))
    )
    monkeypatch.setattr(recognizers, 'MODULATE_SAFE_UPLOAD_BYTES', 10)
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    modulate.assert_not_called()
    soniox.assert_called_once()
    assert row(client)['recovery']['recognizers']['modulate']['outcome'] == 'error'


@pytest.mark.parametrize('flac', [True, False])
def test_modulate_multipart_type_and_burn_duration(monkeypatch, legacy_dependencies, flac):
    stt = legacy_dependencies[0]
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-only-key')
    monkeypatch.setenv('PRERECORDED_VENDOR_FAIL_FAST_ENABLED', 'false')
    pcm = b'\x01\x00' * 16000
    monkeypatch.setattr(recognizers, 'MODULATE_SAFE_UPLOAD_BYTES', 10000 if flac else 100000)
    audio = recognizers.recovery_audio(pcm)
    client = install_http(monkeypatch, stt, post=stt_reply())
    burn = Mock()
    monkeypatch.setattr(stt, 'record_vendor_burn', burn)
    stt.modulate_prerecorded_from_bytes(audio, attempts=2)
    upload = client.post.call_args.kwargs['files']['upload_file']
    assert (upload[0], upload[2]) == (('audio.flac', 'audio/flac') if flac else ('audio.wav', 'audio/wav'))
    assert upload[1].getvalue() == audio
    assert burn.call_args.args[1:] == ('ok', 1.0)
