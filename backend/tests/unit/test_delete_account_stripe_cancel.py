"""Account deletion cancels Stripe before starting the grace timer or wipe.

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
        "database.sync_jobs": AutoMockModule("database.sync_jobs"),
        "database._client": AutoMockModule("database._client"),
        "database.legal_holds": AutoMockModule("database.legal_holds"),
        "database.users": AutoMockModule("database.users"),
        "database.processing_backlog": AutoMockModule("database.processing_backlog"),
        "database.action_items": AutoMockModule("database.action_items"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.memories": AutoMockModule("database.memories"),
        "database.screen_activity": AutoMockModule("database.screen_activity"),
        "database.frame_requests": AutoMockModule("database.frame_requests"),
        "database.vector_db": AutoMockModule("database.vector_db"),
        "database.dev_api_key": AutoMockModule("database.dev_api_key"),
        "database.mcp_api_key": AutoMockModule("database.mcp_api_key"),
        "database.mcp_oauth": AutoMockModule("database.mcp_oauth"),
        "database.messaging": AutoMockModule("database.messaging"),
        "services.users.agent_vm_account_cleanup": AutoMockModule("services.users.agent_vm_account_cleanup"),
        "utils": _pkg("utils"),
        "utils.cloud_tasks": AutoMockModule("utils.cloud_tasks"),
        "utils.stripe": AutoMockModule("utils.stripe"),
        "utils.executors": AutoMockModule("utils.executors"),
        "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
        "utils.observability": _pkg("utils.observability"),
        "utils.observability.fallback": AutoMockModule("utils.observability.fallback"),
        "utils.integration_telemetry": AutoMockModule("utils.integration_telemetry"),
        "utils.other": _pkg("utils.other"),
        "utils.other.endpoints": AutoMockModule("utils.other.endpoints"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
        "utils.memory.memory_service": AutoMockModule("utils.memory.memory_service"),
        "utils.memory.memory_system": AutoMockModule("utils.memory.memory_system"),
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.frame_request_storage": AutoMockModule("utils.retrieval.frame_request_storage"),
        "utils.other.storage": AutoMockModule("utils.other.storage"),
        "utils.sync": _pkg("utils.sync"),
        "utils.sync.cap_hold": AutoMockModule("utils.sync.cap_hold"),
        "utils.twilio_service": AutoMockModule("utils.twilio_service"),
    }
    with stub_modules(fakes):
        service = load_module_fresh(
            "services.users.account_deletion",
            os.path.join(str(_BACKEND), "services", "users", "account_deletion.py"),
        )
        service.users_db.mark_user_deletion_wipe_intent.return_value = {
            'wipe_job_id': 'job-1',
            'dispatch_claimed': True,
        }
        service.deletion_grace_db.promote_grace_to_immediate.return_value = None
        service.account_deletion_grace_enabled = lambda: False
        service.users_db.mark_user_deletion_wipe_started.return_value = True
        service.users_db.get_existing_user_subscription.return_value = None
        service.stripe_utils.find_billable_app_subscription_ids.return_value = []
        service.firebase_auth.revoke_refresh_tokens = MagicMock()
        service.delete_account_credentials = MagicMock()
        yield service


def _sub(stripe_subscription_id):
    s = MagicMock()
    s.stripe_subscription_id = stripe_subscription_id
    return s


def test_paid_user_subscription_is_cancelled_before_immediate_wipe_dispatch(users_service):
    with patch.object(
        users_service.users_db, 'get_existing_user_subscription', return_value=_sub('sub_123')
    ), patch.object(
        users_service.stripe_utils, 'cancel_subscription_for_account_deletion', return_value=MagicMock()
    ) as cancel, patch.object(
        users_service.auth, 'delete_account'
    ) as fb_delete, patch.object(
        users_service, 'submit_with_context'
    ) as submit:
        resp = users_service.start_account_deletion(uid='uid1')
    cancel.assert_called_once_with('sub_123')
    fb_delete.assert_not_called()
    submit.assert_called_once_with(users_service.cleanup_executor, users_service.background_wipe_user_data, 'uid1')
    assert resp['status'] == 'ok'


def test_free_user_does_not_call_stripe(users_service):
    with patch.object(users_service.users_db, 'get_existing_user_subscription', return_value=_sub(None)), patch.object(
        users_service.stripe_utils, 'cancel_subscription_for_account_deletion'
    ) as cancel, patch.object(users_service.auth, 'delete_account'), patch.object(
        users_service, 'submit_with_context'
    ) as submit:
        resp = users_service.start_account_deletion(uid='uid1')
    cancel.assert_not_called()
    submit.assert_called_once_with(users_service.cleanup_executor, users_service.background_wipe_user_data, 'uid1')
    assert resp['status'] == 'ok'


def test_request_does_not_start_the_grace_or_wipe_when_stripe_cancellation_fails(users_service):
    with patch.object(
        users_service.users_db, 'get_existing_user_subscription', return_value=_sub('sub_123')
    ), patch.object(
        users_service.stripe_utils,
        'cancel_subscription_for_account_deletion',
        side_effect=Exception('stripe down'),
    ), patch.object(
        users_service.users_db, 'mark_user_deletion_billing_failed'
    ) as mark_billing_failed, patch.object(
        users_service.auth, 'delete_account'
    ) as fb_delete, patch.object(
        users_service, 'submit_with_context'
    ) as submit:
        with pytest.raises(users_service.DeletionBillingError):
            users_service.start_account_deletion(uid='uid1')
    mark_billing_failed.assert_not_called()
    fb_delete.assert_not_called()
    submit.assert_not_called()
