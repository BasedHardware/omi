"""The timezone a client may store is the timezone the scheduler can use.

The daily-summary cron selects recipients from ``pytz.all_timezones`` and every reader
resolves zones with ``pytz``, but the validators accepted anything ``ZoneInfo`` knew.
``ZoneInfo`` reads the host's newer tz database (``America/Coyhaique``, ``Factory``), so a
device could store a zone the cron never selects and the recap routes could not resolve.
"""

from unittest.mock import MagicMock

import pytest
import pytz

import database.notifications as notifications_module
from models.other import SyncUserTimeZoneRequest

ZONEINFO_ONLY = 'America/Coyhaique'  # added to the tz database after pytz 2024.1


@pytest.fixture
def pytz_rejects_zoneinfo_only(monkeypatch):
    """Pin pytz's verdict for the zone regardless of the host tz database."""
    real = pytz.timezone

    def timezone(name):
        if name == ZONEINFO_ONLY:
            raise pytz.UnknownTimeZoneError(name)
        return real(name)

    monkeypatch.setattr(pytz, 'timezone', timezone)


def test_validator_follows_pytz_not_zoneinfo(pytz_rejects_zoneinfo_only):
    assert SyncUserTimeZoneRequest(time_zone=' Asia/Kolkata ').time_zone == 'Asia/Kolkata'
    # pytz knows the lowercase alias ZoneInfo rejects; the scheduler can use it.
    assert SyncUserTimeZoneRequest(time_zone='utc').time_zone == 'utc'
    with pytest.raises(ValueError):
        SyncUserTimeZoneRequest(time_zone=ZONEINFO_ONLY)
    with pytest.raises(ValueError):
        SyncUserTimeZoneRequest(time_zone='Not/A/Timezone')


def test_is_schedulable_time_zone(pytz_rejects_zoneinfo_only):
    assert notifications_module.is_schedulable_time_zone('Asia/Kolkata')
    assert not notifications_module.is_schedulable_time_zone(ZONEINFO_ONLY)
    assert not notifications_module.is_schedulable_time_zone(None)
    assert not notifications_module.is_schedulable_time_zone('')


def test_resolve_user_timezone_falls_back_to_utc_for_a_zone_the_scheduler_cannot_use(
    monkeypatch, pytz_rejects_zoneinfo_only
):
    monkeypatch.setattr(notifications_module, 'get_user_time_zone', lambda uid: ZONEINFO_ONLY)
    assert notifications_module.resolve_user_timezone('u1') == 'UTC'
    monkeypatch.setattr(notifications_module, 'get_user_time_zone', lambda uid: 'Asia/Kolkata')
    assert notifications_module.resolve_user_timezone('u1') == 'Asia/Kolkata'


def test_sync_from_client_ignores_a_zone_the_scheduler_cannot_use(monkeypatch, pytz_rejects_zoneinfo_only):
    monkeypatch.setattr(notifications_module, 'get_user_time_zone', lambda uid: 'Asia/Kolkata')
    set_tz = MagicMock()
    monkeypatch.setattr(notifications_module, 'set_user_time_zone', set_tz)

    assert notifications_module.sync_user_time_zone_from_client('u1', ZONEINFO_ONLY) == 'Asia/Kolkata'

    set_tz.assert_not_called()


def test_token_registration_does_not_schedule_a_zone_the_scheduler_cannot_use(monkeypatch, pytz_rejects_zoneinfo_only):
    store = MagicMock()
    user = store.collection.return_value.document.return_value
    user.get.return_value.exists = False
    user.collection.return_value.document.return_value.get.return_value.exists = False
    schedule = MagicMock()
    monkeypatch.setattr(notifications_module, '_update_summary_schedule', schedule)

    notifications_module.save_token(
        'uid1', {'device_key': 'd', 'fcm_token': 'not-a-real-token', 'time_zone': ZONEINFO_ONLY}, firestore_client=store
    )

    schedule.assert_called_once_with('uid1', {}, firestore_client=store)
