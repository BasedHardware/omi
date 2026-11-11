"""Regression coverage for Deepgram retirement (2026-08-27, no contract).

The rails asserted here: no surface admits Deepgram — not a dg-* slot in the
chain, not a self-hosted flag, not a BYOK key — batch never silently gains a
paid provider, a runtime without credentials degrades to Velma instead of
failing mid-session, and the endpoint guards stay for anyone reviving the
self-hosted client.
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


def test_streaming_never_selects_retired_hosted_deepgram_when_configured(monkeypatch):
    """A chain that still lists dg-nova-3 with a live client must degrade, not route."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', object())
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', True)

    service, language, model = streaming.get_stt_service_for_language('en', multi_lang_enabled=False)

    assert service == streaming.STTService.modulate
    assert language == 'en'
    assert model == 'velma-2'


def test_streaming_skips_deepgram_when_no_client_is_configured(monkeypatch):
    """No credentials must degrade to Velma, not fail at connect."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', True)
    monkeypatch.setattr(streaming, 'get_byok_key', lambda provider: None)

    service, language, model = streaming.get_stt_service_for_language('en')

    assert service == streaming.STTService.modulate
    assert model == 'velma-2'


def test_ptt_never_selects_deepgram_even_when_configured(monkeypatch):
    """PTT cannot connect Deepgram, so it must not be selectable there."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', object())
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', True)
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


def test_streaming_never_selects_retired_self_hosted_deepgram(monkeypatch):
    """Retirement covers the self-hosted deployment: the flag alone routes nothing."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', True)
    monkeypatch.setattr(streaming, 'deepgram', object())
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', True)

    service, _, model = streaming.get_stt_service_for_language('en')

    assert service == streaming.STTService.modulate
    assert model == 'velma-2'


def test_byok_does_not_reactivate_retired_deepgram(monkeypatch):
    """Retirement outranks BYOK: a user key never re-admits a retired provider."""
    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', True)
    monkeypatch.setattr(streaming, 'get_byok_key', lambda provider: 'user-key')

    service, _, model = streaming.get_stt_service_for_language('en', multi_lang_enabled=False)

    assert service == streaming.STTService.modulate
    assert model == 'velma-2'


def test_managed_client_is_not_built_at_import(monkeypatch):
    """Importing must not depend on Deepgram configuration."""
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', False)
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.delenv('DEEPGRAM_API_KEY', raising=False)

    assert streaming._managed_deepgram_client() is None
    assert streaming._managed_deepgram_ready is True


def test_deepgram_client_cannot_be_created_without_configuration(monkeypatch):
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', True)
    monkeypatch.setattr(streaming, 'get_byok_key', lambda provider: None)

    with pytest.raises(RuntimeError, match='Deepgram is not configured'):
        streaming._deepgram_client_for_request()


def test_self_hosted_endpoint_cannot_be_the_hosted_deepgram_api():
    with pytest.raises(ValueError, match='must not point to api.deepgram.com'):
        streaming._require_self_hosted_deepgram_endpoint('https://api.deepgram.com')


def test_self_hosted_endpoint_must_be_set_when_self_hosting_is_declared():
    with pytest.raises(ValueError, match='DEEPGRAM_SELF_HOSTED_URL must be set'):
        streaming._require_self_hosted_deepgram_endpoint('')


def test_policy_retires_both_deepgram_deployments_on_every_surface():
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PTT)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PTT)


def test_runtime_reports_the_deployment_it_actually_serves_from():
    assert deepgram_provider_for_runtime(False) == DEEPGRAM_CLOUD_PROVIDER
    assert deepgram_provider_for_runtime(True) == DEEPGRAM_SELF_HOSTED_PROVIDER
