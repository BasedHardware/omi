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
