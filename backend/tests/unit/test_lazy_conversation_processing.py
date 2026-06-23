"""Unit tests for lazy desktop conversation processing (freemium cost cut).

Validates `should_defer_desktop_processing`: desktop users on a non-desktop-entitled plan
(basic / Neo) without BYOK are deferred (raw transcript on capture, enriched on first open);
Operator/Architect and BYOK users are processed normally; lookups fail safe to "process".

Uses sys.modules stubs so importing utils.subscription doesn't trigger Firestore/Firebase init.
"""

import sys
import types

import pytest
from unittest.mock import MagicMock


class TestShouldDeferDesktopProcessing:
    @pytest.fixture(autouse=True)
    def _setup_subscription(self):
        def _stub(name):
            if name not in sys.modules:
                sys.modules[name] = types.ModuleType(name)
            return sys.modules[name]

        saved = {}
        stubs = [
            'google.cloud',
            'google.cloud.firestore',
            'google.cloud.firestore_v1',
            'firebase_admin',
            'firebase_admin.auth',
            'firebase_admin.firestore',
            'database._client',
            'database.redis_db',
            'database.users',
            'database.user_usage',
            'database.announcements',
        ]
        for name in stubs:
            saved[name] = sys.modules.get(name)
            mod = _stub(name)
            if name == 'database._client':
                mod.db = MagicMock()
            elif name == 'database.redis_db':
                mod.get_generic_cache = MagicMock(return_value=None)
                mod.set_generic_cache = MagicMock()
                mod.delete_generic_cache = MagicMock()
            elif name == 'database.users':
                mod.get_user_valid_subscription = MagicMock(return_value=None)
                mod.is_byok_active = MagicMock(return_value=False)
            elif name == 'database.announcements':
                mod.compare_versions = MagicMock()
            elif name == 'firebase_admin.auth':
                mod.get_user = MagicMock()

        if 'utils.subscription' in sys.modules:
            del sys.modules['utils.subscription']
        import utils.subscription as sub

        self._sub = sub
        self._users = sys.modules['database.users']
        yield
        for name in stubs:
            if saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]
        sys.modules.pop('utils.subscription', None)

    def _sub_with_plan(self, plan):
        s = MagicMock()
        s.plan = plan
        return s

    def test_basic_plan_is_deferred(self):
        from models.users import PlanType

        self._users.is_byok_active.return_value = False
        self._users.get_user_valid_subscription.return_value = None  # no sub => basic
        assert self._sub.should_defer_desktop_processing('uid') is True

    def test_neo_unlimited_is_deferred(self):
        from models.users import PlanType

        self._users.is_byok_active.return_value = False
        self._users.get_user_valid_subscription.return_value = self._sub_with_plan(PlanType.unlimited)
        assert self._sub.should_defer_desktop_processing('uid') is True

    def test_operator_is_not_deferred(self):
        from models.users import PlanType

        self._users.is_byok_active.return_value = False
        self._users.get_user_valid_subscription.return_value = self._sub_with_plan(PlanType.operator)
        assert self._sub.should_defer_desktop_processing('uid') is False

    def test_architect_is_not_deferred(self):
        from models.users import PlanType

        self._users.is_byok_active.return_value = False
        self._users.get_user_valid_subscription.return_value = self._sub_with_plan(PlanType.architect)
        assert self._sub.should_defer_desktop_processing('uid') is False

    def test_byok_basic_is_not_deferred(self):
        from models.users import PlanType

        self._users.is_byok_active.return_value = True
        self._users.get_user_valid_subscription.return_value = None
        assert self._sub.should_defer_desktop_processing('uid') is False

    def test_lookup_error_fails_safe_to_not_deferred(self):
        self._users.is_byok_active.side_effect = RuntimeError("firestore down")
        assert self._sub.should_defer_desktop_processing('uid') is False
