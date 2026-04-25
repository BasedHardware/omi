"""Tests for subscription restructure: Basic + Operator ($49) + Architect ($400),
deprecate Unlimited for existing users. Issue #6734."""

import sys
import types

# Mock external dependencies before importing app code
_announcements_mod = types.ModuleType("database.announcements")


def _compare_versions(a, b):
    """Semantic version comparison matching the real _compare_versions."""
    a_parts = [int(x) for x in a.split('.')]
    b_parts = [int(x) for x in b.split('.')]
    for x, y in zip(a_parts, b_parts):
        if x != y:
            return 1 if x > y else -1
    return len(a_parts) - len(b_parts)


_announcements_mod._compare_versions = _compare_versions
sys.modules.setdefault("database.users", types.SimpleNamespace())
sys.modules.setdefault("database.user_usage", types.SimpleNamespace())
sys.modules.setdefault("database.announcements", _announcements_mod)

from models.users import PlanType, PlanLimits, Subscription


def test_operator_chat_cap_independent_from_unlimited(monkeypatch):
    """F4: Operator and Unlimited chat caps must be independently configurable."""
    monkeypatch.setenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", "750")
    monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "3000")

    # Re-import to pick up env vars
    import importlib
    import utils.subscription as sub_mod

    importlib.reload(sub_mod)

    operator_limits = sub_mod.get_plan_limits(PlanType.operator)
    unlimited_limits = sub_mod.get_plan_limits(PlanType.unlimited)

    assert operator_limits.chat_questions_per_month == 750
    assert unlimited_limits.chat_questions_per_month == 3000
    assert operator_limits.chat_questions_per_month != unlimited_limits.chat_questions_per_month


def test_operator_and_neo_defaults(monkeypatch):
    """Operator defaults to 500, Neo defaults to 200."""
    monkeypatch.delenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", raising=False)
    monkeypatch.delenv("NEO_CHAT_QUESTIONS_PER_MONTH", raising=False)

    import importlib
    import utils.subscription as sub_mod

    importlib.reload(sub_mod)

    operator_limits = sub_mod.get_plan_limits(PlanType.operator)
    unlimited_limits = sub_mod.get_plan_limits(PlanType.unlimited)

    assert operator_limits.chat_questions_per_month == 500
    assert unlimited_limits.chat_questions_per_month == 200


def test_architect_uses_dollar_cap():
    """Architect plan uses dollar cap, not question count."""
    from utils.subscription import get_plan_limits

    limits = get_plan_limits(PlanType.architect)
    assert limits.chat_cost_usd_per_month is not None
    assert limits.chat_questions_per_month is None
    assert limits.transcription_seconds is None  # unlimited transcription


def test_operator_is_paid():
    from utils.subscription import is_paid_plan

    assert is_paid_plan(PlanType.operator)
    assert is_paid_plan(PlanType.architect)
    assert is_paid_plan(PlanType.unlimited)
    assert not is_paid_plan(PlanType.basic)


def test_filter_plans_for_basic_user():
    """Basic users see Neo, Operator, and Architect in purchase catalog."""
    from utils.subscription import get_paid_plan_definitions, filter_plans_for_user

    definitions = get_paid_plan_definitions()
    filtered = filter_plans_for_user(definitions, PlanType.basic)

    plan_ids = [d['plan_id'] for d in filtered]
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_filter_plans_keeps_legacy_for_current_subscriber():
    """Unlimited subscribers see their plan in catalog for active-plan detection."""
    from utils.subscription import get_paid_plan_definitions, filter_plans_for_user

    definitions = get_paid_plan_definitions()
    filtered = filter_plans_for_user(definitions, PlanType.unlimited)

    plan_ids = [d['plan_id'] for d in filtered]
    assert 'unlimited' in plan_ids
    assert 'operator' in plan_ids
    assert 'architect' in plan_ids


def test_legacy_client_adaptation():
    """Old clients see Unlimited Plan (not legacy suffix) and no Operator."""
    from utils.subscription import get_paid_plan_definitions, adapt_plans_for_legacy_client

    definitions = get_paid_plan_definitions()
    adapted = adapt_plans_for_legacy_client(definitions)

    plan_ids = [d['plan_id'] for d in adapted]
    assert 'operator' not in plan_ids
    assert 'unlimited' in plan_ids
    assert 'architect' in plan_ids

    unlimited_def = next(d for d in adapted if d['plan_id'] == 'unlimited')
    assert unlimited_def['title'] == 'Unlimited Plan'
    assert unlimited_def['legacy'] is False  # old clients don't know about legacy flag

    architect_def = next(d for d in adapted if d['plan_id'] == 'architect')
    assert architect_def['title'] == 'Omi Pro'


def test_version_gating_macos_always_new():
    """macOS always gets new plans (no version header = True)."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans('macos', None) is True
    assert should_show_new_plans('macos', '99.99.999') is True


def test_version_gating_mobile_requires_version():
    """Mobile requires version header and must meet minimum."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans('android', None) is False
    assert should_show_new_plans('ios', None) is False

    assert should_show_new_plans('android', '99.99.999') is True
    assert should_show_new_plans('ios', '99.99.999') is True


def test_version_gating_old_mobile_gets_legacy():
    """Old mobile builds get legacy catalog."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans('android', '0.0.1') is False
    assert should_show_new_plans('ios', '0.0.1') is False


def test_version_gating_exact_threshold():
    """Exact threshold version gets new plans."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans('android', '1.0.530') is True
    assert should_show_new_plans('ios', '1.0.530') is True
    assert should_show_new_plans('macos', '0.11.324') is True


def test_version_gating_just_below_threshold():
    """One version below threshold gets legacy."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans('android', '1.0.529') is False
    assert should_show_new_plans('ios', '1.0.529') is False
    assert should_show_new_plans('macos', '0.11.323') is False


def test_version_gating_malformed_version():
    """Malformed version: macOS fail-open, mobile fail-closed."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans('macos', 'not.a.version') is True
    assert should_show_new_plans('android', 'not.a.version') is False
    assert should_show_new_plans('ios', 'not.a.version') is False


def test_version_gating_unknown_platform():
    """Unknown platform gets legacy catalog."""
    from utils.subscription import should_show_new_plans

    assert should_show_new_plans(None, None) is False
    assert should_show_new_plans('windows', '1.0.0') is False


def test_subscription_deprecation_fields():
    """Subscription model supports deprecated + deprecation_message."""
    sub = Subscription(plan=PlanType.unlimited, deprecated=True, deprecation_message="Your plan is retiring.")

    assert sub.deprecated is True
    assert sub.deprecation_message == "Your plan is retiring."

    # Non-deprecated plan
    sub2 = Subscription(plan=PlanType.operator)
    assert sub2.deprecated is False
    assert sub2.deprecation_message is None


def test_operator_price_id_mapping(monkeypatch):
    """Operator price IDs resolve to operator plan type."""
    monkeypatch.setenv("STRIPE_OPERATOR_MONTHLY_PRICE_ID", "price_op_monthly")
    monkeypatch.setenv("STRIPE_OPERATOR_ANNUAL_PRICE_ID", "price_op_annual")

    import importlib
    import utils.subscription as sub_mod

    importlib.reload(sub_mod)

    assert sub_mod.get_plan_type_from_price_id("price_op_monthly") == PlanType.operator
    assert sub_mod.get_plan_type_from_price_id("price_op_annual") == PlanType.operator


def test_plan_features_differentiate_operator_neo(monkeypatch):
    """Operator and Neo show separate feature lists with their own caps."""
    monkeypatch.setenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", "600")
    monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "300")

    import importlib
    import utils.subscription as sub_mod

    importlib.reload(sub_mod)

    op_features = sub_mod.get_plan_features(PlanType.operator)
    neo_features = sub_mod.get_plan_features(PlanType.unlimited)

    assert "600 chat questions per month" in op_features
    assert "300 chat questions per month" in neo_features


def test_plan_display_names():
    from utils.subscription import get_plan_display_name

    assert get_plan_display_name(PlanType.basic) == 'Free'
    assert get_plan_display_name(PlanType.operator) == 'Operator'
    assert get_plan_display_name(PlanType.architect) == 'Architect'
    assert get_plan_display_name(PlanType.unlimited) == 'Neo'
