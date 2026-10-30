"""Tests for plan-aware fair-use caps and the hard daily-audio ceiling
(utils/fair_use.py).

``utils.fair_use`` imports cleanly; we toggle ``FAIR_USE_ENABLED`` per-test via
``patch.object`` and drive the pure detection functions with injected
``speech_totals`` so no Redis is touched. See backend/docs/test_isolation.md.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import utils.fair_use as fair_use_mod
from models.fair_use import SoftCapTrigger
from models.users import PlanType

DEFAULT_TIER_PLANS = [PlanType.basic, PlanType.plus, None]
UNLIMITED_TIER_PLANS = [
    PlanType.unlimited_v2,
    PlanType.unlimited,
    PlanType.operator,
    PlanType.architect,
]


def _totals(daily_ms=0, three_day_ms=0, weekly_ms=0):
    return {'daily_ms': daily_ms, 'three_day_ms': three_day_ms, 'weekly_ms': weekly_ms}


class TestFairUseCapsForPlan:
    def test_default_tier_plans_get_default_caps(self):
        expected = (
            fair_use_mod.FAIR_USE_DAILY_SPEECH_MS,
            fair_use_mod.FAIR_USE_3DAY_SPEECH_MS,
            fair_use_mod.FAIR_USE_WEEKLY_SPEECH_MS,
        )
        for plan in DEFAULT_TIER_PLANS:
            assert fair_use_mod.fair_use_caps_for_plan(plan) == expected, plan
            assert fair_use_mod._is_unlimited_tier(plan) is False, plan

    def test_unlimited_tier_plans_get_raised_caps(self):
        expected = (
            fair_use_mod.FAIR_USE_DAILY_SPEECH_MS_UNLIMITED,
            fair_use_mod.FAIR_USE_3DAY_SPEECH_MS_UNLIMITED,
            fair_use_mod.FAIR_USE_WEEKLY_SPEECH_MS_UNLIMITED,
        )
        for plan in UNLIMITED_TIER_PLANS:
            assert fair_use_mod.fair_use_caps_for_plan(plan) == expected, plan
            assert fair_use_mod._is_unlimited_tier(plan) is True, plan

    def test_unlimited_daily_cap_is_higher_than_default(self):
        # Guards the whole point of the feature: Unlimited must tolerate more before scrutiny.
        assert fair_use_mod.FAIR_USE_DAILY_SPEECH_MS_UNLIMITED > fair_use_mod.FAIR_USE_DAILY_SPEECH_MS

    def test_free_and_plus_are_never_unlimited_tier(self):
        # The whole point of the tier split: Free/Plus must never get the raised caps.
        assert fair_use_mod._is_unlimited_tier(PlanType.basic) is False
        assert fair_use_mod._is_unlimited_tier(PlanType.plus) is False
        assert fair_use_mod._is_unlimited_tier(None) is False

    def test_is_unlimited_tier_accepts_raw_string_plan(self):
        # subscription.plan may arrive as a raw string; PlanType is a str enum so membership holds.
        assert fair_use_mod._is_unlimited_tier('unlimited_v2') is True
        assert fair_use_mod._is_unlimited_tier('basic') is False

    def test_unknown_plan_fails_closed_during_classification(self):
        with pytest.raises(ValueError, match='unknown catalog plan'):
            fair_use_mod._is_unlimited_tier('future_plan_123')


class TestCheckSoftCapsPlanAware:
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_default_tier_triggers_daily_at_three_hours(self):
        totals = _totals(daily_ms=fair_use_mod.FAIR_USE_DAILY_SPEECH_MS + 1)
        for plan in [PlanType.basic, PlanType.plus]:
            triggers = [t['trigger'] for t in fair_use_mod.check_soft_caps('u', totals, plan)]
            assert SoftCapTrigger.DAILY in triggers, plan

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_unlimited_tier_does_not_trigger_below_its_higher_daily_cap(self):
        # Just over the DEFAULT daily cap but under the UNLIMITED daily cap.
        totals = _totals(daily_ms=fair_use_mod.FAIR_USE_DAILY_SPEECH_MS + 1)
        assert fair_use_mod.check_soft_caps('u', totals, PlanType.unlimited_v2) == []

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_unlimited_tier_triggers_daily_above_its_own_cap(self):
        totals = _totals(daily_ms=fair_use_mod.FAIR_USE_DAILY_SPEECH_MS_UNLIMITED + 1)
        triggers = [t['trigger'] for t in fair_use_mod.check_soft_caps('u', totals, PlanType.unlimited_v2)]
        assert SoftCapTrigger.DAILY in triggers

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_plan_none_is_backwards_compatible_default_tier(self):
        totals = _totals(daily_ms=fair_use_mod.FAIR_USE_DAILY_SPEECH_MS + 1)
        triggers = [t['trigger'] for t in fair_use_mod.check_soft_caps('u', totals)]
        assert SoftCapTrigger.DAILY in triggers

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_reported_threshold_matches_the_tier(self):
        totals = _totals(daily_ms=fair_use_mod.FAIR_USE_DAILY_SPEECH_MS_UNLIMITED + 1)
        [daily] = [
            t
            for t in fair_use_mod.check_soft_caps('u', totals, PlanType.unlimited_v2)
            if t['trigger'] == SoftCapTrigger.DAILY
        ]
        assert daily['threshold_ms'] == fair_use_mod.FAIR_USE_DAILY_SPEECH_MS_UNLIMITED


class TestDailyAudioCeiling:
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_exceeded_at_or_above_ceiling(self):
        totals = _totals(daily_ms=fair_use_mod.MAX_DAILY_AUDIO_MS)
        assert fair_use_mod.is_daily_audio_ceiling_exceeded('u', totals) is True

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_not_exceeded_below_ceiling(self):
        totals = _totals(daily_ms=fair_use_mod.MAX_DAILY_AUDIO_MS - 1)
        assert fair_use_mod.is_daily_audio_ceiling_exceeded('u', totals) is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'MAX_DAILY_AUDIO_MS', 0)
    def test_disabled_when_ceiling_is_zero(self):
        totals = _totals(daily_ms=10**12)
        assert fair_use_mod.is_daily_audio_ceiling_exceeded('u', totals) is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_when_fair_use_off(self):
        totals = _totals(daily_ms=10**12)
        assert fair_use_mod.is_daily_audio_ceiling_exceeded('u', totals) is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_exempt_uid_bypasses_ceiling(self):
        totals = _totals(daily_ms=10**12)
        with patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', {'vip'}):
            assert fair_use_mod.is_daily_audio_ceiling_exceeded('vip', totals) is False


class TestHardRestrictionUsesPlanCaps:
    @pytest.mark.parametrize(
        'plan,window,cap_index',
        [
            (PlanType.unlimited_v2, 'daily_ms', 0),
            (PlanType.unlimited_v2, 'three_day_ms', 1),
            (PlanType.unlimited_v2, 'weekly_ms', 2),
            (PlanType.basic, 'daily_ms', 0),
            (PlanType.basic, 'three_day_ms', 1),
            (PlanType.basic, 'weekly_ms', 2),
            (PlanType.plus, 'daily_ms', 0),
            (PlanType.plus, 'three_day_ms', 1),
            (PlanType.plus, 'weekly_ms', 2),
        ],
    )
    def test_blocks_only_above_the_active_plan_cap(self, plan, window, cap_index):
        cap = fair_use_mod.fair_use_caps_for_plan(plan)[cap_index]
        state = {'stage': 'restrict', 'restrict_until': datetime.now(timezone.utc) + timedelta(days=1)}
        subscription = SimpleNamespace(plan=plan)
        with patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True), patch.object(
            fair_use_mod, 'FAIR_USE_KILL_SWITCH', False
        ), patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set()), patch.object(
            fair_use_mod, 'fair_use_db'
        ) as fair_use_db, patch.object(
            fair_use_mod, 'get_rolling_speech_ms'
        ) as get_speech, patch.object(
            fair_use_mod.users_db, 'get_existing_user_subscription', return_value=subscription
        ):
            fair_use_db.get_fair_use_state.return_value = state
            get_speech.return_value = _totals(**{window: cap})
            assert fair_use_mod.get_hard_restriction_status('u') == (False, None)

            get_speech.return_value = _totals(**{window: cap + 1})
            restricted, retry_after = fair_use_mod.get_hard_restriction_status('u')
            assert restricted is True
            assert retry_after is not None
