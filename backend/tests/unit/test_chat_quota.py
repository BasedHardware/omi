"""Tests for chat quota enforcement and snapshot logic."""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

# ── Stub out heavy dependencies before importing production code ────────────
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

# Create stubs for database modules used by get_chat_quota_snapshot
_db_users_mod = types.SimpleNamespace(get_user_valid_subscription=MagicMock())
_db_user_usage_mod = types.SimpleNamespace(get_monthly_chat_usage=MagicMock())

sys.modules.setdefault("database._client", types.SimpleNamespace(db=MagicMock()))
sys.modules["database.users"] = _db_users_mod
sys.modules["database.user_usage"] = _db_user_usage_mod
sys.modules.setdefault("database.announcements", _announcements_mod)

from models.users import PlanType, PlanLimits, Subscription

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_subscription(plan: PlanType) -> Subscription:
    """Build a minimal Subscription object for the given plan type."""
    return Subscription(
        plan=plan,
        status="active",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _reload_subscription_module():
    """Reload utils.subscription to pick up env var changes."""
    import importlib
    import utils.subscription as sub_mod

    importlib.reload(sub_mod)
    return sub_mod


_RESET_AT = 1735689600  # Fixed timestamp for tests


# ── get_chat_quota_snapshot ─────────────────────────────────────────────────


class TestGetChatQuotaSnapshot:
    """Tests for get_chat_quota_snapshot()."""

    def test_neo_below_cap(self, monkeypatch):
        """Neo user with 100 questions used out of 2000 → allowed=True."""
        monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "2000")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.unlimited))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 100,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")

        assert snapshot['allowed'] is True
        assert snapshot['unit'] == 'questions'
        assert snapshot['used'] == 100.0
        assert snapshot['limit'] == 2000.0

    def test_neo_at_cap(self, monkeypatch):
        """Neo user with 2000 questions used (equal to cap) → allowed=False."""
        monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "2000")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.unlimited))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 2000,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is False

    def test_neo_above_cap(self, monkeypatch):
        """Neo user with 2001 questions used → allowed=False."""
        monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "2000")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.unlimited))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 2001,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is False

    def test_architect_cost_based_below(self, monkeypatch):
        """Architect tier uses cost_usd; $200 used of $400 → allowed=True."""
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.architect))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 500,
                'cost_usd': 200.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")

        assert snapshot['allowed'] is True
        assert snapshot['unit'] == 'cost_usd'
        assert snapshot['used'] == 200.0

    def test_architect_cost_based_exceeded(self, monkeypatch):
        """Architect tier with $400+ used → allowed=False."""
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.architect))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 1000,
                'cost_usd': 400.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is False

    def test_architect_cost_based_above(self, monkeypatch):
        """Architect tier with $450 used (above $400 cap) → allowed=False."""
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.architect))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 1000,
                'cost_usd': 450.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is False
        assert snapshot['used'] == 450.0
        assert snapshot['limit'] == 400.0

    def test_basic_plan_has_limit(self, monkeypatch):
        """Basic (free) plan has 30 questions/month by default."""
        monkeypatch.setenv("FREE_CHAT_QUESTIONS_PER_MONTH", "30")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=None)
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 10,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")

        assert snapshot['allowed'] is True
        assert snapshot['limit'] == 30.0

    def test_basic_plan_exceeded(self, monkeypatch):
        """Basic (free) plan exceeded at 30 questions → allowed=False."""
        monkeypatch.setenv("FREE_CHAT_QUESTIONS_PER_MONTH", "30")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=None)
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 30,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is False

    def test_operator_boundary(self, monkeypatch):
        """Operator at 499/500 questions → allowed=True; at 500 → False."""
        monkeypatch.setenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", "500")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.operator))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 499,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is True

        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 500,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is False

    def test_over_cap_percent_clamps_at_100(self, monkeypatch):
        """When used > limit, percent should clamp at 100.0 (not exceed it)."""
        monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "200")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.unlimited))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 500,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        # Percent clamping is done at the endpoint level, not in the snapshot.
        # Verify the snapshot returns raw values for the endpoint to clamp.
        assert snapshot['used'] == 500.0
        assert snapshot['limit'] == 200.0
        assert snapshot['allowed'] is False

    def test_reset_at_propagated(self, monkeypatch):
        """reset_at from usage data flows through the snapshot."""
        monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "200")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=_make_subscription(PlanType.unlimited))
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 50,
                'cost_usd': 0.0,
                'reset_at': 1746057600,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['reset_at'] == 1746057600

    def test_no_subscription_falls_back_to_basic(self, monkeypatch):
        """When user has no subscription, falls back to basic plan limits."""
        monkeypatch.setenv("FREE_CHAT_QUESTIONS_PER_MONTH", "30")
        sub_mod = _reload_subscription_module()

        _db_users_mod.get_user_valid_subscription = MagicMock(return_value=None)
        _db_user_usage_mod.get_monthly_chat_usage = MagicMock(
            return_value={
                'questions': 25,
                'cost_usd': 0.0,
                'reset_at': _RESET_AT,
            }
        )

        snapshot = sub_mod.get_chat_quota_snapshot("uid123")
        assert snapshot['allowed'] is True
        assert snapshot['limit'] == 30.0
        assert snapshot['unit'] == 'questions'


# ── enforce_chat_quota ──────────────────────────────────────────────────────


class TestEnforceChatQuota:
    """Tests for enforce_chat_quota()."""

    def test_enforcement_allowed(self, monkeypatch):
        """When user is within quota, no exception."""
        sub_mod = _reload_subscription_module()

        with patch.object(
            sub_mod,
            "get_chat_quota_snapshot",
            return_value={
                'allowed': True,
                'plan': PlanType.unlimited,
                'unit': 'questions',
                'used': 100,
                'limit': 2000,
                'reset_at': _RESET_AT,
            },
        ):
            sub_mod.enforce_chat_quota("uid123")  # no exception

    def test_enforcement_exceeded_raises_402(self, monkeypatch):
        """When user exceeds quota, raises HTTPException 402."""
        from fastapi import HTTPException

        sub_mod = _reload_subscription_module()

        with patch.object(
            sub_mod,
            "get_chat_quota_snapshot",
            return_value={
                'allowed': False,
                'plan': PlanType.unlimited,
                'unit': 'questions',
                'used': 2001,
                'limit': 2000,
                'reset_at': _RESET_AT,
            },
        ):
            with pytest.raises(HTTPException) as exc_info:
                sub_mod.enforce_chat_quota("uid123")

            assert exc_info.value.status_code == 402
            assert exc_info.value.detail['error'] == 'quota_exceeded'
            assert exc_info.value.detail['plan'] == 'Neo'
            assert exc_info.value.detail['plan_type'] == 'unlimited'
            assert exc_info.value.detail['unit'] == 'questions'
            assert exc_info.value.detail['used'] == 2001
            assert exc_info.value.detail['limit'] == 2000
            assert exc_info.value.detail['reset_at'] == _RESET_AT

    def test_enforcement_402_operator_plan(self, monkeypatch):
        """Operator plan shows correct display name in 402 detail."""
        from fastapi import HTTPException

        sub_mod = _reload_subscription_module()

        with patch.object(
            sub_mod,
            "get_chat_quota_snapshot",
            return_value={
                'allowed': False,
                'plan': PlanType.operator,
                'unit': 'questions',
                'used': 501,
                'limit': 500,
                'reset_at': _RESET_AT,
            },
        ):
            with pytest.raises(HTTPException) as exc_info:
                sub_mod.enforce_chat_quota("uid123")

            assert exc_info.value.status_code == 402
            assert exc_info.value.detail['plan'] == 'Operator'

    def test_enforcement_402_architect_cost_based(self, monkeypatch):
        """Architect plan shows cost_usd unit in 402 detail."""
        from fastapi import HTTPException

        sub_mod = _reload_subscription_module()

        with patch.object(
            sub_mod,
            "get_chat_quota_snapshot",
            return_value={
                'allowed': False,
                'plan': PlanType.architect,
                'unit': 'cost_usd',
                'used': 400.50,
                'limit': 400,
                'reset_at': _RESET_AT,
            },
        ):
            with pytest.raises(HTTPException) as exc_info:
                sub_mod.enforce_chat_quota("uid123")

            assert exc_info.value.status_code == 402
            assert exc_info.value.detail['unit'] == 'cost_usd'
            assert exc_info.value.detail['used'] == 400.5
