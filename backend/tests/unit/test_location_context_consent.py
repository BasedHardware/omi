"""Server-owned authorization for city-only chat context."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from database import users as users_db
from models.users import (
    LOCATION_CONTEXT_DISCLOSED_PROVIDERS,
    LOCATION_CONTEXT_PURPOSE,
    LocationContextConsent,
    LocationContextConsentStatus,
)


def _client_with_consent(payload):
    snapshot = MagicMock()
    snapshot.to_dict.return_value = {'location_context_consent': payload}
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value = snapshot
    return client


def _valid_consent(now):
    return LocationContextConsent(
        status=LocationContextConsentStatus.granted,
        purpose=LOCATION_CONTEXT_PURPOSE,
        disclosed_providers=LOCATION_CONTEXT_DISCLOSED_PROVIDERS,
        granted_at=now,
        expires_at=now + timedelta(days=1),
    )


def test_consent_reader_rejects_malformed_or_unexpected_provider_disclosures():
    now = datetime.now(timezone.utc)
    malformed_client = _client_with_consent({'status': 'granted'})
    assert users_db.get_user_location_context_consent('uid1', firestore_client=malformed_client) is None

    wrong_provider = _valid_consent(now).model_copy(update={'disclosed_providers': ('Google Maps', 'unknown')})
    parsed = users_db.get_user_location_context_consent(
        'uid1', firestore_client=_client_with_consent(wrong_provider.model_dump())
    )
    assert parsed is not None
    assert parsed.is_active(now) is False


def test_revocation_persists_before_best_effort_coordinate_cache_deletion():
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    client = MagicMock()
    with patch.object(users_db, 'delete_cached_user_geolocation') as delete_cached:
        consent = users_db.set_user_location_context_consent('uid1', enabled=False, now=now, firestore_client=client)

    assert consent.status is LocationContextConsentStatus.revoked
    assert consent.is_active(now) is False
    client.collection.return_value.document.return_value.set.assert_called_once_with(
        {'location_context_consent': consent.model_dump()}, merge=True
    )
    delete_cached.assert_called_once_with('uid1')


def test_grant_is_server_timestamped_and_expires_after_the_fixed_consent_window():
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    client = MagicMock()
    consent = users_db.set_user_location_context_consent('uid1', enabled=True, now=now, firestore_client=client)

    assert consent.is_active(now)
    assert consent.expires_at == now + users_db.LOCATION_CONTEXT_CONSENT_TTL
