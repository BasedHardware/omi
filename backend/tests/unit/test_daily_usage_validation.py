"""#19955 — upsert_desktop_daily_usage input validation + counter KeyError.

Before the fix an empty uid/date/device id built a malformed document path,
and a counters dict missing any counter field raised KeyError. Counters now
read with defaults and non-int values (incl. bools) sanitize to 0.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

import database.daily_summaries as daily_summaries_db

COUNTER_FIELDS = daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS


def _fake_db(existing=None):
    written = []
    usage_ref = MagicMock()
    usage_ref.get.return_value = SimpleNamespace(
        exists=existing is not None,
        to_dict=lambda: dict(existing or {}),
    )
    txn = MagicMock()
    txn.set.side_effect = lambda ref, payload: written.append(payload)
    user_ref = MagicMock()
    user_ref.collection.return_value.document.return_value = usage_ref
    db = MagicMock()
    db.collection.return_value.document.return_value = user_ref
    db.transaction.return_value = txn
    return db, written


def test_rejects_empty_uid():
    db, _ = _fake_db()
    daily_summaries_db.db = db
    for bad in ('', '  ', None, 42):
        with pytest.raises(ValueError):
            daily_summaries_db.upsert_desktop_daily_usage(bad, '2026-10-14', 'UTC', 'dev1', {})


def test_rejects_missing_date_or_device():
    db, _ = _fake_db()
    daily_summaries_db.db = db
    for date, dev in (('', 'd1'), (None, 'd1'), ('2026-10-14', ''), ('2026-10-14', None)):
        with pytest.raises(ValueError):
            daily_summaries_db.upsert_desktop_daily_usage('u1', date, 'UTC', dev, {'watching_seconds': 5})


def test_missing_counter_field_defaults_zero_no_keyerror():
    db, written = _fake_db()
    daily_summaries_db.db = db
    daily_summaries_db.upsert_desktop_daily_usage('u1', '2026-10-14', 'UTC', 'dev1', {'watching_seconds': 12})
    payload = written[0]
    assert payload['watching_seconds'] == 12
    for f in COUNTER_FIELDS:
        assert f in payload  # every counter key is written — no KeyError


def test_none_counters_treated_as_empty():
    db, written = _fake_db()
    daily_summaries_db.db = db
    daily_summaries_db.upsert_desktop_daily_usage('u1', '2026-10-14', 'UTC', 'dev1', None)
    assert all(written[0][f] == 0 for f in COUNTER_FIELDS)


def test_merge_by_max_and_type_guards():
    existing = {f: 10 for f in COUNTER_FIELDS}
    existing['watching_seconds'] = 'corrupt'  # non-int stored value sanitizes to 0
    db, written = _fake_db(existing)
    daily_summaries_db.db = db
    counters = {f: 3 for f in COUNTER_FIELDS}
    counters['listening_seconds'] = 99  # incoming wins
    counters['ptt_turns'] = True  # bool is not a valid int counter
    daily_summaries_db.upsert_desktop_daily_usage('u1', '2026-10-14', 'UTC', 'dev1', counters)
    payload = written[0]
    assert payload['listening_seconds'] == 99
    assert payload['watching_seconds'] == 3  # corrupt stored + incoming 3 -> 3
    assert payload['ptt_turns'] == 10  # bool incoming -> 0, existing 10 wins
    assert payload['proactive_cards_shown'] == 10
