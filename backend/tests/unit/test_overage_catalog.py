"""Chat overage reporting must consume the catalog allocation and policy."""

from config.plan_catalog import plan_uses_overage
from models.users import PlanType
from utils import overage


def test_overage_policy_matrix_uses_one_catalog_predicate():
    assert {plan.value: plan_uses_overage(plan) for plan in PlanType} == {
        'basic': False,
        'unlimited': True,
        'architect': True,
        'operator': True,
        'plus': False,
        'unlimited_v2': False,
    }
    assert not hasattr(overage, 'is_overage_plan')


def test_reporting_preserves_catalog_units_and_hard_caps(monkeypatch):
    usage = {
        'questions': 501,
        'cost_usd': 450.0,
        'reset_at': 123,
    }
    monkeypatch.setattr(overage.user_usage_db, 'get_monthly_chat_usage', lambda uid: usage)

    operator = overage.get_user_overage('uid', PlanType.operator)
    assert operator['included_questions'] == 500
    assert operator['included_cost_usd'] is None
    assert operator['excess_questions'] == 1
    assert operator['overage_usd'] > 0

    architect = overage.get_user_overage('uid', PlanType.architect)
    assert architect['included_questions'] is None
    assert architect['included_cost_usd'] == 400.0
    assert architect['excess_questions'] == 0
    assert architect['overage_usd'] > 0

    plus = overage.get_user_overage('uid', PlanType.plus)
    assert plus['included_questions'] == 200
    assert plus['overage_usd'] == 0.0


def test_reporting_and_admission_share_a_legacy_chat_overlay(monkeypatch):
    monkeypatch.setenv('OPERATOR_CHAT_QUESTIONS_PER_MONTH', '750')
    usage = {'questions': 751, 'cost_usd': 1.0, 'reset_at': 123}
    monkeypatch.setattr(overage.user_usage_db, 'get_monthly_chat_usage', lambda uid: usage)

    snapshot = overage.get_user_overage('uid', PlanType.operator)
    assert snapshot['included_questions'] == 750


class TestChatLimitZeroSemantics:
    """Pin the post-ruling meaning of a chat limit of exactly zero.

    Before the catalog, ``get_chat_quota_snapshot`` guarded on ``limit_value > 0``,
    so a computed limit of 0 left ``allowed = True`` -- i.e. 0 meant *unlimited*.
    David's ruling retired that convention: 0 means zero. The guard is gone, so 0
    now denies. That is intended, but it is a silent inversion at the env-overlay
    seam (FREE/NEO/OPERATOR_CHAT_QUESTIONS_PER_MONTH,
    ARCHITECT_CHAT_COST_USD_PER_MONTH), where an operator setting 0 under the old
    convention meant "unlimited" and now means "deny everything".

    These call the real ``get_chat_quota_snapshot`` rather than restating its
    arithmetic: a test that copies the logic it guards would not have caught the
    change it exists to pin.
    """

    def _snapshot(self, monkeypatch, chat_questions_limit, used_questions):
        from models.users import PlanType, Subscription
        from utils import subscription as sub_mod

        limits = sub_mod.get_plan_limits(PlanType.basic).model_copy(
            update={'chat_questions_per_month': chat_questions_limit, 'chat_cost_usd_per_month': None}
        )

        monkeypatch.setattr(
            sub_mod.users_db, 'get_user_valid_subscription', lambda *a, **k: Subscription(plan=PlanType.basic)
        )
        monkeypatch.setattr(sub_mod, 'get_plan_limits', lambda *a, **k: limits)
        monkeypatch.setattr(sub_mod, 'is_trial_paywalled', lambda *a, **k: False)
        monkeypatch.setattr(
            sub_mod.user_usage_db,
            'get_monthly_chat_usage',
            lambda *a, **k: {'questions': used_questions, 'cost_usd': 0.0, 'reset_at': 0},
        )
        return sub_mod.get_chat_quota_snapshot('uid-zero-semantics', provision=False)

    def test_zero_chat_limit_denies_rather_than_meaning_unlimited(self, monkeypatch):
        snap = self._snapshot(monkeypatch, 0, 0.0)
        assert snap['limit'] == 0
        assert snap['allowed'] is False, "a finite chat limit of 0 must deny, not mean unlimited"

    def test_none_chat_limit_still_means_unlimited(self, monkeypatch):
        snap = self._snapshot(monkeypatch, None, 10_000.0)
        assert snap['limit'] is None
        assert snap['allowed'] is True, "None remains the typed representation of unlimited"
