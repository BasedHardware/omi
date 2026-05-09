"""Tests for ``database.plan_caps_config`` — the Firestore-backed plan caps layer.

The module under test reads per-plan caps from ``app_config/plan_caps`` in
Firestore and falls back to env-var defaults when the doc is missing/incomplete.
This file pins the fallback behavior so callers (``utils.subscription.get_plan_limits``)
keep their pre-refactor semantics for every existing plan.
"""

import sys
import types
from unittest.mock import patch, MagicMock

import pytest

# Stub heavy deps before importing the production module.
sys.modules.setdefault("database._client", types.SimpleNamespace(db=MagicMock()))
sys.modules.setdefault("database.cache", types.SimpleNamespace(get_memory_cache=MagicMock()))

from models.users import PlanType, PlanLimits


def _reload_config_module():
    import importlib
    import database.plan_caps_config as mod

    importlib.reload(mod)
    return mod


# ── Fallback defaults (no Firestore doc) ────────────────────────────────────


class TestPlanCapsDefaults:
    """When the Firestore doc is missing/empty, env-var fallbacks apply.

    These match the pre-refactor ``get_plan_limits`` behavior exactly so the
    refactor in ``utils.subscription`` is a no-op for existing plans.
    """

    def test_basic_defaults(self, monkeypatch):
        monkeypatch.setenv("FREE_CHAT_QUESTIONS_PER_MONTH", "30")
        monkeypatch.setenv("BASIC_TIER_MINUTES_LIMIT_PER_MONTH", "1200")
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.basic)
        assert caps["chat_questions_per_month"] == 30
        assert caps["chat_cost_usd_per_month"] is None
        assert caps["transcription_seconds"] == 1200 * 60

    def test_unlimited_defaults(self, monkeypatch):
        monkeypatch.setenv("NEO_CHAT_QUESTIONS_PER_MONTH", "200")
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.unlimited)
        assert caps["chat_questions_per_month"] == 200
        assert caps["transcription_seconds"] is None
        assert caps["chat_cost_usd_per_month"] is None

    def test_operator_defaults(self, monkeypatch):
        monkeypatch.setenv("OPERATOR_CHAT_QUESTIONS_PER_MONTH", "500")
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.operator)
        assert caps["chat_questions_per_month"] == 500
        assert caps["transcription_seconds"] is None

    def test_architect_defaults(self, monkeypatch):
        monkeypatch.setenv("ARCHITECT_CHAT_COST_USD_PER_MONTH", "400.0")
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            caps = mod.get_plan_caps(PlanType.architect)
        assert caps["chat_questions_per_month"] is None
        assert caps["chat_cost_usd_per_month"] == 400.0
        assert caps["transcription_seconds"] is None


# ── Firestore overrides ─────────────────────────────────────────────────────


class TestPlanCapsFirestoreOverride:
    """Firestore overrides take precedence over env defaults."""

    def test_override_chat_questions(self):
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={"plans": {"unlimited": {"chat_questions_per_month": 300}}},
        ):
            caps = mod.get_plan_caps(PlanType.unlimited)
        assert caps["chat_questions_per_month"] == 300

    def test_override_with_null_clears_cap(self):
        """Setting a cap to null in Firestore makes it unlimited."""
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={"plans": {"basic": {"chat_questions_per_month": None}}},
        ):
            caps = mod.get_plan_caps(PlanType.basic)
        assert caps["chat_questions_per_month"] is None

    def test_override_unknown_key_ignored(self):
        """Typos in Firestore must not silently change behavior."""
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={"plans": {"unlimited": {"chat_xxxxx": 999}}},
        ):
            caps = mod.get_plan_caps(PlanType.unlimited)
        assert "chat_xxxxx" not in caps

    def test_partial_override_keeps_other_defaults(self, monkeypatch):
        """Override only one field → others keep env defaults."""
        monkeypatch.setenv("BASIC_TIER_MINUTES_LIMIT_PER_MONTH", "1200")
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={"plans": {"basic": {"chat_questions_per_month": 25}}},
        ):
            caps = mod.get_plan_caps(PlanType.basic)
        assert caps["chat_questions_per_month"] == 25
        assert caps["transcription_seconds"] == 1200 * 60


# ── Platform overrides (forward-compat for desktop extras) ──────────────────


class TestPlatformOverrides:
    def test_no_platform_returns_base(self):
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={
                "plans": {"unlimited": {"chat_questions_per_month": 200}},
                "platform_overrides": {"desktop": {"unlimited": {"chat_questions_per_month": 999}}},
            },
        ):
            caps = mod.get_plan_caps(PlanType.unlimited)
        assert caps["chat_questions_per_month"] == 200

    def test_desktop_override_applied(self):
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={
                "plans": {"unlimited": {"chat_questions_per_month": 200}},
                "platform_overrides": {"desktop": {"unlimited": {"chat_questions_per_month": 999}}},
            },
        ):
            caps = mod.get_plan_caps(PlanType.unlimited, platform="desktop")
        assert caps["chat_questions_per_month"] == 999

    def test_platform_with_no_override_for_plan(self):
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={
                "plans": {"unlimited": {"chat_questions_per_month": 200}},
                "platform_overrides": {"desktop": {}},
            },
        ):
            caps = mod.get_plan_caps(PlanType.unlimited, platform="desktop")
        assert caps["chat_questions_per_month"] == 200


# ── PlanLimits adapter ──────────────────────────────────────────────────────


class TestGetPlanLimitsFromConfig:
    """Adapter that returns a ``PlanLimits`` pydantic model."""

    def test_returns_planlimits(self):
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={"plans": {"unlimited": {"chat_questions_per_month": 200, "transcription_seconds": None}}},
        ):
            limits = mod.get_plan_limits_from_config(PlanType.unlimited)
        assert isinstance(limits, PlanLimits)
        assert limits.chat_questions_per_month == 200
        assert limits.transcription_seconds is None
        assert limits.chat_cost_usd_per_month is None

    def test_architect_cost_cap_propagates(self, monkeypatch):
        monkeypatch.setenv("ARCHITECT_CHAT_COST_USD_PER_MONTH", "400.0")
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            limits = mod.get_plan_limits_from_config(PlanType.architect)
        assert limits.chat_cost_usd_per_month == 400.0
        assert limits.chat_questions_per_month is None


# ── Superwall product map (read by webhook handler in Phase 2) ──────────────


class TestSuperwallProductMap:
    def test_returns_map(self):
        mod = _reload_config_module()
        with patch.object(
            mod,
            "_get_config",
            return_value={"superwall_product_map": {"com.omi.app.lite_monthly": "lite"}},
        ):
            assert mod.get_superwall_product_map() == {"com.omi.app.lite_monthly": "lite"}

    def test_empty_when_missing(self):
        mod = _reload_config_module()
        with patch.object(mod, "_get_config", return_value={}):
            assert mod.get_superwall_product_map() == {}
