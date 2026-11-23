"""Validate the natural key before accessing Firestore."""

import pytest

import database.calendar_meetings as meetings_db


@pytest.mark.parametrize(
    ('payload', 'missing_field'),
    [
        ({'calendar_event_id': 'e1'}, 'calendar_source'),
        ({'calendar_source': 'google'}, 'calendar_event_id'),
    ],
)
def test_missing_natural_key_raises_valueerror(payload, missing_field):
    with pytest.raises(ValueError, match=missing_field):
        meetings_db.create_meeting('u1', payload)
