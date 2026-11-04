"""An explicit client preference cannot revive the retired plain streaming slot."""

from unittest.mock import Mock

import pytest

from utils.stt import streaming
from config.policy.listen import ListenSessionPolicy, current_listen_policy, service_models


@pytest.mark.parametrize(
    'configured', [None, ['parakeet', 'modulate-velma-2', 'soniox'], ['modulate-velma-2', 'soniox']]
)
def test_explicit_parakeet_falls_back_and_switch_can_readmit(monkeypatch, configured):
    monkeypatch.delenv('STT_GPU_FLEET_OFF', raising=False)
    monkeypatch.delenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', raising=False)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    if configured is not None:
        monkeypatch.setattr(streaming, 'stt_service_models', configured)
    fallback = Mock()
    monkeypatch.setattr(streaming, 'record_fallback', fallback)
    assert (
        streaming.get_stt_service_for_language('en', multi_lang_enabled=False, preferred_service='parakeet')[0]
        == streaming.STTService.modulate
    )
    assert fallback.call_args.kwargs['component'] == 'stt_selection'
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
    assert fallback.call_args.kwargs['from_mode'] == 'parakeet'
    monkeypatch.setenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', 'true')
    # Rollback restores the preference even with the new two-vendor runtime list.
    if configured is not None:
        assert (
            streaming.get_stt_service_for_language('en', multi_lang_enabled=False, preferred_service='parakeet')[0]
            == streaming.STTService.parakeet
        )
    assert (
        streaming.get_stt_service_for_language(
            'en', multi_lang_enabled=False, exclude=frozenset({'modulate', 'soniox'})
        )[0]
        == streaming.STTService.parakeet
    )


@pytest.mark.parametrize('pinned', [False, True])
@pytest.mark.parametrize('slot_enabled,fleet_off', [(False, False), (True, False), (True, True)])
def test_rollback_restores_effective_models_without_mutating_the_runtime_list(
    monkeypatch, pinned, slot_enabled, fleet_off
):
    configured = ['modulate-velma-2', 'soniox']
    monkeypatch.setenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', str(slot_enabled))
    monkeypatch.setenv('STT_GPU_FLEET_OFF', str(fleet_off))
    policy = ListenSessionPolicy(service_models=tuple(configured)) if pinned else None
    token = current_listen_policy.set(policy)
    try:
        assert service_models(configured) == (
            ['modulate-velma-2', 'soniox'] if fleet_off else configured + (['parakeet'] if slot_enabled else [])
        )
        assert configured == ['modulate-velma-2', 'soniox']
        if policy is not None:
            assert policy.service_models == tuple(configured)
    finally:
        current_listen_policy.reset(token)


@pytest.mark.parametrize('provider', [streaming.STTService.parakeet, streaming.STTService.soniox])
def test_primary_readiness_resolves_non_modulate_providers(monkeypatch, provider):
    monkeypatch.delenv('STT_GPU_FLEET_OFF', raising=False)
    monkeypatch.setattr(streaming, 'stt_service_models', [provider.value])
    assert streaming._primary_streaming_service() == provider


@pytest.mark.parametrize('pinned', [False, True])
@pytest.mark.parametrize('exclude,expected', [(frozenset(), 'modulate'), (frozenset({'modulate'}), 'soniox')])
def test_retired_plain_only_managed_chain_falls_through_to_vendors(monkeypatch, pinned, exclude, expected):
    monkeypatch.setenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', 'false')
    monkeypatch.setenv('STT_GPU_FLEET_OFF', 'false')
    monkeypatch.setenv('SONIOX_API_KEY', 'test-soniox-key')
    monkeypatch.setattr(streaming, 'stt_service_models', ['parakeet'])
    policy = ListenSessionPolicy(service_models=('parakeet',)) if pinned else None
    token = current_listen_policy.set(policy)
    try:
        service, language, _ = streaming.get_stt_service_for_language(
            'en', multi_lang_enabled=False, preferred_service='parakeet', window_uid='test-user', exclude=exclude
        )
        assert service.value == expected
        assert language == 'en'
        assert not streaming.parakeet_is_configured_fallback('en')
        assert service_models(['parakeet']) == ['parakeet', 'modulate-velma-2', 'soniox']
        if policy is not None:
            assert policy.service_models == ('parakeet',)
    finally:
        current_listen_policy.reset(token)


def test_streaming_retirement_does_not_rewrite_ptt_models(monkeypatch):
    monkeypatch.setenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', 'false')
    monkeypatch.setenv('STT_GPU_FLEET_OFF', 'false')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    monkeypatch.setattr(streaming, 'stt_service_models', ['parakeet'])
    assert (
        streaming.get_stt_service_for_language(
            'en', multi_lang_enabled=False, surface=streaming.STTServingSurface.PTT, preferred_service='parakeet'
        )[0]
        == streaming.STTService.parakeet
    )
