"""database.goals goal-history documents were keyed by UTC's calendar day, not the user's own.

``_append_goal_progress_event`` and ``save_goal_progress_history`` both wrote/merged
``goal_history/{date}`` with ``date = datetime.now(timezone.utc).strftime('%Y-%m-%d')``. A
user west of UTC (e.g. US Pacific, UTC-7/8) whose local evening hasn't yet crossed UTC
midnight has their progress update written into *tomorrow's* UTC-dated document; a user
east of UTC can have it land in *yesterday's*. Either way, ``GET /v1/goals/{id}/history``
(``database.goals.get_goal_history``, ordered by the ``date`` field) returns a chart whose
day boundaries don't match the user's own calendar — the same bug class already fixed for
the proactive-notification daily cap via ``resolve_user_timezone``.

``_history_date_str`` reads ``time_zone`` itself through ``_get_db(firestore_client)``
(the same client-injection seam every other read in this module uses) rather than calling
``database.notifications.resolve_user_timezone``, which has no such seam and always hit the
real Firestore client — invisible here (this file injects a fake client throughout) but it
broke ``tests/unit/test_workstream_core.py``'s hermetic goal tests, which exercise
``goals.py`` through their own ``fake_db`` and have no reason to know ``database.goals``
reached into a different module's unmocked client.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timezone

import database.goals as goals


def _client_with_time_zone(tz: str | None):
    """A fake Firestore client whose users/{uid} doc has (or lacks) a time_zone field."""
    client = MagicMock()
    snapshot = client.collection.return_value.document.return_value.get.return_value
    if tz is None:
        snapshot.exists = False
        snapshot.to_dict.return_value = None
    else:
        snapshot.exists = True
        snapshot.to_dict.return_value = {'time_zone': tz}
    return client


def test_history_date_str_uses_the_users_local_day_not_utcs():
    # 2026-09-21 02:30 UTC is still 2026-09-20 evening in Los Angeles (UTC-7).
    client = _client_with_time_zone('America/Los_Angeles')
    now = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)
    assert goals._history_date_str('u1', now, firestore_client=client) == '2026-09-20'


def test_history_date_str_uses_the_users_local_day_east_of_utc():
    # 2026-09-20 23:30 UTC is already 2026-09-21 morning in Tokyo (UTC+9).
    client = _client_with_time_zone('Asia/Tokyo')
    now = datetime(2026, 9, 20, 23, 30, tzinfo=timezone.utc)
    assert goals._history_date_str('u1', now, firestore_client=client) == '2026-09-21'


def test_history_date_str_falls_back_to_utc_for_an_unresolvable_zone():
    client = _client_with_time_zone('not-a-real-zone')
    now = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)
    assert goals._history_date_str('u1', now, firestore_client=client) == '2026-09-21'


def test_history_date_str_falls_back_to_utc_when_the_user_has_no_time_zone_on_file():
    client = _client_with_time_zone(None)
    now = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)
    assert goals._history_date_str('u1', now, firestore_client=client) == '2026-09-21'


def test_history_date_str_falls_back_to_utc_when_the_read_itself_fails():
    client = MagicMock()
    client.collection.return_value.document.return_value.get.side_effect = RuntimeError('boom')
    now = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)
    assert goals._history_date_str('u1', now, firestore_client=client) == '2026-09-21'


def test_save_goal_progress_history_writes_the_users_local_date(monkeypatch):
    """The document id and the stored `date` field must both be the local day, not UTC's."""
    fixed_now = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(goals, 'datetime', _FixedDatetime)

    client = _client_with_time_zone('America/Los_Angeles')
    goal_doc_ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    history_collection = goal_doc_ref.collection.return_value

    goals.save_goal_progress_history('u1', 'g1', 42.0, firestore_client=client)

    history_collection.document.assert_called_once_with('2026-09-20')
    written_doc = history_collection.document.return_value
    written_doc.set.assert_called_once_with({'date': '2026-09-20', 'value': 42.0, 'recorded_at': fixed_now}, merge=True)
