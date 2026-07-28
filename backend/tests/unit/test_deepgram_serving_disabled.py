"""Regression coverage for hosted-Deepgram removal and self-hosted retention."""

import pytest

from utils.stt import streaming
from utils.stt.pre_recorded import PrerecordedSTTService, get_prerecorded_service
from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    STTServingSurface,
    provider_is_enabled,
)


def test_streaming_ignores_a_stale_deepgram_model_configuration(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.internal')

    service, language, model = streaming.get_stt_service_for_language('en', multi_lang_enabled=False)

    # After #10048 fix: Modulate is the safe primary; Deepgram retirement must be subtractive
    assert service == streaming.STTService.modulate
    assert language == 'en'
    assert model == 'velma-2'


def test_ptt_ignores_a_self_hosted_deepgram_model_configuration(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', True)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.internal')

    service, language, model = streaming.get_stt_service_for_language('en', surface=STTServingSurface.PTT)

    # After #10048 fix: Modulate is the safe primary for PTT too
    assert service == streaming.STTService.modulate
    assert language == 'en'
    assert model == 'velma-2'


def test_prerecorded_ignores_a_stale_deepgram_model_configuration(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')

    service, language, model = get_prerecorded_service('ja')

    assert service == PrerecordedSTTService.MODULATE
    assert language == 'ja'
    assert model == 'velma-2'


def test_streaming_can_select_explicit_self_hosted_deepgram(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', True)

    service, language, model = streaming.get_stt_service_for_language('en')

    assert service == streaming.STTService.deepgram
    assert language == 'multi'
    assert model == 'nova-3'


def test_hosted_deepgram_client_cannot_be_created_without_self_hosting(monkeypatch):
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)

    with pytest.raises(RuntimeError, match='Hosted Deepgram is disabled'):
        streaming._deepgram_client_for_request()


def test_self_hosted_endpoint_cannot_be_the_hosted_deepgram_api():
    with pytest.raises(ValueError, match='must not point to api.deepgram.com'):
        streaming._require_self_hosted_deepgram_endpoint('https://api.deepgram.com')


def test_policy_keeps_hosted_and_self_hosted_deepgram_distinct():
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING)
    assert provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
