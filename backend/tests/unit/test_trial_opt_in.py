"""Opt-in desktop trial — covers `get_trial_metadata`, `_is_trial_expired_uncached`,
and the lazy backfill window introduced for the legacy auto-start era.

Mocks `firebase_auth.get_user` plus the four `users_db` calls the trial logic
touches. No HTTP, no real Firestore. The endpoint itself is a thin wrapper
around these two functions plus `set_subscription_trial_started_at`; its
semantics are covered transitively here.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# Stub heavy infrastructure before importing utils.subscription so the test
# never tries to pull in Firestore / firebase_admin / redis / database modules.
def _stub_modules():
    _fb_admin = types.ModuleType("firebase_admin")
    _fb_admin.auth = MagicMock()
    sys.modules.setdefault("firebase_admin", _fb_admin)
    sys.modules.setdefault("firebase_admin.auth", _fb_admin.auth)

    _db_mod = types.ModuleType("database")
    sys.modules.setdefault("database", _db_mod)
    for name in [
        "database.users",
        "database.user_usage",
        "database.redis_db",
        "database.announcements",
    ]:
        m = types.ModuleType(name)
        sys.modules.setdefault(name, m)
        setattr(_db_mod, name.split(".")[-1], m)

    sys.modules["database.announcements"].compare_versions = lambda a, b: 0


_stub_modules()


from models.users import (  # noqa: E402  (stubs above)
    PlanType,
    Subscription,
    SubscriptionStatus,
)
from utils import subscription as subscription_module  # noqa: E402
from utils.subscription import (  # noqa: E402
    TRIAL_LENGTH_SECONDS,
    _is_trial_expired_uncached,
    get_trial_metadata,
)

# ---------------------------------------------------------------------------
# Builders + a small users_db shim. Each test rebinds `users_db` on the
# subscription module to a fresh shim so tests are independent.
# ---------------------------------------------------------------------------


class _StubUsersDB:
    def __init__(self, *, plan=PlanType.basic, trial_started_at=None, is_byok=False):
        self.valid_sub = Subscription(plan=plan, status=SubscriptionStatus.active)
        self.raw_sub = Subscription(
            plan=plan,
            status=SubscriptionStatus.active,
            trial_started_at=trial_started_at,
        )
        self._is_byok = is_byok
        self.set_calls = []  # records (uid, started_at) tuples

    def get_user_valid_subscription(self, uid):
        return self.valid_sub

    def get_user_subscription(self, uid):
        return self.raw_sub

    def is_byok_active(self, uid):
        return self._is_byok

    def set_subscription_trial_started_at(self, uid, started_at):
        self.set_calls.append((uid, started_at))
        # Mirror the write so subsequent reads inside the same call see it.
        self.raw_sub.trial_started_at = started_at


def _firebase_user_record(creation_ms):
    user_metadata = MagicMock()
    user_metadata.creation_timestamp = creation_ms
    record = MagicMock()
    record.user_metadata = user_metadata
    return record


def _patch_world(monkeypatch, *, users_db, fb_creation_ms=None, now=1_700_000_000.0, has_byok_headers=False):
    monkeypatch.setattr(subscription_module, "users_db", users_db)
    monkeypatch.setattr(subscription_module.time, "time", lambda: now)
    monkeypatch.setattr(
        subscription_module.firebase_auth,
        "get_user",
        lambda uid: _firebase_user_record(fb_creation_ms),
    )
    monkeypatch.setattr(subscription_module, "_request_has_all_byok_keys", lambda: has_byok_headers)


# ---------------------------------------------------------------------------
# get_trial_metadata
# ---------------------------------------------------------------------------


def test_opt_in_available_when_no_stored_value_and_firebase_account_is_old(monkeypatch):
    """Brand-new behavior: no auto-start. User sees an opt-in offer."""
    now = 2_000_000_000.0
    old_creation_ms = (now - 30 * 86400) * 1000  # 30 days ago
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=None)
    _patch_world(monkeypatch, users_db=db, fb_creation_ms=old_creation_ms, now=now)

    md = get_trial_metadata("uid-old")

    assert md.trial_available is True
    assert md.trial_started_at is None
    assert md.trial_expired is False
    assert md.trial_duration_seconds == TRIAL_LENGTH_SECONDS
    assert db.set_calls == [], "must not backfill expired-derivation users"


def test_lazy_backfill_for_mid_trial_existing_user(monkeypatch):
    """Backward compat: a user currently mid-trial under the old derivation
    keeps their trial running, with `trial_started_at` lazily backfilled.
    """
    now = 2_000_000_000.0
    creation_ms = (now - 1 * 86400) * 1000  # 1 day ago — well within the window
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=None)
    _patch_world(monkeypatch, users_db=db, fb_creation_ms=creation_ms, now=now)

    md = get_trial_metadata("uid-midtrial")

    expected_started = int(creation_ms / 1000)
    assert db.set_calls == [("uid-midtrial", expected_started)], "must backfill exactly once"
    assert md.trial_started_at == expected_started
    assert md.trial_ends_at == expected_started + TRIAL_LENGTH_SECONDS
    assert md.trial_expired is False
    assert md.trial_available is False
    assert md.trial_remaining_seconds > 0


def test_stored_trial_mid_window_returns_live_countdown(monkeypatch):
    now = 2_000_000_000.0
    started = int(now) - 12 * 3600  # 12h into the trial
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=started)
    _patch_world(monkeypatch, users_db=db, now=now)

    md = get_trial_metadata("uid-active")

    assert md.trial_started_at == started
    assert md.trial_ends_at == started + TRIAL_LENGTH_SECONDS
    assert md.trial_remaining_seconds == TRIAL_LENGTH_SECONDS - 12 * 3600
    assert md.trial_expired is False
    assert md.trial_available is False
    assert db.set_calls == []


def test_stored_trial_past_window_returns_expired(monkeypatch):
    now = 2_000_000_000.0
    started = int(now) - TRIAL_LENGTH_SECONDS - 7200  # 2h after expiry
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=started)
    _patch_world(monkeypatch, users_db=db, now=now)

    md = get_trial_metadata("uid-expired")

    assert md.trial_expired is True
    assert md.trial_available is False, "expired ≠ available; user already used it"
    assert md.trial_remaining_seconds == 0


def test_paid_desktop_plan_never_sees_opt_in_offer(monkeypatch):
    db = _StubUsersDB(plan=PlanType.operator, trial_started_at=None)
    _patch_world(monkeypatch, users_db=db)

    md = get_trial_metadata("uid-operator")

    assert md.trial_available is False
    assert md.trial_started_at is None
    assert md.trial_expired is False


def test_byok_active_never_sees_opt_in_offer(monkeypatch):
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=None, is_byok=True)
    _patch_world(monkeypatch, users_db=db)

    md = get_trial_metadata("uid-byok")

    assert md.trial_available is False


def test_request_with_byok_headers_short_circuits(monkeypatch):
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=None)
    _patch_world(monkeypatch, users_db=db, has_byok_headers=True)

    md = get_trial_metadata("uid-byok-headers")

    assert md.trial_available is False, "BYOK headers escape hatch wins"


# ---------------------------------------------------------------------------
# _is_trial_expired_uncached (the paywall gate)
# ---------------------------------------------------------------------------


def test_paywall_gate_returns_false_when_trial_never_started(monkeypatch):
    """Critical opt-in invariant: never paywall a user who hasn't opted in.
    They keep access to the basic free tier; the opt-in offer is what they
    see when they want to upgrade.
    """
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=None)
    _patch_world(monkeypatch, users_db=db)

    assert _is_trial_expired_uncached("uid-never") is False


def test_paywall_gate_uses_stored_timestamp_when_set(monkeypatch):
    now = 2_000_000_000.0
    started = int(now) - TRIAL_LENGTH_SECONDS - 60  # 1 min past expiry
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=started)
    _patch_world(monkeypatch, users_db=db, now=now)

    assert _is_trial_expired_uncached("uid-just-expired") is True


def test_paywall_gate_returns_false_mid_trial_window(monkeypatch):
    now = 2_000_000_000.0
    started = int(now) - 86400  # 1 day in
    db = _StubUsersDB(plan=PlanType.basic, trial_started_at=started)
    _patch_world(monkeypatch, users_db=db, now=now)

    assert _is_trial_expired_uncached("uid-mid") is False


def test_paywall_gate_returns_false_for_paid_plan_regardless_of_timestamp(monkeypatch):
    now = 2_000_000_000.0
    started = int(now) - TRIAL_LENGTH_SECONDS - 86400
    db = _StubUsersDB(plan=PlanType.operator, trial_started_at=started)
    _patch_world(monkeypatch, users_db=db, now=now)

    assert _is_trial_expired_uncached("uid-paid") is False
