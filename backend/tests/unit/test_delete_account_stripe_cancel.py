"""Regression test for issue #6750 — delete-account must cancel the active Stripe subscription.

Before the fix, DELETE /v1/users/delete-account revoked Firebase auth and wiped Firestore but never
canceled the user's Stripe subscription, so a paying user kept getting billed with no way to log back
in and cancel. The handler now cancels the subscription (best-effort) before the wipe.

``services.users.account_deletion`` binds its collaborators at import (``from database import users as
users_db``, ``from utils import stripe as stripe_utils``, …) and those packages pull heavy chains with
import-time side effects, so the fake ``database``/``utils`` namespaces must be active before the
module is exec'd. This is the sanctioned Tier-2 "fake must precede import" case: see
``backend/docs/test_isolation.md`` and ``testing.import_isolation.load_module_fresh``.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _pkg(name):
    m = AutoMockModule(name)
    m.__path__ = []
    return m


@pytest.fixture(scope="module")
def users_service():
    """Load a fresh services.users.account_deletion against stubbed database/utils namespaces."""
    fakes = {
        "database": _pkg("database"),
        "database.users": AutoMockModule("database.users"),
        "database.action_items": AutoMockModule("database.action_items"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.memories": AutoMockModule("database.memories"),
        "database.screen_activity": AutoMockModule("database.screen_activity"),
        "database.vector_db": AutoMockModule("database.vector_db"),
        "utils": _pkg("utils"),
        "utils.cloud_tasks": AutoMockModule("utils.cloud_tasks"),
        "utils.stripe": AutoMockModule("utils.stripe"),
        "utils.executors": AutoMockModule("utils.executors"),
        "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
        "utils.other": _pkg("utils.other"),
        "utils.other.endpoints": AutoMockModule("utils.other.endpoints"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
        "utils.other.storage": AutoMockModule("utils.other.storage"),
        "utils.twilio_service": AutoMockModule("utils.twilio_service"),
    }
    with stub_modules(fakes):
        yield load_module_fresh(
            "services.users.account_deletion",
            os.path.join(str(_BACKEND), "services", "users", "account_deletion.py"),
        )


def _sub(stripe_subscription_id):
    s = MagicMock()
    s.stripe_subscription_id = stripe_subscription_id
    return s


def test_paid_user_subscription_is_canceled_before_wipe(users_service):
    with patch.object(
        users_service.users_db, 'get_user_subscription', return_value=_sub('sub_123')
    ) as get_sub, patch.object(
        users_service.stripe_utils, 'cancel_subscription', return_value=MagicMock()
    ) as cancel, patch.object(
        users_service.auth, 'delete_account'
    ) as fb_delete, patch.object(
        users_service, 'submit_with_context'
    ) as submit:
        resp = users_service.start_account_deletion(uid='uid1')
    get_sub.assert_called_once_with('uid1')
    cancel.assert_called_once_with('sub_123')
    fb_delete.assert_called_once()  # deletion still proceeds
    submit.assert_called_once_with(users_service.cleanup_executor, users_service.background_wipe_user_data, 'uid1')
    assert resp['status'] == 'ok'


def test_free_user_does_not_call_stripe(users_service):
    with patch.object(users_service.users_db, 'get_user_subscription', return_value=_sub(None)), patch.object(
        users_service.stripe_utils, 'cancel_subscription'
    ) as cancel, patch.object(users_service.auth, 'delete_account'), patch.object(
        users_service, 'submit_with_context'
    ) as submit:
        resp = users_service.start_account_deletion(uid='uid1')
    cancel.assert_not_called()
    submit.assert_called_once_with(users_service.cleanup_executor, users_service.background_wipe_user_data, 'uid1')
    assert resp['status'] == 'ok'


def test_stripe_error_does_not_block_deletion(users_service):
    with patch.object(users_service.users_db, 'get_user_subscription', return_value=_sub('sub_123')), patch.object(
        users_service.stripe_utils, 'cancel_subscription', side_effect=Exception('stripe down')
    ), patch.object(users_service.auth, 'delete_account') as fb_delete, patch.object(
        users_service, 'submit_with_context'
    ) as submit:
        resp = users_service.start_account_deletion(uid='uid1')
    fb_delete.assert_called_once()  # best-effort: Stripe failure must not abort deletion
    submit.assert_called_once_with(users_service.cleanup_executor, users_service.background_wipe_user_data, 'uid1')
    assert resp['status'] == 'ok'
