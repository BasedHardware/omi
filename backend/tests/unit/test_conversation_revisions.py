from datetime import datetime, timezone
import math
import pytest

from database.conversation_revisions import ensure_timezone_aware, firestore_revision_datetime


class MockProtoTimestamp:
    def __init__(self, seconds, nanos):
        self.seconds = seconds
        self.nanos = nanos


class MockFirestoreDatetimeObj:
    def __init__(self, dt_val):
        self._dt = dt_val

    def ToDatetime(self, tzinfo=None):
        if tzinfo and self._dt.tzinfo is None:
            return self._dt.replace(tzinfo=tzinfo)
        return self._dt


class MockBrokenDatetimeObj:
    def ToDatetime(self, tzinfo=None):
        raise OverflowError('Timestamp overflow in protobuf')


def test_ensure_timezone_aware_naive():
    dt_naive = datetime(2026, 10, 1, 12, 0, 0)
    aware = ensure_timezone_aware(dt_naive)
    assert aware.tzinfo == timezone.utc
    assert aware.year == 2026


def test_ensure_timezone_aware_already_aware():
    dt_aware = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    res = ensure_timezone_aware(dt_aware)
    assert res is dt_aware


def test_firestore_revision_datetime_from_datetime():
    dt_naive = datetime(2026, 5, 10, 8, 30, 0)
    res = firestore_revision_datetime(dt_naive)
    assert res.tzinfo == timezone.utc

    dt_aware = datetime(2026, 5, 10, 8, 30, 0, tzinfo=timezone.utc)
    res = firestore_revision_datetime(dt_aware)
    assert res == dt_aware


def test_firestore_revision_datetime_from_todatetime():
    mock_obj = MockFirestoreDatetimeObj(datetime(2026, 1, 1, 0, 0, 0))
    res = firestore_revision_datetime(mock_obj)
    assert res == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    mock_broken = MockBrokenDatetimeObj()
    assert firestore_revision_datetime(mock_broken) is None


def test_firestore_revision_datetime_from_seconds_nanos():
    ts = MockProtoTimestamp(1770000000, 500000000)
    res = firestore_revision_datetime(ts)
    assert res == datetime.fromtimestamp(1770000000.5, tz=timezone.utc)


def test_firestore_revision_datetime_string_seconds_nanos():
    ts = MockProtoTimestamp('1770000000', '500000000')
    res = firestore_revision_datetime(ts)
    assert res is not None


def test_firestore_revision_datetime_invalid_inputs_return_none():
    assert firestore_revision_datetime(None) is None
    assert firestore_revision_datetime('not a timestamp') is None
    assert firestore_revision_datetime(123456) is None
    assert firestore_revision_datetime(MockProtoTimestamp(float('nan'), 0)) is None
    assert firestore_revision_datetime(MockProtoTimestamp(0, float('nan'))) is None
    assert firestore_revision_datetime(MockProtoTimestamp(float('inf'), 0)) is None
    assert firestore_revision_datetime(MockProtoTimestamp(10**18, 0)) is None
