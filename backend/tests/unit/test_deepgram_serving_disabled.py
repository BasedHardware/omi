"""Regression coverage for Deepgram serving: hosted restored, guard rails kept.

The rails the removal introduced still hold and are asserted here: batch never
silently gains a paid provider, a runtime without credentials skips Deepgram
instead of failing mid-session, and a deployment that declares self-hosting can
never fall back to the hosted API.
"""

import pytest

from utils.stt import streaming
from utils.stt.pre_recorded import PrerecordedSTTService, get_prerecorded_service
from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    STTServingSurface,
    deepgram_provider_for_runtime,
    provider_is_enabled,
)


def test_streaming_selects_hosted_deepgram_when_configured(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', object())

    service, language, model = streaming.get_stt_service_for_language('en', multi_lang_enabled=False)

    assert service == streaming.STTService.deepgram
    assert language == 'en'
    assert model == 'nova-3'


def test_streaming_skips_deepgram_when_no_client_is_configured(monkeypatch):
    """No credentials must degrade to Velma, not fail at connect."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)

    service, language, model = streaming.get_stt_service_for_language('en')

    assert service == streaming.STTService.modulate
    assert model == 'velma-2'


def test_ptt_never_selects_deepgram_even_when_configured(monkeypatch):
    """PTT cannot connect Deepgram, so it must not be selectable there."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', object())
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.internal')

    service, language, model = streaming.get_stt_service_for_language('en', surface=STTServingSurface.PTT)

    assert service == streaming.STTService.modulate
    assert language == 'en'
    assert model == 'velma-2'


def test_prerecorded_still_ignores_a_deepgram_model_configuration(monkeypatch):
    """Batch stays on Parakeet/Velma even if a manifest names Deepgram."""
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'dg-nova-3')

    service, language, model = get_prerecorded_service('ja')

    assert service == PrerecordedSTTService.MODULATE
    assert language == 'ja'
    assert model == 'velma-2'


def test_streaming_can_select_explicit_self_hosted_deepgram(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', True)
    monkeypatch.setattr(streaming, 'deepgram', object())

    service, language, model = streaming.get_stt_service_for_language('en')

    assert service == streaming.STTService.deepgram
    assert language == 'multi'
    assert model == 'nova-3'


def test_deepgram_client_cannot_be_created_without_configuration(monkeypatch):
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)

    with pytest.raises(RuntimeError, match='Deepgram is not configured'):
        streaming._deepgram_client_for_request()


def test_self_hosted_endpoint_cannot_be_the_hosted_deepgram_api():
    with pytest.raises(ValueError, match='must not point to api.deepgram.com'):
        streaming._require_self_hosted_deepgram_endpoint('https://api.deepgram.com')


def test_self_hosted_endpoint_must_be_set_when_self_hosting_is_declared():
    with pytest.raises(ValueError, match='DEEPGRAM_SELF_HOSTED_URL must be set'):
        streaming._require_self_hosted_deepgram_endpoint('')


def test_policy_keeps_hosted_and_self_hosted_deepgram_distinct():
    assert provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING)
    assert provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PTT)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PTT)


def test_runtime_reports_the_deployment_it_actually_serves_from():
    assert deepgram_provider_for_runtime(False) == DEEPGRAM_CLOUD_PROVIDER
    assert deepgram_provider_for_runtime(True) == DEEPGRAM_SELF_HOSTED_PROVIDER
