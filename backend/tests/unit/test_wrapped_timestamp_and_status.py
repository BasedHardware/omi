import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import database.wrapped as wrapped_db

with patch.dict(sys.modules, {'utils.wrapped.generate_2025': MagicMock()}):
    import routers.wrapped as wrapped_router


class _FakeFirestoreTimestamp:
    def __init__(self, epoch: float):
        self._epoch = epoch

    def timestamp(self) -> float:
        return self._epoch


def test_coerce_timestamp_anchors_naive_datetime_to_utc():
    naive = datetime(2026, 1, 15, 12, 30, 0)
    coerced = wrapped_db._coerce_timestamp(naive)
    assert coerced == datetime(2026, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
    assert coerced.tzinfo == timezone.utc

    fake_ts = _FakeFirestoreTimestamp(1768480200.0)
    assert wrapped_db._coerce_timestamp(fake_ts) == datetime.fromtimestamp(1768480200.0, tz=timezone.utc)


def test_get_wrapped_status_falls_back_when_status_is_none():
    with patch.object(wrapped_router.wrapped_db, 'get_wrapped', return_value={'status': None, 'year': 2025}):
        resp = wrapped_router.get_wrapped_status(year=2025, uid='user-1')
    assert resp.status == wrapped_db.WrappedStatus.NOT_GENERATED
    assert resp.year == 2025
