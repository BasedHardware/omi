"""Tests for chat-cap enforcement and plan version-gating logic.

Filed alongside #6751 (zero existing coverage). Covers:

- ``enforce_chat_quota``    — kill-switch, under-cap, over-cap, missing usage doc.
- ``should_show_new_plans`` — non-macOS, missing version, valid below/above
                              threshold, malformed version (documented fail-open).
- ``adapt_plans_for_legacy_client`` — Operator hidden, Architect rename,
                                      Unlimited legacy flag stripped.

Heavy infrastructure (Firestore, Firebase admin, Stripe SDK, redis) is stubbed
before importing the module under test, mirroring the pattern already used by
``test_available_plans_resilience.py``.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# --- env vars needed at import time --------------------------------------
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# --- Stub heavy modules before subscription import -----------------------

_mock_db_client = types.ModuleType("database._client")
_mock_db_client.db = MagicMock()
sys.modules["database._client"] = _mock_db_client

_fb_admin = types.ModuleType("firebase_admin")
_fb_admin.auth = MagicMock()
sys.modules["firebase_admin"] = _fb_admin
sys.modules["firebase_admin.auth"] = _fb_admin.auth

_db_pkg = types.ModuleType("database")
sys.modules.setdefault("database", _db_pkg)
for _name in (
    "database.users",
    "database.user_usage",
    "database.redis_db",
    "database.cache",
    "database.announcements",
):
    _m = types.ModuleType(_name)
    sys.modules[_name] = _m
    setattr(_db_pkg, _name.split(".")[-1], _m)


# database.announcements.compare_versions is needed at subscription import time.
def _compare_versions(v1: str, v2: str) -> int:
    a = tuple(int(p) for p in v1.split("+", 1)[0].split("."))
    b = tuple(int(p) for p in v2.split("+", 1)[0].split("."))
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


sys.modules["database.announcements"].compare_versions = _compare_versions
sys.modules["database.announcements"]._compare_versions = _compare_versions  # backward-compat name

# stripe is imported at module top of utils/subscription.py
_stripe = types.ModuleType("stripe")
_stripe.api_key = None
_stripe.Price = MagicMock()
sys.modules["stripe"] = _stripe

# log_sanitizer.sanitize is used by subscription
_log_san = types.ModuleType("utils.log_sanitizer")
_log_san.sanitize = lambda s: s
sys.modules["utils.log_sanitizer"] = _log_san

# Now safe to import the module under test
from utils import subscription  # noqa: E402
from models.users import PlanType  # noqa: E402


# =======================================================================
#                       enforce_chat_quota
# =======================================================================


class TestEnforceChatQuotaKillSwitch:
    """When the kill-switch is off, enforce is a strict no-op."""

    def test_killswitch_off_never_raises(self, monkeypatch):
        monkeypatch.setattr(subscription, "CHAT_CAP_ENFORCEMENT_ENABLED", False)
        with patch.object(subscription, "get_chat_quota_snapshot") as snap:
            snap.return_value = {
                "plan": PlanType.basic,
                "unit": "questions",
                "used": 9_999.0,
                "limit": 30.0,
                "allowed": False,
                "reset_at": "2026-05-01T00:00:00Z",
            }
            subscription.enforce_chat_quota("uid-x")
            snap.assert_not_called()  # short-circuits before snapshot read


class TestEnforceChatQuotaQuestionUnit:
    """Free / legacy-Unlimited / Operator: question-count gating."""

    def _snap(self, used: float, limit: float, plan: PlanType = PlanType.basic) -> dict:
        return {
            "plan": plan,
            "unit": "questions",
            "used": used,
            "limit": limit,
            "allowed": used < limit,
            "reset_at": "2026-05-01T00:00:00Z",
        }

    def test_under_limit_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(subscription, "CHAT_CAP_ENFORCEMENT_ENABLED", True)
        with patch.object(subscription, "get_chat_quota_snapshot", return_value=self._snap(29.0, 30.0)):
            subscription.enforce_chat_quota("uid-x")  # no exception

    def test_at_limit_raises_402(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(subscription, "CHAT_CAP_ENFORCEMENT_ENABLED", True)
        with patch.object(subscription, "get_chat_quota_snapshot", return_value=self._snap(30.0, 30.0)):
            with pytest.raises(HTTPException) as exc:
                subscription.enforce_chat_quota("uid-x")
            assert exc.value.status_code == 402
            detail = exc.value.detail
            assert detail["error"] == "quota_exceeded"
            assert detail["unit"] == "questions"
            assert detail["used"] == 30.0
            assert detail["limit"] == 30.0
            assert detail["plan_type"] == "basic"
            assert "reset_at" in detail

    def test_over_limit_includes_actual_used(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(subscription, "CHAT_CAP_ENFORCEMENT_ENABLED", True)
        with patch.object(subscription, "get_chat_quota_snapshot", return_value=self._snap(34.0, 30.0)):
            with pytest.raises(HTTPException) as exc:
                subscription.enforce_chat_quota("uid-x")
            assert exc.value.detail["used"] == 34.0


class TestEnforceChatQuotaCostUnit:
    """Pro/Architect: dollar-cost gating."""

    def test_under_cost_cap_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(subscription, "CHAT_CAP_ENFORCEMENT_ENABLED", True)
        snap = {
            "plan": PlanType.pro,
            "unit": "cost_usd",
            "used": 399.5,
            "limit": 400.0,
            "allowed": True,
            "reset_at": "2026-05-01T00:00:00Z",
        }
        with patch.object(subscription, "get_chat_quota_snapshot", return_value=snap):
            subscription.enforce_chat_quota("uid-pro")

    def test_over_cost_cap_raises_with_cost_unit(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(subscription, "CHAT_CAP_ENFORCEMENT_ENABLED", True)
        snap = {
            "plan": PlanType.pro,
            "unit": "cost_usd",
            "used": 400.123456,
            "limit": 400.0,
            "allowed": False,
            "reset_at": "2026-05-01T00:00:00Z",
        }
        with patch.object(subscription, "get_chat_quota_snapshot", return_value=snap):
            with pytest.raises(HTTPException) as exc:
                subscription.enforce_chat_quota("uid-pro")
            assert exc.value.status_code == 402
            assert exc.value.detail["unit"] == "cost_usd"
            # 4-decimal rounding contract for the response body
            assert exc.value.detail["used"] == 400.1235
            assert exc.value.detail["plan_type"] == "pro"


# =======================================================================
#                       should_show_new_plans
# =======================================================================


class TestShouldShowNewPlansPlatform:
    """Non-macOS clients always see the legacy catalog."""

    @pytest.mark.parametrize("platform", ["ios", "iOS", "android", "Android", None, "", "windows"])
    def test_non_macos_returns_false(self, platform):
        assert subscription.should_show_new_plans(platform, "0.11.500") is False


class TestShouldShowNewPlansVersion:
    """Version-gating semantics on macOS."""

    def test_missing_version_falls_open(self, monkeypatch):
        # Documented intent: APIClient.swift doesn't currently send X-App-Version
        # so requiring it would fail-closed for every real desktop user.
        monkeypatch.setattr(subscription, "NEW_PLANS_MIN_DESKTOP_VERSION", "0.11.324")
        assert subscription.should_show_new_plans("macos", None) is True
        assert subscription.should_show_new_plans("macos", "") is True

    def test_above_or_equal_threshold_returns_true(self, monkeypatch):
        monkeypatch.setattr(subscription, "NEW_PLANS_MIN_DESKTOP_VERSION", "0.11.324")
        assert subscription.should_show_new_plans("macos", "0.11.324") is True
        assert subscription.should_show_new_plans("macos", "0.11.325") is True
        assert subscription.should_show_new_plans("macos", "0.12.0") is True

    def test_below_threshold_returns_false(self, monkeypatch):
        monkeypatch.setattr(subscription, "NEW_PLANS_MIN_DESKTOP_VERSION", "0.11.324")
        assert subscription.should_show_new_plans("macos", "0.11.323") is False
        assert subscription.should_show_new_plans("macos", "0.10.999") is False

    def test_malformed_version_falls_open_on_macos(self, monkeypatch):
        # Documented intent: malformed version is fail-open on macOS rather
        # than show the old catalog to a desktop client.
        monkeypatch.setattr(subscription, "NEW_PLANS_MIN_DESKTOP_VERSION", "0.11.324")
        assert subscription.should_show_new_plans("macos", "not-a-version") is True
        assert subscription.should_show_new_plans("macos", "abc.def.ghi") is True

    def test_case_insensitive_platform_match(self, monkeypatch):
        monkeypatch.setattr(subscription, "NEW_PLANS_MIN_DESKTOP_VERSION", "0.11.324")
        assert subscription.should_show_new_plans("MacOS", "0.11.500") is True
        assert subscription.should_show_new_plans("MACOS", "0.11.500") is True


# =======================================================================
#                       adapt_plans_for_legacy_client
# =======================================================================


class TestAdaptPlansForLegacyClient:
    """Pre-v0.11.324 clients get the old plan shape (no Operator,
    Architect renamed to Omi Pro, Unlimited's legacy flag stripped)."""

    def _new_catalog(self) -> list[dict]:
        return [
            {"plan_type": PlanType.operator, "plan_id": "operator", "title": "Operator", "legacy": False},
            {"plan_type": PlanType.pro, "plan_id": "pro", "title": "Architect", "legacy": False},
            {
                "plan_type": PlanType.unlimited,
                "plan_id": "unlimited",
                "title": "Unlimited (legacy)",
                "legacy": True,
            },
        ]

    def test_operator_is_dropped(self):
        out = subscription.adapt_plans_for_legacy_client(self._new_catalog())
        assert all(d["plan_id"] != "operator" for d in out)

    def test_architect_renamed_to_omi_pro(self):
        out = subscription.adapt_plans_for_legacy_client(self._new_catalog())
        pro = next(d for d in out if d["plan_id"] == "pro")
        assert pro["title"] == "Omi Pro"

    def test_unlimited_loses_legacy_suffix_and_flag(self):
        out = subscription.adapt_plans_for_legacy_client(self._new_catalog())
        unlim = next(d for d in out if d["plan_id"] == "unlimited")
        assert unlim["title"] == "Unlimited Plan"
        assert unlim["legacy"] is False

    def test_does_not_mutate_input(self):
        original = self._new_catalog()
        snapshot = [dict(d) for d in original]
        subscription.adapt_plans_for_legacy_client(original)
        assert original == snapshot
