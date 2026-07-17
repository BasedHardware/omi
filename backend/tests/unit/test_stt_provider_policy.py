"""Regression coverage for the single source of truth governing STT serving."""

from config.stt_provider_policy import (
    DEEPGRAM_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    STTServingSurface,
    canonical_model_config,
    provider_for_model_token,
    provider_is_enabled,
)


def test_deepgram_is_disabled_for_every_serving_surface():
    assert all(not provider_is_enabled(DEEPGRAM_PROVIDER, surface) for surface in STTServingSurface)


def test_policy_owns_the_safe_model_order_for_every_serving_surface():
    expected = 'parakeet,modulate-velma-2'
    for surface in STTServingSurface:
        assert canonical_model_config(surface) == expected
        assert provider_is_enabled(PARAKEET_PROVIDER, surface)
        assert provider_is_enabled(MODULATE_PROVIDER, surface)


def test_retired_model_tokens_stay_classified_by_the_policy():
    assert provider_for_model_token('dg-nova-3') == DEEPGRAM_PROVIDER
