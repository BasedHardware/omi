"""jsonb codec: Firestore-native values survive a round trip; foreign types are refused."""

from datetime import datetime, timedelta, timezone

import pytest

from database.jobstore import codec


def test_round_trip_keeps_datetimes_offsets_bytes_and_plain_json():
    doc = {
        'a': datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone(timedelta(hours=-7))),
        'b': [b'\x00\xff', {'c': 1.0, 'd': 2, 'e': None, 'f': True}],
        'naive': datetime(2026, 1, 2, 3, 4, 5),
    }
    assert codec.loads(codec.dumps(doc)) == doc


def test_unknown_types_are_refused_not_stringified():
    with pytest.raises(TypeError):
        codec.dumps({'x': {1, 2}})
