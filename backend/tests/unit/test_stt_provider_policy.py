"""Regression coverage for the single source of truth governing STT serving."""

from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    STTServingSurface,
    canonical_model_config,
    provider_for_model_token,
    provider_is_enabled,
)


def test_hosted_deepgram_is_disabled_for_every_serving_surface():
    assert all(not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, surface) for surface in STTServingSurface)


def test_self_hosted_deepgram_is_explicitly_limited_to_streaming():
    assert provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PTT)


def test_policy_owns_the_safe_model_order_for_every_serving_surface():
    expected = 'parakeet,modulate-velma-2'
    for surface in STTServingSurface:
        assert canonical_model_config(surface) == expected
        assert provider_is_enabled(PARAKEET_PROVIDER, surface)
        assert provider_is_enabled(MODULATE_PROVIDER, surface)


def test_deepgram_model_tokens_are_classified_as_self_hosted_only():
    assert provider_for_model_token('dg-nova-3') == DEEPGRAM_SELF_HOSTED_PROVIDER
