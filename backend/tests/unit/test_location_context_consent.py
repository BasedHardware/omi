"""Server-owned authorization for city-only chat context (migrated to the WP2 storage port)."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import users as users_db
from models.users import (
    LOCATION_CONTEXT_DISCLOSED_PROVIDERS,
    LOCATION_CONTEXT_PURPOSE,
    LocationContextConsent,
    LocationContextConsentStatus,
)
from tests.store_fakes import FakeDocumentStore


def _store_with_consent(payload):
    store = FakeDocumentStore()
    store.set('users/uid1', {'location_context_consent': payload})
    return store


def _valid_consent(now):
    return LocationContextConsent(
        status=LocationContextConsentStatus.granted,
        purpose=LOCATION_CONTEXT_PURPOSE,
        disclosed_providers=LOCATION_CONTEXT_DISCLOSED_PROVIDERS,
        granted_at=now,
        expires_at=now + timedelta(days=1),
    )


def test_consent_reader_rejects_malformed_or_unexpected_provider_disclosures(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(users_db, '_store', lambda: _store_with_consent({'status': 'granted'}))
    assert users_db.get_user_location_context_consent('uid1') is None

    wrong_provider = _valid_consent(now).model_copy(update={'disclosed_providers': ('Google Maps', 'unknown')})
    monkeypatch.setattr(users_db, '_store', lambda: _store_with_consent(wrong_provider.model_dump()))
    parsed = users_db.get_user_location_context_consent('uid1')
    assert parsed is not None
    assert parsed.is_active(now) is False


def test_revocation_persists_before_best_effort_coordinate_cache_deletion(monkeypatch):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    store = FakeDocumentStore()
    monkeypatch.setattr(users_db, '_store', lambda: store)
    with patch.object(users_db, 'delete_cached_user_geolocation') as delete_cached:
        consent = users_db.set_user_location_context_consent('uid1', enabled=False, now=now)

    assert consent.status is LocationContextConsentStatus.revoked
    assert consent.is_active(now) is False
    assert store.get('users/uid1').to_dict()['location_context_consent'] == consent.model_dump()
    delete_cached.assert_called_once_with('uid1')


def test_grant_is_server_timestamped_and_expires_after_the_fixed_consent_window(monkeypatch):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    store = FakeDocumentStore()
    monkeypatch.setattr(users_db, '_store', lambda: store)
    consent = users_db.set_user_location_context_consent('uid1', enabled=True, now=now)

    assert consent.is_active(now)
    assert consent.expires_at == now + users_db.LOCATION_CONTEXT_CONSENT_TTL
