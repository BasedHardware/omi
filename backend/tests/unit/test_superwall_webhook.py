"""Tests for the Superwall webhook handler — signature verification, idempotency,
and per-event ``user.subscription`` mutations.

Mirrors the Superwall normalized webhook payload shape documented at
https://superwall.com/docs/integrations/webhooks. The handler must:
  - reject bad / missing / stale signatures
  - short-circuit on duplicate ``svix-id`` (svix retries shouldn't double-apply)
  - resolve ``product_id`` → ``PlanType`` via the Firestore product map
  - infer source (ios vs android) from event metadata
  - mutate ``Subscription`` correctly per event type, including the legacy-Stripe
    conflict path (accept + log warning, no auto-cancel of Stripe)
"""

import base64
import hashlib
import hmac
import json
import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

# Stub heavy deps before importing target.
sys.modules.setdefault(
    "database._client",
    types.SimpleNamespace(db=MagicMock(), document_id_from_seed=MagicMock(return_value="seed_id")),
)
sys.modules.setdefault("database.cache", types.SimpleNamespace(get_memory_cache=MagicMock()))

from models.users import PlanType, Subscription, SubscriptionSource, SubscriptionStatus

# ── Signature verification ──────────────────────────────────────────────────


_SECRET_RAW = b"superwall_test_secret_bytes_xx"
_SECRET = "whsec_" + base64.b64encode(_SECRET_RAW).decode()


def _sign(svix_id: str, ts: str, body: bytes, secret_bytes: bytes = _SECRET_RAW) -> str:
    digest = hmac.new(secret_bytes, f"{svix_id}.{ts}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


class TestVerifySignature:
    def test_valid_signature_accepted(self):
        from routers.superwall import verify_signature

        body = b'{"type":"initial_purchase","app_user_id":"uid1"}'
        ts = str(int(time.time()))
        svix_id = "msg_abc"
        sig = _sign(svix_id, ts, body)
        assert verify_signature(_SECRET, svix_id, ts, sig, body) is True

    def test_tampered_body_rejected(self):
        from routers.superwall import verify_signature

        body = b'{"type":"initial_purchase","app_user_id":"uid1"}'
        ts = str(int(time.time()))
        svix_id = "msg_abc"
        sig = _sign(svix_id, ts, body)
        assert verify_signature(_SECRET, svix_id, ts, sig, body + b'x') is False

    def test_wrong_secret_rejected(self):
        from routers.superwall import verify_signature

        body = b'{"type":"initial_purchase"}'
        ts = str(int(time.time()))
        svix_id = "msg_abc"
        sig = _sign(svix_id, ts, body, secret_bytes=b"different_secret_bytes_xxxxxxx")
        assert verify_signature(_SECRET, svix_id, ts, sig, body) is False

    def test_stale_timestamp_rejected(self):
        from routers.superwall import verify_signature

        body = b'{"type":"renewal"}'
        old_ts = str(int(time.time()) - 600)  # 10 min old > 5 min tolerance
        svix_id = "msg_abc"
        sig = _sign(svix_id, old_ts, body)
        assert verify_signature(_SECRET, svix_id, old_ts, sig, body) is False

    def test_missing_headers_rejected(self):
        from routers.superwall import verify_signature

        body = b'{}'
        assert verify_signature(_SECRET, None, "1", "v1,xx", body) is False
        assert verify_signature(_SECRET, "id", None, "v1,xx", body) is False
        assert verify_signature(_SECRET, "id", "1", None, body) is False

    def test_multi_signature_header_one_valid(self):
        """svix may send multiple v1 signatures (key rotation). One match suffices."""
        from routers.superwall import verify_signature

        body = b'{"type":"renewal"}'
        ts = str(int(time.time()))
        svix_id = "msg_abc"
        good = _sign(svix_id, ts, body)
        bogus = "v1,deadbeefdeadbeefdeadbeefdeadbeef=="
        # Header form: space-separated tokens
        combined = f"{bogus} {good}"
        assert verify_signature(_SECRET, svix_id, ts, combined, body) is True


# ── Product → PlanType resolution ───────────────────────────────────────────


class TestResolvePlan:
    def test_known_product_resolves(self):
        from routers import superwall

        with patch.object(
            superwall,
            "get_superwall_product_map",
            return_value={"com.omi.app.lite_monthly": "lite"},
        ):
            assert superwall.resolve_plan("com.omi.app.lite_monthly") == PlanType.lite

    def test_unknown_product_returns_none(self):
        from routers import superwall

        with patch.object(superwall, "get_superwall_product_map", return_value={}):
            assert superwall.resolve_plan("com.omi.app.unknown") is None

    def test_mapping_to_invalid_plan_returns_none(self):
        from routers import superwall

        with patch.object(
            superwall,
            "get_superwall_product_map",
            return_value={"com.omi.app.weird": "not_a_plan"},
        ):
            assert superwall.resolve_plan("com.omi.app.weird") is None

    def test_play_store_triple_resolves_via_normalized_key(self):
        """Google Play v5 sends ``<product>:<base_plan>:<offer>`` —
        the bare-id portion should still resolve from the same map.
        """
        from routers import superwall

        with patch.object(
            superwall,
            "get_superwall_product_map",
            return_value={"com.omi.app.lite_monthly": "lite"},
        ):
            assert superwall.resolve_plan("com.omi.app.lite_monthly:monthly:sw-auto") == PlanType.lite
            assert superwall.resolve_plan("com.omi.app.lite_monthly") == PlanType.lite


# ── Per-event handlers ──────────────────────────────────────────────────────


class TestHandlers:
    # Handlers receive the inner `data` envelope from Superwall's webhook —
    # camelCase keys, expirationAt in milliseconds, store as APP_STORE/PLAY_STORE.
    def _payload(self, **overrides) -> dict:
        base = {
            'originalAppUserId': 'uid_test',
            'productId': 'com.omi.app.lite_monthly',
            'originalTransactionId': 'sub_xyz',
            'expirationAt': 1900000000000,  # ms since epoch (Superwall's format)
            'store': 'APP_STORE',
        }
        base.update(overrides)
        return base

    def test_initial_purchase_writes_active_sub(self):
        from routers import superwall

        with (
            patch("database.users.get_user_valid_subscription", return_value=None),
            patch("database.users.update_user_subscription") as mock_update,
        ):
            superwall.handle_initial_purchase(
                "uid_test", PlanType.lite, SubscriptionSource.superwall_ios, self._payload()
            )
        called_uid, sub_dict = mock_update.call_args.args
        assert called_uid == "uid_test"
        assert sub_dict["plan"] == "lite"
        assert sub_dict["status"] == "active"
        assert sub_dict["source"] == "superwall_ios"
        assert sub_dict["superwall_subscription_id"] == "sub_xyz"
        # expirationAt was 1900000000000 ms → stored as 1900000000 seconds
        assert sub_dict["current_period_end"] == 1900000000
        assert sub_dict["cancel_at_period_end"] is False

    def test_initial_purchase_with_active_stripe_logs_but_accepts(self, caplog):
        from routers import superwall

        existing = Subscription(
            plan=PlanType.unlimited,
            status=SubscriptionStatus.active,
            source=SubscriptionSource.stripe,
        )
        with (
            patch("database.users.get_user_valid_subscription", return_value=existing),
            patch("database.users.update_user_subscription") as mock_update,
            caplog.at_level("WARNING"),
        ):
            superwall.handle_initial_purchase(
                "uid_test", PlanType.lite, SubscriptionSource.superwall_ios, self._payload()
            )
        # The Superwall sub IS written (Apple/Google already charged).
        assert mock_update.called
        # Conflict warning is emitted for ops follow-up.
        assert any("active Stripe sub" in r.getMessage() for r in caplog.records)

    def test_cancellation_sets_cancel_at_period_end(self):
        from routers import superwall

        with patch("database.users.update_user_subscription") as mock_update:
            superwall.handle_cancellation("uid_test", PlanType.lite, SubscriptionSource.superwall_ios, self._payload())
        sub_dict = mock_update.call_args.args[1]
        assert sub_dict["cancel_at_period_end"] is True
        assert sub_dict["status"] == "active"  # still active until period_end

    def test_expiration_reverts_to_basic(self):
        from routers import superwall

        with patch("database.users.update_user_subscription") as mock_update:
            superwall.handle_expiration("uid_test", PlanType.lite, SubscriptionSource.superwall_ios, self._payload())
        sub_dict = mock_update.call_args.args[1]
        assert sub_dict["plan"] == "basic"
        assert sub_dict["status"] == "inactive"

    def test_renewal_clears_cancel_flag(self):
        from routers import superwall

        with patch("database.users.update_user_subscription") as mock_update:
            superwall.handle_renewal("uid_test", PlanType.lite, SubscriptionSource.superwall_ios, self._payload())
        sub_dict = mock_update.call_args.args[1]
        assert sub_dict["cancel_at_period_end"] is False
        assert sub_dict["status"] == "active"

    def test_product_change_overwrites_plan(self):
        from routers import superwall

        with patch("database.users.update_user_subscription") as mock_update:
            superwall.handle_product_change(
                "uid_test",
                PlanType.unlimited_v2,
                SubscriptionSource.superwall_ios,
                self._payload(productId="com.omi.app.unlimited_v2_monthly"),
            )
        sub_dict = mock_update.call_args.args[1]
        assert sub_dict["plan"] == "unlimited_v2"


class TestSourceDetection:
    """Superwall's `store` field uses uppercase values per their webhook spec:
    APP_STORE / PLAY_STORE / STRIPE.
    """

    def test_play_store_event_is_android(self):
        from routers.superwall import _detect_source

        assert _detect_source({"store": "PLAY_STORE"}) == SubscriptionSource.superwall_android

    def test_app_store_event_is_ios(self):
        from routers.superwall import _detect_source

        assert _detect_source({"store": "APP_STORE"}) == SubscriptionSource.superwall_ios

    def test_stripe_store_defaults_to_ios(self):
        # Superwall-on-Stripe isn't a path we use; default to iOS rather than
        # silently mislabeling.
        from routers.superwall import _detect_source

        assert _detect_source({"store": "STRIPE"}) == SubscriptionSource.superwall_ios

    def test_missing_store_defaults_to_ios(self):
        from routers.superwall import _detect_source

        assert _detect_source({}) == SubscriptionSource.superwall_ios


# ── Dispatch ────────────────────────────────────────────────────────────────


class TestDispatch:
    """dispatch_event reads the outer Superwall envelope: top-level `type` +
    nested `data` dict containing originalAppUserId / productId / etc.
    """

    def test_unknown_event_type_ignored(self):
        from routers import superwall

        result = superwall.dispatch_event(
            "unsupported_event",
            {"type": "unsupported_event", "data": {"originalAppUserId": "uid_x"}},
        )
        assert result == "ignored"

    def test_missing_app_user_id_returns_error(self):
        from routers import superwall

        result = superwall.dispatch_event(
            "initial_purchase",
            {"type": "initial_purchase", "data": {"productId": "com.omi.app.lite_monthly"}},
        )
        assert result == "missing_uid"

    def test_anonymous_alias_returns_error(self):
        """If the user purchased before identify() was called, Superwall sends
        the SDK's anonymous alias ($SuperwallAlias:UUID). We can't reconcile
        that to an omi user — reject so svix stops retrying.
        """
        from routers import superwall

        result = superwall.dispatch_event(
            "initial_purchase",
            {
                "type": "initial_purchase",
                "data": {
                    "originalAppUserId": "$SuperwallAlias:7152E89E-60A6-4B2E-9C67-D7ED8F5BE372",
                    "productId": "com.omi.app.lite_monthly",
                },
            },
        )
        assert result == "missing_uid"

    def test_unknown_product_returns_error(self):
        from routers import superwall

        with patch.object(superwall, "get_superwall_product_map", return_value={}):
            result = superwall.dispatch_event(
                "initial_purchase",
                {
                    "type": "initial_purchase",
                    "data": {
                        "originalAppUserId": "uid_x",
                        "productId": "com.omi.app.unknown",
                    },
                },
            )
        assert result == "unknown_product"

    def test_full_initial_purchase_dispatch(self):
        from routers import superwall

        # Real Superwall envelope: top-level routing fields + nested data dict.
        payload = {
            "object": "event",
            "type": "initial_purchase",
            "projectId": 22416,
            "applicationId": 44831,
            "timestamp": 1900000000000,
            "data": {
                "originalAppUserId": "uid_z",
                "productId": "com.omi.app.lite_monthly",
                "originalTransactionId": "sub_z",
                "transactionId": "txn_z",
                "expirationAt": 1900000000000,  # ms
                "store": "APP_STORE",
                "environment": "SANDBOX",
                "isTrialConversion": False,
            },
        }
        with (
            patch.object(superwall, "get_superwall_product_map", return_value={"com.omi.app.lite_monthly": "lite"}),
            patch("database.users.get_user_valid_subscription", return_value=None),
            patch("database.users.update_user_subscription") as mock_update,
        ):
            assert superwall.dispatch_event("initial_purchase", payload) == "processed"
        assert mock_update.called
        called_uid, sub_dict = mock_update.call_args.args
        assert called_uid == "uid_z"
        assert sub_dict["plan"] == "lite"
        assert sub_dict["source"] == "superwall_ios"
        assert sub_dict["superwall_subscription_id"] == "sub_z"
        assert sub_dict["current_period_end"] == 1900000000  # ms → s
