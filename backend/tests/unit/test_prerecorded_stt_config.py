from __future__ import annotations

import pytest

from config.prerecorded_stt import (
    DEFAULT_STT_PRERECORDED_MODELS,
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


def test_empty_model_preference_uses_non_deepgram_defaults():
    assert get_prerecorded_models({'STT_PRERECORDED_MODEL': ' , '}) == DEFAULT_STT_PRERECORDED_MODELS


def test_literal_and_opaque_deploy_requirements_share_provider_contract():
    expected = {'HOSTED_PARAKEET_API_URL', 'MODULATE_API_KEY'}
    for model_config in ('dg-nova-3', 'modulate-velma-2', 'parakeet', 'unknown-model', 'parakeet,dg-nova-3'):
        assert set(required_env_for_model_config(model_config)) == expected
    assert set(required_env_for_model_config(None, source_is_opaque=True)) == expected


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
