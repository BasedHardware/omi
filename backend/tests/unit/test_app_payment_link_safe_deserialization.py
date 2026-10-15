"""Hermetic unit tests for safe App deserialization in upsert_app_payment_link.

Verifies that upsert_app_payment_link in utils.apps uses _safe_build_app / App.deserialize_safe
instead of bare App(**app_data), preventing unhandled ValidationError (HTTP 500)
crashes when an app document in Firestore lacks required schema fields.
"""

from __future__ import annotations

import ast
import inspect
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

# Module-level holder initialized inside encapsulated setup function
apps_utils = None


class _AutoMockModule(ModuleType):
    """Dynamic stub module providing mock attributes on access."""

    def __getattr__(self, name: str) -> Any:
        val = MagicMock()
        setattr(self, name, val)
        return val


def _setup_stubs_and_import():
    """Encapsulated stub setup satisfying Tier-2 AST isolation invariants."""
    global apps_utils
    if apps_utils is not None:
        return apps_utils

    import sys

    stubs = [
        "redis",
        "firebase_admin",
        "firebase_admin.auth",
        "pycountry",
        "stripe",
        "langchain_core",
        "langchain_core.messages",
        "langchain_core.callbacks",
        "utils.llm",
        "utils.llm.persona",
        "utils.llm.usage_tracker",
        "utils.llm.clients",
        "database.cache",
        "database.redis_db",
        "database.auth",
        "database.conversations",
        "database._client",
        "utils.memory.memory_service",
        "utils.other.storage",
        "utils.social",
    ]

    for mod_name in stubs:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = _AutoMockModule(mod_name)

    import utils.apps as _apps_mod

    apps_utils = _apps_mod
    return apps_utils


def setup_module():
    _setup_stubs_and_import()


@pytest.fixture(autouse=True, scope="module")
def _ensure_module_stubs():
    _setup_stubs_and_import()


def _valid_app_dict(app_id: str = "app_1") -> Dict[str, Any]:
    return {
        "id": app_id,
        "name": "Super AI Agent",
        "category": "productivity",
        "author": "Antigravity",
        "description": "An autonomous AI assistant",
        "image": "https://example.com/icon.png",
        "capabilities": ["chat"],
        "uid": "user_dev_1",
        "is_paid": True,
        "payment_plan": "monthly_recurring",
        "price": 9.99,
    }


class TestUpsertAppPaymentLinkSafeDeserialization:
    """Validate that upsert_app_payment_link gracefully handles malformed app records."""

    def test_upsert_payment_link_malformed_record_returns_none_without_crash(self, monkeypatch):
        """A stored app document missing required fields must return None and log warning, not raise ValidationError."""
        _setup_stubs_and_import()

        corrupt_app_data = {
            "id": "corrupt_app_123",
            # Missing name, author, description, category, image, capabilities
        }

        monkeypatch.setattr(apps_utils, "get_app_by_id_db", lambda _id: corrupt_app_data)
        warn_mock = MagicMock()
        monkeypatch.setattr(apps_utils.logger, "warning", warn_mock)

        # Must not raise ValidationError
        result = apps_utils.upsert_app_payment_link(
            app_id="corrupt_app_123",
            is_paid_app=True,
            price=15.0,
            payment_plan="monthly_recurring",
            uid="user_dev_1",
        )

        assert result is None
        # Verify a warning was logged
        assert warn_mock.called

    def test_upsert_payment_link_non_existent_app_returns_none(self, monkeypatch):
        """When an app is not found in database, return None without crashing."""
        _setup_stubs_and_import()

        monkeypatch.setattr(apps_utils, "get_app_by_id_db", lambda _id: None)

        result = apps_utils.upsert_app_payment_link(
            app_id="missing_app_404",
            is_paid_app=True,
            price=10.0,
            payment_plan="monthly_recurring",
            uid="user_dev_1",
        )

        assert result is None

    def test_upsert_payment_link_valid_app_succeeds(self, monkeypatch):
        """A well-formed app document must build recurring Stripe link and return updated App model."""
        _setup_stubs_and_import()

        app_data = _valid_app_dict("valid_app_999")
        monkeypatch.setattr(apps_utils, "get_app_by_id_db", lambda _id: app_data)
        monkeypatch.setattr(apps_utils, "get_stripe_connect_account_id", lambda _uid: "acct_test")
        monkeypatch.setattr(apps_utils, "update_app_in_db", lambda _d: None)

        fake_stripe = MagicMock()
        fake_stripe.create_product.return_value = SimpleNamespace(id="prod_test")
        fake_stripe.create_app_monthly_recurring_price.return_value = SimpleNamespace(id="price_test")
        fake_stripe.create_app_payment_link.return_value = SimpleNamespace(
            id="link_test", url="https://buy.stripe.com/test"
        )
        monkeypatch.setattr(apps_utils, "stripe", fake_stripe)

        result = apps_utils.upsert_app_payment_link(
            app_id="valid_app_999",
            is_paid_app=True,
            price=9.99,
            payment_plan="monthly_recurring",
            uid="user_dev_1",
        )

        assert result is not None
        assert result.id == "valid_app_999"
        assert result.payment_link == "https://buy.stripe.com/test"

    def test_upsert_payment_link_ast_uses_safe_build_app(self):
        """Verify via AST that upsert_app_payment_link does not use raw App(**...) constructor."""
        _setup_stubs_and_import()

        src = inspect.getsource(apps_utils.upsert_app_payment_link)
        tree = ast.parse(src)

        raw_app_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Detects bare App(**...) instantiation
                if isinstance(func, ast.Name) and func.id == "App":
                    has_double_star = any(kw.arg is None for kw in node.keywords)
                    if has_double_star:
                        raw_app_calls.append(node.lineno)

        assert not raw_app_calls, (
            f"Found bare App(**...) call in upsert_app_payment_link at line(s) {raw_app_calls}. "
            "Use _safe_build_app(...) instead."
        )
