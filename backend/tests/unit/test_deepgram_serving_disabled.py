"""Regression coverage for the no-Deepgram serving policy."""

from utils.stt import streaming
from utils.stt.pre_recorded import PrerecordedSTTService, get_prerecorded_service
from config.stt_provider_policy import STTServingSurface


def test_streaming_ignores_a_stale_deepgram_model_configuration(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.internal')

    service, language, model = streaming.get_stt_service_for_language('en')

    assert service == streaming.STTService.parakeet
    assert language == 'en'
    assert model == 'parakeet'


def test_ptt_ignores_a_stale_deepgram_model_configuration(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.internal')

    service, language, model = streaming.get_stt_service_for_language('en', surface=STTServingSurface.PTT)

    assert service == streaming.STTService.parakeet
    assert language == 'en'
    assert model == 'parakeet'


def test_prerecorded_ignores_a_stale_deepgram_model_configuration(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')

    service, language, model = get_prerecorded_service('ja')

    assert service == PrerecordedSTTService.MODULATE
    assert language == 'ja'
    assert model == 'velma-2'
