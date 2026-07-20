"""Regression coverage for the single source of truth governing STT serving."""

from pathlib import Path

import pytest
import yaml

from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_PROVIDER,
    STTServingSurface,
    canonical_model_config,
    modulate_supports_language,
    parakeet_supports_language,
    provider_for_model_token,
    provider_is_enabled,
    supports_live_multilingual_mode,
)

ROOT = Path(__file__).resolve().parents[3]
PARAKEET_VALUES_FILES = (
    ROOT / 'backend/charts/parakeet/dev_omi_parakeet_values.yaml',
    ROOT / 'backend/charts/parakeet/prod_omi_parakeet_values.yaml',
)


def _chart_env_value(values_path: Path, name: str) -> str | None:
    values = yaml.safe_load(values_path.read_text(encoding='utf-8'))
    for entry in values.get('env', []) if isinstance(values, dict) else []:
        if isinstance(entry, dict) and entry.get('name') == name:
            return str(entry.get('value')) if 'value' in entry else None
    return None


def test_hosted_deepgram_is_disabled_for_every_serving_surface():
    assert all(not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, surface) for surface in STTServingSurface)


def test_self_hosted_deepgram_is_explicitly_limited_to_streaming():
    assert provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PTT)


def test_policy_owns_the_safe_model_order_for_every_serving_surface():
    expected = 'modulate-velma-2,parakeet'
    for surface in STTServingSurface:
        assert canonical_model_config(surface) == expected
        assert provider_is_enabled(PARAKEET_PROVIDER, surface)
        assert provider_is_enabled(MODULATE_PROVIDER, surface)


def test_deepgram_model_tokens_are_classified_as_self_hosted_only():
    assert provider_for_model_token('dg-nova-3') == DEEPGRAM_SELF_HOSTED_PROVIDER


def test_parakeet_capability_tracks_the_model_selected_for_each_surface():
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'en')
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'es')
    assert parakeet_supports_language(STTServingSurface.PTT, 'en')
    assert not parakeet_supports_language(STTServingSurface.PTT, 'multi')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'es')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'multi')


@pytest.mark.parametrize('values_path', PARAKEET_VALUES_FILES)
def test_parakeet_chart_models_match_the_capability_policy(values_path: Path):
    """A model deployment swap must update the policy before routing can change (#10009)."""
    assert _chart_env_value(values_path, 'PARAKEET_MODEL') == PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]
    assert (
        _chart_env_value(values_path, 'PARAKEET_STREAM_MODEL') == PARAKEET_MODEL_BY_SURFACE[STTServingSurface.STREAMING]
    )
    assert PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PTT] == PARAKEET_MODEL_BY_SURFACE[STTServingSurface.STREAMING]


def test_live_multilingual_policy_normalizes_supported_locales_and_rejects_unknown_languages():
    assert supports_live_multilingual_mode('zh-TW')
    assert supports_live_multilingual_mode('ar')
    assert modulate_supports_language('es-419')
    assert not supports_live_multilingual_mode('xx-unsupported')
