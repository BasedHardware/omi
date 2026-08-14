"""cubic PR 10887 C1: the auth-port migration made _get_user return a neutral UserProfile, but the
desktop trial paywall still read Firebase's user_metadata.creation_timestamp off it -> AttributeError,
swallowed by a broad except -> the account-age paywall silently never fired (fail-open). Assert the
neutral created_at field is populated by the adapters and read by the trial path."""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import time  # noqa: E402
from types import SimpleNamespace  # noqa: E402


def test_firebase_get_user_profile_maps_creation_timestamp_to_created_at(monkeypatch):
    import utils.auth.adapters.firebase as fb

    rec = SimpleNamespace(
        uid='u1', email='a@b.c', email_verified=True, phone_number=None, display_name='Ada',
        photo_url=None, disabled=False, provider_data=[],
        user_metadata=SimpleNamespace(creation_timestamp=1700000000000),
    )
    monkeypatch.setattr(fb, '_auth', lambda: SimpleNamespace(get_user=lambda uid: rec))
    profile = fb.FirebaseAuthProvider().get_user_profile('u1')
    assert profile.created_at == 1700000000000  # neutral epoch-ms field carries the creation time


def test_trial_expiry_reads_created_at_and_fires_for_old_accounts(monkeypatch):
    import database.users  # noqa: F401 — establish the users<->subscription import order (cycle)
    import utils.subscription as sub
    from utils.auth.ports import UserProfile

    # Reach the created_at line: an eligible free-desktop plan, not a BYOK user.
    monkeypatch.setattr(sub.users_db, 'get_user_valid_subscription', lambda uid, **k: None)
    monkeypatch.setattr(sub, 'desktop_trial_paywall_eligible', lambda plan, subscription=None: True)
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid, **k: False)

    old_ms = int((time.time() - sub.TRIAL_LENGTH_SECONDS - 100) * 1000)
    monkeypatch.setattr(sub, '_get_user', lambda uid: UserProfile(uid=uid, created_at=old_ms))
    # Before the fix this read .user_metadata -> AttributeError -> swallowed -> False (paywall disabled).
    assert sub._is_trial_expired_uncached('u1', provision=False) is True

    fresh_ms = int(time.time() * 1000)
    monkeypatch.setattr(sub, '_get_user', lambda uid: UserProfile(uid=uid, created_at=fresh_ms))
    assert sub._is_trial_expired_uncached('u1', provision=False) is False

    # No creation timestamp (backend didn't expose it) fails open to "not expired".
    monkeypatch.setattr(sub, '_get_user', lambda uid: UserProfile(uid=uid, created_at=None))
    assert sub._is_trial_expired_uncached('u1', provision=False) is False
