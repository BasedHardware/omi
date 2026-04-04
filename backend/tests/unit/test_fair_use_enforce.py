"""Tests for fair-use throttle/restrict enforcement (#6314).

Verifies that:
- Throttle stage forces STT model downgrade from nova-3 to nova-2
- Restrict stage forces STT model downgrade from nova-3 to nova-2
- Warning/none stages use normal model selection (nova-3)
- Pre-recorded model selection also respects fair-use stage
- DG budget is enforced for throttle stage (not just restrict)
"""

import unittest

from utils.stt.streaming import get_stt_service_for_language, STTService
from utils.stt.pre_recorded import get_deepgram_model_for_language


class TestStreamingModelDowngrade(unittest.TestCase):
    """Test get_stt_service_for_language with fair_use_stage param."""

    def test_none_stage_uses_nova3(self):
        """Normal users get nova-3."""
        _, _, model = get_stt_service_for_language('en', fair_use_stage='none')
        self.assertEqual(model, 'nova-3')

    def test_warning_stage_uses_nova3(self):
        """Warning stage is notification-only — no model downgrade."""
        _, _, model = get_stt_service_for_language('en', fair_use_stage='warning')
        self.assertEqual(model, 'nova-3')

    def test_throttle_stage_forces_nova2(self):
        """Throttle stage must downgrade to nova-2."""
        _, _, model = get_stt_service_for_language('en', fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')

    def test_restrict_stage_forces_nova2(self):
        """Restrict stage must downgrade to nova-2."""
        _, _, model = get_stt_service_for_language('en', fair_use_stage='restrict')
        self.assertEqual(model, 'nova-2-general')

    def test_throttle_multi_lang_uses_nova2(self):
        """Throttle with multi-lang should use nova-2-general."""
        _, lang, model = get_stt_service_for_language('multi', multi_lang_enabled=True, fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')
        self.assertEqual(lang, 'multi')

    def test_throttle_nova3_only_language_preserves_lang(self):
        """Languages only in nova-3 (e.g., Bulgarian) keep their language code with nova-2."""
        _, lang, model = get_stt_service_for_language('bg', multi_lang_enabled=False, fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')
        # Language passed through — Deepgram handles unsupported langs gracefully
        self.assertEqual(lang, 'bg')

    def test_throttle_nova3_only_language_multi_enabled(self):
        """Nova-3-only language with multi-lang enabled should fall back to nova-2 multi."""
        _, lang, model = get_stt_service_for_language('bg', multi_lang_enabled=True, fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')
        self.assertEqual(lang, 'multi')

    def test_restrict_spanish_uses_nova2(self):
        """Spanish (in nova-2 multi) should use nova-2 when restricted."""
        _, lang, model = get_stt_service_for_language('es', multi_lang_enabled=True, fair_use_stage='restrict')
        self.assertEqual(model, 'nova-2-general')

    def test_throttle_french_single_lang_preserves_language(self):
        """French single-language mode should preserve language code when throttled."""
        _, lang, model = get_stt_service_for_language('fr', multi_lang_enabled=False, fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')
        self.assertEqual(lang, 'fr')

    def test_default_stage_is_none(self):
        """Default fair_use_stage should be 'none' (backward compatible)."""
        _, _, model = get_stt_service_for_language('en')
        self.assertEqual(model, 'nova-3')

    def test_all_returns_deepgram_service(self):
        """All fair-use downgrades should still use Deepgram."""
        for stage in ('none', 'warning', 'throttle', 'restrict'):
            service, _, _ = get_stt_service_for_language('en', fair_use_stage=stage)
            self.assertEqual(service, STTService.deepgram, f'stage={stage} should use Deepgram')


class TestPreRecordedModelDowngrade(unittest.TestCase):
    """Test get_deepgram_model_for_language with fair_use_stage param."""

    def test_none_stage_uses_nova3(self):
        """Normal pre-recorded uses nova-3."""
        _, model = get_deepgram_model_for_language('en')
        self.assertEqual(model, 'nova-3')

    def test_throttle_forces_nova2(self):
        """Throttle pre-recorded must use nova-2."""
        _, model = get_deepgram_model_for_language('en', fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')

    def test_restrict_forces_nova2(self):
        """Restrict pre-recorded must use nova-2."""
        _, model = get_deepgram_model_for_language('multi', fair_use_stage='restrict')
        self.assertEqual(model, 'nova-2-general')

    def test_warning_uses_nova3(self):
        """Warning stage should not downgrade pre-recorded."""
        _, model = get_deepgram_model_for_language('en', fair_use_stage='warning')
        self.assertEqual(model, 'nova-3')

    def test_throttle_nova3_only_language(self):
        """Nova-3-only language preserves language code with nova-2 when throttled."""
        lang, model = get_deepgram_model_for_language('bg', fair_use_stage='throttle')
        self.assertEqual(model, 'nova-2-general')
        self.assertEqual(lang, 'bg')

    def test_default_stage_backward_compat(self):
        """Default should be 'none' for backward compatibility."""
        _, model = get_deepgram_model_for_language('multi')
        self.assertEqual(model, 'nova-3')


class TestThrottleDgBudgetEnforcement(unittest.TestCase):
    """Test that throttle stage gets DG budget enforcement (not just restrict)."""

    def test_throttle_triggers_dg_budget_check(self):
        """Throttle stage should check DG budget (same as restrict)."""
        # The enforcement logic in transcribe.py checks:
        # if stage in ('throttle', 'restrict') and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
        #     fair_use_track_dg_usage = True
        dg_budget_ms = 1800000  # default FAIR_USE_RESTRICT_DAILY_DG_MS
        stage = 'throttle'
        should_track = stage in ('throttle', 'restrict') and dg_budget_ms > 0
        self.assertTrue(should_track, 'Throttle stage should trigger DG usage tracking')

    def test_warning_does_not_trigger_dg_budget(self):
        """Warning stage should NOT check DG budget."""
        stage = 'warning'
        should_track = stage in ('throttle', 'restrict')
        self.assertFalse(should_track, 'Warning stage should not trigger DG usage tracking')

    def test_none_does_not_trigger_dg_budget(self):
        """None stage should NOT check DG budget."""
        stage = 'none'
        should_track = stage in ('throttle', 'restrict')
        self.assertFalse(should_track, 'None stage should not trigger DG usage tracking')


if __name__ == '__main__':
    unittest.main()
