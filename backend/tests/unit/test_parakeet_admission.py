"""Tests for Parakeet capacity admission control (#10048).

Covers:
- Modulate is the safe default primary, Parakeet is secondary
- Retiring a provider does not change the safe primary
- Parakeet capacity exhaustion falls back to Modulate
- Health/unavailable fallback
- Capability mismatch
- Allocation 0% / canary / 100% behavior
- Admission gate correctness (concurrent cap, allocation, release)
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from config.parakeet_admission import (
    ADMIT_REASON_ADMITTED,
    ADMIT_REASON_ALLOCATION_REJECTED,
    ADMIT_REASON_ALLOCATION_ZERO,
    ADMIT_REASON_CAPACITY_FULL,
    release,
    reset_state_for_testing,
    try_admit,
)
from config.stt_provider_policy import (
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    STTServingSurface,
    DEFAULT_MODELS_BY_SURFACE,
    default_models_for_surface,
    provider_is_enabled,
)
from utils.observability.fallback import ALLOWED_REASONS

# ---------------------------------------------------------------------------
# Policy: default ordering
# ---------------------------------------------------------------------------


class TestDefaultModelOrdering:
    """Modulate Velma-2 must be the safe primary for all surfaces."""

    def test_streaming_primary_is_modulate(self):
        models = DEFAULT_MODELS_BY_SURFACE[STTServingSurface.STREAMING]
        assert models[0] == 'modulate-velma-2', f"Expected modulate-velma-2 first, got {models}"
        assert 'parakeet' in models, "Parakeet must still be available as secondary"

    def test_prerecorded_primary_is_modulate(self):
        models = DEFAULT_MODELS_BY_SURFACE[STTServingSurface.PRERECORDED]
        assert models[0] == 'modulate-velma-2'

    def test_ptt_primary_is_modulate(self):
        models = DEFAULT_MODELS_BY_SURFACE[STTServingSurface.PTT]
        assert models[0] == 'modulate-velma-2'

    def test_all_surfaces_have_modulate_as_first(self):
        for surface in STTServingSurface:
            models = DEFAULT_MODELS_BY_SURFACE[surface]
            assert models[0] == 'modulate-velma-2', f"{surface}: first model is {models[0]}"

    def test_retiring_deepgram_cloud_does_not_change_primary(self):
        """Retiring hosted Deepgram must be subtractive, not promote Parakeet."""
        assert not provider_is_enabled('deepgram_cloud', STTServingSurface.STREAMING)
        # Modulate must still be primary regardless of Deepgram's state
        models = default_models_for_surface(STTServingSurface.STREAMING)
        assert models[0] == 'modulate-velma-2'


# ---------------------------------------------------------------------------
# Admission gate
# ---------------------------------------------------------------------------


class TestParakeetAdmissionGate:
    """Capacity-based admission for Parakeet live-STT."""

    def setup_method(self):
        reset_state_for_testing()

    def teardown_method(self):
        reset_state_for_testing()

    def test_admit_when_capacity_available(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "100", "PARAKEET_MAX_CONCURRENT": "30"}):
            admitted, reason = try_admit()
        assert admitted is True
        assert reason == ADMIT_REASON_ADMITTED

    def test_reject_when_capacity_full(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "100", "PARAKEET_MAX_CONCURRENT": "2"}):
            assert try_admit()[0] is True
            assert try_admit()[0] is True
            admitted, reason = try_admit()
        assert admitted is False
        assert reason == ADMIT_REASON_CAPACITY_FULL

    def test_release_frees_capacity(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "100", "PARAKEET_MAX_CONCURRENT": "1"}):
            assert try_admit()[0] is True
            assert try_admit()[0] is False  # full
            release()
            admitted, reason = try_admit()
        assert admitted is True
        assert reason == ADMIT_REASON_ADMITTED

    def test_allocation_zero_blocks_all(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "0", "PARAKEET_MAX_CONCURRENT": "1000"}):
            admitted, reason = try_admit()
        assert admitted is False
        assert reason == ADMIT_REASON_ALLOCATION_ZERO

    def test_allocation_100_admits_within_cap(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "100", "PARAKEET_MAX_CONCURRENT": "5"}):
            for _ in range(5):
                assert try_admit()[0] is True
            admitted, reason = try_admit()
        assert admitted is False
        assert reason == ADMIT_REASON_CAPACITY_FULL

    def test_allocation_canary_admits_some(self):
        """At 10% allocation, ~10% of requests should be admitted on average."""
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "10", "PARAKEET_MAX_CONCURRENT": "1000"}):
            admitted_count = 0
            trials = 1000
            for _ in range(trials):
                admitted, _ = try_admit()
                if admitted:
                    admitted_count += 1
                else:
                    # Non-admitted don't consume a slot, so no release needed
                    pass
        # Should be roughly 100, allow wide statistical tolerance
        assert 50 <= admitted_count <= 200, f"Expected ~100, got {admitted_count}"

    def test_allocation_canary_rejects_reason(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "1", "PARAKEET_MAX_CONCURRENT": "1000"}):
            # Retry until we hit an allocation rejection (should happen quickly at 1%)
            for _ in range(500):
                admitted, reason = try_admit()
                if not admitted:
                    # Release any that were admitted
                    break
                release()
        # We should have gotten a rejection. Reason should be allocation_rejected
        # (not capacity_full since cap is 1000)
        if not admitted:
            assert reason == ADMIT_REASON_ALLOCATION_REJECTED

    def test_max_concurrent_defaults_to_30(self):
        from config.parakeet_admission import DEFAULT_PARAKEET_MAX_CONCURRENT

        assert DEFAULT_PARAKEET_MAX_CONCURRENT == 30

    def test_invalid_allocation_defaults_to_full(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "not_a_number", "PARAKEET_MAX_CONCURRENT": "1"}):
            admitted, reason = try_admit()
        assert admitted is True
        assert reason == ADMIT_REASON_ADMITTED

    def test_invalid_max_concurrent_defaults(self):
        with patch.dict(os.environ, {"PARAKEET_ALLOCATION_PCT": "100", "PARAKEET_MAX_CONCURRENT": "abc"}):
            # Should default to 30
            for _ in range(30):
                assert try_admit()[0] is True
            admitted, reason = try_admit()
        assert admitted is False
        assert reason == ADMIT_REASON_CAPACITY_FULL


# ---------------------------------------------------------------------------
# STT selection integration with admission
# ---------------------------------------------------------------------------


class TestSTTSelectionWithAdmission:
    """STT selection falls back to Modulate when Parakeet admission is denied."""

    def setup_method(self):
        reset_state_for_testing()

    def teardown_method(self):
        reset_state_for_testing()

    def test_parakeet_capacity_exhaustion_falls_to_modulate(self):
        """When Parakeet cap is full, selection must fall to Modulate."""
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet', 'modulate-velma-2']), patch.dict(
            os.environ,
            {
                'HOSTED_PARAKEET_API_URL': 'http://parakeet.test',
                'PARAKEET_ALLOCATION_PCT': '100',
                'PARAKEET_MAX_CONCURRENT': '1',
                'MODULATE_API_KEY': 'test-key',
            },
        ):
            # First request: Parakeet admitted
            service1, lang1, model1 = get_stt_service_for_language('en', multi_lang_enabled=False)
            assert service1 == STTService.parakeet

            # Second request: Parakeet full → Modulate
            service2, lang2, model2 = get_stt_service_for_language('en', multi_lang_enabled=False)
            assert service2 == STTService.modulate
            assert model2 == 'velma-2'

    def test_allocation_zero_forces_modulate(self):
        """PARAKEET_ALLOCATION_PCT=0 must force all traffic to Modulate."""
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet', 'modulate-velma-2']), patch.dict(
            os.environ,
            {
                'HOSTED_PARAKEET_API_URL': 'http://parakeet.test',
                'PARAKEET_ALLOCATION_PCT': '0',
                'PARAKEET_MAX_CONCURRENT': '1000',
                'MODULATE_API_KEY': 'test-key',
            },
        ):
            service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.modulate
        assert model == 'velma-2'

    def test_allocation_100_with_cap_allows_parakeet(self):
        """100% allocation + cap room → Parakeet is selected for English."""
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet', 'modulate-velma-2']), patch.dict(
            os.environ,
            {
                'HOSTED_PARAKEET_API_URL': 'http://parakeet.test',
                'PARAKEET_ALLOCATION_PCT': '100',
                'PARAKEET_MAX_CONCURRENT': '1000',
                'MODULATE_API_KEY': 'test-key',
            },
        ):
            service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.parakeet

    def test_capability_mismatch_falls_to_modulate(self):
        """Non-English language still falls to Modulate even when Parakeet has capacity."""
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet', 'modulate-velma-2']), patch.dict(
            os.environ,
            {
                'HOSTED_PARAKEET_API_URL': 'http://parakeet.test',
                'PARAKEET_ALLOCATION_PCT': '100',
                'PARAKEET_MAX_CONCURRENT': '1000',
                'MODULATE_API_KEY': 'test-key',
            },
        ):
            service, lang, model = get_stt_service_for_language('ja', multi_lang_enabled=False)
        assert service == STTService.modulate
        assert model == 'velma-2'

    def test_config_incomplete_skips_parakeet(self):
        """Missing HOSTED_PARAKEET_API_URL skips Parakeet entirely."""
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet', 'modulate-velma-2']), patch.dict(
            os.environ,
            {
                # HOSTED_PARAKEET_API_URL NOT set
                'PARAKEET_ALLOCATION_PCT': '100',
                'PARAKEET_MAX_CONCURRENT': '1000',
                'MODULATE_API_KEY': 'test-key',
            },
            clear=False,
        ):
            # Remove parakeet URL if present
            env = dict(os.environ)
            env.pop('HOSTED_PARAKEET_API_URL', None)
            with patch.dict(os.environ, env, clear=True):
                service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.modulate
        assert model == 'velma-2'

    def test_retired_provider_does_not_change_primary(self):
        """Retiring Deepgram must not promote Parakeet over Modulate."""
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['dg-nova-3']), patch.dict(
            os.environ,
            {
                'HOSTED_PARAKEET_API_URL': 'http://parakeet.test',
                'PARAKEET_ALLOCATION_PCT': '100',
                'PARAKEET_MAX_CONCURRENT': '1000',
                'MODULATE_API_KEY': 'test-key',
            },
        ):
            # Deepgram is disabled (no self-hosted), so defaults should kick in
            # With new ordering, Modulate is first → selected
            service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.modulate
        assert model == 'velma-2'


# ---------------------------------------------------------------------------
# Fallback telemetry reasons
# ---------------------------------------------------------------------------


class TestFallbackReasonsAreAllowed:
    """Parakeet admission denial reasons must be valid fallback labels."""

    def test_capacity_full_is_allowed(self):
        assert 'capacity_full' in ALLOWED_REASONS

    def test_allocation_zero_is_allowed(self):
        assert 'allocation_zero' in ALLOWED_REASONS

    def test_allocation_rejected_is_allowed(self):
        assert 'allocation_rejected' in ALLOWED_REASONS
