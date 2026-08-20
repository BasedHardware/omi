"""Chat overage reporting must consume the catalog allocation and policy."""

from config.plan_catalog import plan_uses_overage
from models.users import PlanType
from utils import overage


def test_overage_policy_matrix_uses_one_catalog_predicate():
    assert {
        plan.value: plan_uses_overage(plan)
        for plan in PlanType
    } == {
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
