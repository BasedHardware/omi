from __future__ import annotations

import pytest

from config.prerecorded_stt import (
    PrerecordedSTTConfigurationError,
    PrerecordedSTTService,
    get_prerecorded_models,
    require_provider_environment,
    required_env_for_model_config,
)


def test_model_preferences_are_read_from_current_environment(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_MODEL', ' parakeet, dg-nova-3 ')
    assert get_prerecorded_models() == ('parakeet', 'dg-nova-3')

    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'modulate-velma-2')
    assert get_prerecorded_models() == ('modulate-velma-2',)


def test_empty_model_preference_retains_deepgram_default():
    assert get_prerecorded_models({'STT_PRERECORDED_MODEL': ' , '}) == ('dg-nova-3',)


def test_literal_and_opaque_deploy_requirements_share_provider_contract():
    assert required_env_for_model_config('dg-nova-3') == ('DEEPGRAM_API_KEY',)
    assert required_env_for_model_config('modulate-velma-2') == (
        'MODULATE_API_KEY',
        'DEEPGRAM_API_KEY',
    )
    assert required_env_for_model_config('parakeet') == (
        'HOSTED_PARAKEET_API_URL',
        'DEEPGRAM_API_KEY',
    )
    assert required_env_for_model_config('unknown-model') == ('DEEPGRAM_API_KEY',)
    assert required_env_for_model_config('parakeet,dg-nova-3') == (
        'HOSTED_PARAKEET_API_URL',
        'DEEPGRAM_API_KEY',
    )
    assert required_env_for_model_config(None, source_is_opaque=True) == (
        'DEEPGRAM_API_KEY',
        'MODULATE_API_KEY',
        'HOSTED_PARAKEET_API_URL',
    )


def test_runtime_configuration_error_identifies_provider_and_missing_binding():
    with pytest.raises(PrerecordedSTTConfigurationError) as exc_info:
        require_provider_environment(PrerecordedSTTService.PARAKEET, {})

    assert exc_info.value.provider == PrerecordedSTTService.PARAKEET
    assert exc_info.value.missing_env == 'HOSTED_PARAKEET_API_URL'


def test_whitespace_only_provider_binding_is_missing():
    with pytest.raises(PrerecordedSTTConfigurationError):
        require_provider_environment(
            PrerecordedSTTService.MODULATE,
            {'MODULATE_API_KEY': '   '},
        )
