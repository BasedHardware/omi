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


class TestLegacyZeroOverlayKeepsUnlimited:
    """Production sets the Basic words/insights overlays to literal ``0``.

    Those variables were authored when ``0`` meant *unlimited*. The catalog retires
    that sentinel, but retiring it must not reinterpret configuration that is
    already deployed: reading prod's zeros as a finite zero would hand every Free
    user a zero allowance and advertise "0 words transcribed per month".

    This pins the bridge against the values actually set on the production Cloud Run
    service and the prod Helm charts, verified 2026-08-20.
    """

    PROD_OVERLAY = {
        'BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH': '0',
        'BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH': '0',
    }

    def _reloaded(self, monkeypatch):
        import importlib

        from utils import subscription as sub_mod

        for key, value in self.PROD_OVERLAY.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(sub_mod)

    def test_prod_zero_overlays_still_mean_unlimited(self, monkeypatch):
        from models.users import PlanType

        sub_mod = self._reloaded(monkeypatch)
        try:
            limits = sub_mod.get_plan_limits(PlanType.basic)
            assert limits.words_transcribed is None, 'a legacy zero overlay must stay unlimited'
            assert limits.insights_gained is None, 'a legacy zero overlay must stay unlimited'
        finally:
            import importlib

            monkeypatch.undo()
            importlib.reload(sub_mod)

    def test_nonzero_overlay_is_still_honored_as_finite(self, monkeypatch):
        import importlib

        from models.users import PlanType
        from utils import subscription as sub_mod

        monkeypatch.setenv('BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH', '5000')
        sub_mod = importlib.reload(sub_mod)
        try:
            assert sub_mod.get_plan_limits(PlanType.basic).words_transcribed == 5000
        finally:
            monkeypatch.undo()
            importlib.reload(sub_mod)
