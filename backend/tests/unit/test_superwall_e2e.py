"""End-to-end test for the Superwall webhook + cross-rail conflict guard.

Each layer of the rollout is unit-tested individually
(``test_superwall_webhook.py`` for sig + handlers, ``test_catalog_filter.py``
for predicates, ``test_plan_caps_config.py`` for caps). This file glues them
together via a real FastAPI app + ``TestClient`` so the integration boundaries
— signature verification on raw bytes, idempotency table writes, Pydantic
round-trips, route registration, the checkout-session conflict guard — all
exercise their happy and sad paths against the real ``routers/superwall.py``
and ``routers/payment.py``.

Heavy setup at module load mirrors the pattern in
``test_available_plans_resilience.py`` (database/_client + firebase_admin +
all leaf utils stubbed before importing the routers). This keeps the test
self-contained and avoids needing a real Firestore / Redis / Deepgram in CI.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

# ── Env vars consumed at import time ───────────────────────────────────────
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
_WEBHOOK_SECRET_RAW = b"superwall_e2e_test_secret_bytes_x"
_WEBHOOK_SECRET = "whsec_" + base64.b64encode(_WEBHOOK_SECRET_RAW).decode()
os.environ["SUPERWALL_WEBHOOK_SECRET"] = _WEBHOOK_SECRET

# Stripe price IDs the payment router validates at startup. Real prices not
# needed — the conflict-guard test never reaches Stripe.
os.environ["STRIPE_UNLIMITED_MONTHLY_PRICE_ID"] = "price_unlimited_monthly_e2e"
os.environ["STRIPE_UNLIMITED_ANNUAL_PRICE_ID"] = "price_unlimited_annual_e2e"
os.environ["STRIPE_ARCHITECT_MONTHLY_PRICE_ID"] = "price_architect_monthly_e2e"
os.environ["STRIPE_ARCHITECT_ANNUAL_PRICE_ID"] = "price_architect_annual_e2e"

# ── Stub heavy infrastructure before any project import ────────────────────
# Import the real `database` package first so `import database.plan_caps_config`
# can resolve to the on-disk module. Then stub specific leaf submodules in
# sys.modules — those stubs win because they're already cached when the
# import system goes looking.
import database as _real_database  # noqa: F401  (kept as a sys.modules anchor)

_mock_client = types.ModuleType("database._client")
_mock_client.db = MagicMock()
_mock_client.document_id_from_seed = MagicMock(return_value="seed_id")
sys.modules["database._client"] = _mock_client

_fb_admin = types.ModuleType("firebase_admin")
_fb_admin.auth = MagicMock()
sys.modules["firebase_admin"] = _fb_admin
sys.modules["firebase_admin.auth"] = _fb_admin.auth

for _name in [
    "database.users",
    "database.notifications",
    "database.conversations",
    "database.memories",
    "database.action_items",
    "database.redis_db",
    "database.user_usage",
    "database.cache",
    "database.announcements",
    "database.superwall_events",
]:
    sys.modules[_name] = types.ModuleType(_name)

# database.announcements: real `compare_versions` shape so should_show_new_plans works.
_announcements = sys.modules["database.announcements"]


def _compare_versions(a, b):
    a_parts = [int(x) for x in a.split(".")]
    b_parts = [int(x) for x in b.split(".")]
    for x, y in zip(a_parts, b_parts):
        if x != y:
            return 1 if x > y else -1
    return len(a_parts) - len(b_parts)


_announcements.compare_versions = _compare_versions

# database.superwall_events: in-memory idempotency table per test.
_events = sys.modules["database.superwall_events"]
_processed_ids: set[str] = set()
_events.already_processed = lambda svix_id: svix_id in _processed_ids
_events.record_processed = lambda svix_id, event_type, uid: _processed_ids.add(svix_id)

# database.users: in-memory subscription state per uid.
_users_db_mock = sys.modules["database.users"]
_subscription_state: dict = {"sub_dict": None, "valid_sub": None}


def _update_user_subscription(uid, sub_dict):
    _subscription_state["sub_dict"] = sub_dict


def _get_user_valid_subscription(uid):
    return _subscription_state["valid_sub"]


_users_db_mock.update_user_subscription = MagicMock(side_effect=_update_user_subscription)
_users_db_mock.get_user_valid_subscription = MagicMock(side_effect=_get_user_valid_subscription)
_users_db_mock.get_user_subscription = MagicMock(return_value=None)
_users_db_mock.get_stripe_customer_id = MagicMock(return_value=None)
_users_db_mock.is_byok_active = MagicMock(return_value=False)
for _attr in [
    "set_stripe_customer_id",
    "get_user_by_stripe_customer_id",
    "get_stripe_connect_account_id",
    "set_stripe_connect_account_id",
    "set_paypal_payment_details",
    "get_default_payment_method",
    "set_default_payment_method",
    "get_paypal_payment_details",
]:
    setattr(_users_db_mock, _attr, MagicMock())

_redis = sys.modules["database.redis_db"]
_redis.set_credits_invalidation_signal = MagicMock()
_redis.r = MagicMock()

# Utils stubs for heavy external deps that get pulled in via routers/payment.
for _name in [
    "utils.fair_use",
    "utils.notifications",
    "utils.apps",
    "utils.stripe",
    "utils.byok",
    "utils.log_sanitizer",
]:
    _m = types.ModuleType(_name)
    sys.modules[_name] = _m

sys.modules["utils.fair_use"].clear_fair_use_on_upgrade = MagicMock()

_notif_mod = sys.modules["utils.notifications"]
_notif_mod.send_notification = MagicMock()
_notif_mod.send_subscription_paid_personalized_notification = MagicMock()

_apps_mod = sys.modules["utils.apps"]
for _attr in ["find_app_subscription", "get_is_user_paid_app", "paid_app", "set_user_app_sub_customer_id"]:
    setattr(_apps_mod, _attr, MagicMock())

_stripe_utils = sys.modules["utils.stripe"]
_stripe_utils.base_url = "http://test"
_stripe_utils.create_connect_account = MagicMock()
_stripe_utils.refresh_connect_account_link = MagicMock()
_stripe_utils.is_onboarding_complete = MagicMock()
_stripe_utils.create_subscription_checkout_session = MagicMock()
_stripe_utils.modify_subscription = MagicMock()
_stripe_utils.parse_event = MagicMock()

_byok = sys.modules["utils.byok"]
_byok.get_byok_key = MagicMock(return_value=None)

_sanitizer = sys.modules["utils.log_sanitizer"]
_sanitizer.sanitize = lambda s: s
_sanitizer.sanitize_pii = lambda s: s

# utils.other.endpoints — auth dep
_utils_other = types.ModuleType("utils.other")
sys.modules["utils.other"] = _utils_other
_endpoints = types.ModuleType("utils.other.endpoints")
_endpoints.get_current_user_uid = lambda: "uid_test"
_endpoints.get_current_user_uid_no_byok_validation = lambda: "uid_test"
sys.modules["utils.other.endpoints"] = _endpoints
_utils_other.endpoints = _endpoints

# Patch the Firestore-backed product map so resolve_plan() works without hitting Firestore.
import database.plan_caps_config as plan_caps_config

plan_caps_config._get_config = lambda: {
    "superwall_product_map": {
        "com.omi.app.lite_monthly": "lite",
        "com.omi.app.lite_yearly": "lite",
        "com.omi.app.plus_monthly": "plus",
        "com.omi.app.plus_yearly": "plus",
        "com.omi.app.max_monthly": "max",
        "com.omi.app.max_yearly": "max",
    }
}

# ── Build the test app ─────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import superwall as superwall_router
from routers import payment as payment_router
from utils.other import endpoints as auth_endpoints

app = FastAPI()
app.include_router(superwall_router.router)
app.include_router(payment_router.router)
app.dependency_overrides[auth_endpoints.get_current_user_uid] = lambda: "uid_test"
app.dependency_overrides[auth_endpoints.get_current_user_uid_no_byok_validation] = lambda: "uid_test"
client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────


def _sign(svix_id: str, timestamp: str, body: bytes) -> str:
    payload = f"{svix_id}.{timestamp}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(_WEBHOOK_SECRET_RAW, payload, hashlib.sha256).digest()).decode()


def _post_webhook(payload: dict, svix_id: str = "msg_e2e_1", svix_signature: str | None = None):
    body_bytes = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = svix_signature if svix_signature is not None else _sign(svix_id, ts, body_bytes)
    return client.post(
        "/v1/superwall/webhook",
        content=body_bytes,
        headers={
            "svix-id": svix_id,
            "svix-timestamp": ts,
            "svix-signature": sig,
            "Content-Type": "application/json",
        },
    )


def _reset_state():
    _processed_ids.clear()
    _subscription_state["sub_dict"] = None
    _subscription_state["valid_sub"] = None
    _users_db_mock.update_user_subscription.reset_mock()


# ── Tests ──────────────────────────────────────────────────────────────────


class TestWebhookHappyPath:
    def setup_method(self):
        _reset_state()

    def test_initial_purchase_writes_plus_subscription(self):
        """Signed initial_purchase POST → 200, sub written with plan=plus, source=superwall_ios."""
        resp = _post_webhook(
            {
                "type": "initial_purchase",
                "app_user_id": "uid_test",
                "product_id": "com.omi.app.plus_monthly",
                "subscription_id": "sw_sub_123",
                "expires_at": 1900000000,
                "store": "app_store",
            }
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "processed"
        assert body["event_type"] == "initial_purchase"
        # Mock recorded the write
        assert _users_db_mock.update_user_subscription.call_count == 1
        sub_dict = _subscription_state["sub_dict"]
        assert sub_dict["plan"] == "plus"
        assert sub_dict["source"] == "superwall_ios"
        assert sub_dict["status"] == "active"
        assert sub_dict["superwall_subscription_id"] == "sw_sub_123"
        assert sub_dict["current_period_end"] == 1900000000
        assert sub_dict["cancel_at_period_end"] is False

    def test_play_store_event_routes_android_source(self):
        resp = _post_webhook(
            {
                "type": "initial_purchase",
                "app_user_id": "uid_test",
                "product_id": "com.omi.app.lite_yearly",
                "subscription_id": "sw_sub_play_1",
                "expires_at": 1900000000,
                "store": "play_store",
            },
            svix_id="msg_e2e_play",
        )
        assert resp.status_code == 200
        sub_dict = _subscription_state["sub_dict"]
        assert sub_dict["plan"] == "lite"
        assert sub_dict["source"] == "superwall_android"


class TestWebhookLifecycle:
    def setup_method(self):
        _reset_state()

    def test_cancellation_then_expiration(self):
        """cancellation → cancel_at_period_end=True; expiration → revert to basic."""
        # Cancellation
        resp1 = _post_webhook(
            {
                "type": "cancellation",
                "app_user_id": "uid_test",
                "product_id": "com.omi.app.plus_monthly",
                "subscription_id": "sw_sub_lc",
                "expires_at": 1900000000,
                "store": "app_store",
            },
            svix_id="msg_e2e_cancel",
        )
        assert resp1.status_code == 200
        cancelled = _subscription_state["sub_dict"]
        assert cancelled["plan"] == "plus"
        assert cancelled["status"] == "active"
        assert cancelled["cancel_at_period_end"] is True

        # Expiration → basic
        resp2 = _post_webhook(
            {
                "type": "expiration",
                "app_user_id": "uid_test",
                "product_id": "com.omi.app.plus_monthly",
                "subscription_id": "sw_sub_lc",
                "expires_at": 1900000000,
                "store": "app_store",
            },
            svix_id="msg_e2e_expire",
        )
        assert resp2.status_code == 200
        expired = _subscription_state["sub_dict"]
        assert expired["plan"] == "basic"
        assert expired["status"] == "inactive"


class TestSignatureVerification:
    def setup_method(self):
        _reset_state()

    def test_bad_signature_rejected(self):
        body = {"type": "initial_purchase", "app_user_id": "uid_test"}
        resp = _post_webhook(body, svix_id="msg_e2e_bad", svix_signature="v1,deadbeefdeadbeefdeadbeefdead==")
        assert resp.status_code == 401
        # No DB write on auth failure
        assert _users_db_mock.update_user_subscription.call_count == 0


class TestIdempotency:
    def setup_method(self):
        _reset_state()

    def test_duplicate_svix_id_short_circuits(self):
        """Second delivery of the same svix-id returns 'duplicate' and doesn't re-write."""
        payload = {
            "type": "initial_purchase",
            "app_user_id": "uid_test",
            "product_id": "com.omi.app.plus_monthly",
            "subscription_id": "sw_sub_dup",
            "expires_at": 1900000000,
            "store": "app_store",
        }
        resp1 = _post_webhook(payload, svix_id="msg_e2e_dup")
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "processed"

        resp2 = _post_webhook(payload, svix_id="msg_e2e_dup")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "duplicate"

        # Only the first delivery wrote the subscription.
        assert _users_db_mock.update_user_subscription.call_count == 1


class TestStripeConflictGuard:
    def setup_method(self):
        _reset_state()

    def test_checkout_session_422_when_active_superwall_sub(self):
        """Defense-in-depth: /v1/payments/checkout-session refuses to start a
        Stripe checkout when the user already holds an active Superwall sub.
        """
        from models.users import PlanType, Subscription, SubscriptionSource, SubscriptionStatus

        _subscription_state["valid_sub"] = Subscription(
            plan=PlanType.plus,
            status=SubscriptionStatus.active,
            source=SubscriptionSource.superwall_ios,
            superwall_subscription_id="sw_sub_conflict",
        )

        resp = client.post(
            "/v1/payments/checkout-session",
            json={"price_id": "price_unlimited_monthly_e2e"},
        )
        assert resp.status_code == 422
        assert "mobile" in resp.json()["detail"].lower()
