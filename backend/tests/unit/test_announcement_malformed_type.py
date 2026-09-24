"""Announcement.from_dict must tolerate a missing/invalid type instead of raising.

The public announcement list endpoints (/v1/announcements/changelogs, /features, /general) build
Announcement.from_dict(doc) per record in database/announcements.py. from_dict did
AnnouncementType(data.get("type")), so one malformed/legacy announcement with a null or out-of-enum
type raised ValueError and 500'd the whole public list. It now falls back to the generic type.
"""

import os
from datetime import datetime, timezone

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.announcement import Announcement, AnnouncementType  # noqa: E402

_BASE = {'id': 'a1', 'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc)}


def test_bad_type_falls_back_not_raises():
    a = Announcement.from_dict({**_BASE, 'type': 'bogus_type'})
    assert a.type == AnnouncementType.ANNOUNCEMENT


def test_none_type_falls_back():
    a = Announcement.from_dict({**_BASE, 'type': None})
    assert a.type == AnnouncementType.ANNOUNCEMENT


def test_valid_types_preserved():
    for raw, expected in [
        ('changelog', AnnouncementType.CHANGELOG),
        ('feature', AnnouncementType.FEATURE),
        ('announcement', AnnouncementType.ANNOUNCEMENT),
    ]:
        a = Announcement.from_dict({**_BASE, 'type': raw})
        assert a.type == expected


# id and created_at are also required with no default; a legacy doc missing them used to raise
# ValidationError and 500 the whole list, defeating the same tolerance goal stated for type.


def test_missing_created_at_falls_back_not_raises():
    a = Announcement.from_dict({'id': 'a1', 'type': 'announcement'})  # no created_at
    assert a.created_at == datetime.fromtimestamp(0, tz=timezone.utc)


def test_none_created_at_falls_back():
    a = Announcement.from_dict({'id': 'a1', 'type': 'announcement', 'created_at': None})
    assert a.created_at == datetime.fromtimestamp(0, tz=timezone.utc)


def test_missing_id_falls_back_not_raises():
    a = Announcement.from_dict({'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc), 'type': 'announcement'})
    assert a.id == ''


def test_valid_id_and_created_at_preserved():
    ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    a = Announcement.from_dict({'id': 'keep', 'created_at': ts, 'type': 'announcement'})
    assert a.id == 'keep' and a.created_at == ts


def test_naive_and_malformed_datetimes_normalized_to_utc():
    naive_created = datetime(2026, 6, 1, 12, 0, 0)
    naive_expires = datetime(2026, 7, 1, 12, 0, 0)
    a = Announcement.from_dict(
        {
            'id': 'a-naive',
            'created_at': naive_created,
            'expires_at': naive_expires,
            'display': {'start_at': datetime(2026, 5, 1, 8, 0, 0), 'expires_at': '2026-08-01T00:00:00'},
        }
    )
    assert a.created_at == datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert a.expires_at == datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert a.display is not None
    assert a.display.start_at == datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
    assert a.display.expires_at == datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)

    malformed = Announcement.from_dict({'id': 'a-bad-dt', 'created_at': 'not-a-date', 'expires_at': 'not-a-date'})
    assert malformed.created_at == datetime.fromtimestamp(0, tz=timezone.utc)
    assert malformed.expires_at is None


def test_null_active_and_null_content_fall_back_instead_of_raising():
    a = Announcement.from_dict(
        {
            'id': 'a-nulls',
            'active': None,
            'content': None,
            'device_models': ['Omi DevKit 2', None],
        }
    )
    assert a.active is True
    assert a.content == {}
    assert a.device_models == ['Omi DevKit 2']
