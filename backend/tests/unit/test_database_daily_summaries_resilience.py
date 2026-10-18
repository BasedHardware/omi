"""#19122 — identifier validation, NotFound swallow, and merge=True create for
daily_summaries.

Empty/whitespace uid/summary/date used to reach document() and raise
`A document id must not be empty` (or build `__` ids); a concurrent prune
turned visibility updates + deletes into unhandled NotFound 500s; create
lacked an id check and clobbered concurrent fields via destructive set().
"""

import sys
from unittest.mock import MagicMock

sys.path.insert(
    0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__file__)))
)

import pytest
from google.api_core.exceptions import NotFound

import database.daily_summaries as ds

BAD_IDS = ['', '   ', '\t\n', None, 42]


# --- identifier validation across the public surface ---


def test_create_daily_summary_rejects_bad_uid_and_id():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            ds.create_daily_summary(bad, {'id': 's1'})
    with pytest.raises(ValueError):
        ds.create_daily_summary('u', {})
    with pytest.raises(ValueError):
        ds.create_daily_summary('u', {'id': '   '})


def test_read_paths_reject_bad_identifiers():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            ds.get_daily_summary(bad, 's1')
        with pytest.raises(ValueError):
            ds.get_daily_summary('u', bad)
        with pytest.raises(ValueError):
            ds.get_daily_summary_by_date(bad, '2026-10-18')
        with pytest.raises(ValueError):
            ds.get_daily_summary_by_date('u', bad)
        with pytest.raises(ValueError):
            ds.get_daily_summaries(bad)
        with pytest.raises(ValueError):
            ds.get_summaries_count(bad)
        with pytest.raises(ValueError):
            ds.get_desktop_daily_usage(bad, '2026-10-18')
        with pytest.raises(ValueError):
            ds.get_desktop_daily_usage('u', bad)


def test_mutation_paths_reject_bad_identifiers():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            ds.update_daily_summary(bad, 's1', {'id': 's1'})
        with pytest.raises(ValueError):
            ds.update_daily_summary('u', bad, {'id': 'x'})
        with pytest.raises(ValueError):
            ds.delete_daily_summary(bad, 's1')
        with pytest.raises(ValueError):
            ds.delete_daily_summary('u', bad)
        with pytest.raises(ValueError):
            ds.set_daily_summary_visibility(bad, 's1', 'private')
        with pytest.raises(ValueError):
            ds.set_daily_summary_visibility('u', bad, 'private')
        with pytest.raises(ValueError):
            ds.mark_daily_summary_delivery_completed(bad, 's1')
        with pytest.raises(ValueError):
            ds.mark_daily_summary_delivery_completed('u', bad)


# --- NotFound swallow on concurrent prune ---


def test_set_visibility_returns_false_on_concurrent_delete(monkeypatch):
    doc = MagicMock()
    doc.update.side_effect = NotFound('pruned')
    coll = MagicMock()
    coll.document.return_value = doc
    users = MagicMock()
    users.document.return_value = MagicMock(collection=lambda n: coll)
    monkeypatch.setattr(ds, 'db', MagicMock(collection=lambda n: users))
    assert ds.set_daily_summary_visibility('u', 's1', 'private') is False


def test_delete_returns_false_on_concurrent_prune(monkeypatch):
    doc = MagicMock()
    doc.delete.side_effect = NotFound('pruned')
    coll = MagicMock()
    coll.document.return_value = doc
    users = MagicMock()
    users.document.return_value = MagicMock(collection=lambda n: coll)
    monkeypatch.setattr(ds, 'db', MagicMock(collection=lambda n: users))
    assert ds.delete_daily_summary('u', 's1') is False


def test_set_visibility_returns_true_on_success(monkeypatch):
    doc = MagicMock()
    coll = MagicMock()
    coll.document.return_value = doc
    users = MagicMock()
    users.document.return_value = MagicMock(collection=lambda n: coll)
    monkeypatch.setattr(ds, 'db', MagicMock(collection=lambda n: users))
    assert ds.set_daily_summary_visibility('u', 's1', 'private') is True


# --- create merges instead of clobbering ---


def test_create_merges_and_validates_id(monkeypatch):
    doc = MagicMock()
    coll = MagicMock()
    coll.document.return_value = doc
    users = MagicMock()
    users.document.return_value = MagicMock(collection=lambda n: coll)
    monkeypatch.setattr(ds, 'db', MagicMock(collection=lambda n: users))
    out = ds.create_daily_summary('u', {'id': '  s1 ', 'headline': 'h'})
    assert out == '  s1 '  # id passed through (stripped for the doc path)
    coll.document.assert_called_once_with('s1')
    doc.set.assert_called_once_with({'id': '  s1 ', 'headline': 'h'}, merge=True)


# --- upsert_desktop_daily_usage: identifiers + counter tolerance ---


def test_upsert_desktop_daily_usage_rejects_bad_identifiers():
    base = dict(uid='u', date='2026-10-18', timezone_name='UTC', client_device_id='dev1', counters={})
    for bad in BAD_IDS:
        for field in ('uid', 'date', 'client_device_id'):
            args = dict(base)
            args[field] = bad
            with pytest.raises(ValueError):
                ds.upsert_desktop_daily_usage(**args)


def _upsert_harness(monkeypatch, existing=None):
    usage_ref = MagicMock()
    coll = MagicMock()
    coll.document.return_value = usage_ref
    users = MagicMock()
    users.document.return_value = MagicMock(collection=lambda n: coll)
    txn = MagicMock()
    fake_db = MagicMock(collection=lambda n: users)
    fake_db.transaction = lambda: txn
    monkeypatch.setattr(ds, 'db', fake_db)
    # Run the transactional body inline instead of through the retry wrapper.
    monkeypatch.setattr(ds.firestore, 'transactional', lambda fn: (lambda write_txn: fn(write_txn)))
    snap = MagicMock()
    snap.exists = existing is not None
    snap.to_dict.return_value = existing or {}
    usage_ref.get.return_value = snap
    return usage_ref, coll, txn


def test_upsert_strips_whitespace_ids_into_composite_doc_id(monkeypatch):
    usage_ref, coll, txn = _upsert_harness(monkeypatch)
    ds.upsert_desktop_daily_usage(' u ', ' 2026-10-18 ', 'UTC', ' dev1 ', {})
    coll.document.assert_called_once_with('2026-10-18__dev1')


def test_upsert_partial_and_non_int_counters_never_crash(monkeypatch):
    # Stored doc carries a poisoned non-int field; the update reports only a
    # subset of counters with a None — old code raised KeyError/TypeError.
    usage_ref, coll, txn = _upsert_harness(monkeypatch, existing={'watching_seconds': 'bad', 'listening_seconds': 5})
    ds.upsert_desktop_daily_usage('u', '2026-10-18', 'UTC', 'dev1', {'watching_seconds': 3})
    payload = txn.set.call_args[0][1]
    assert payload['watching_seconds'] == 3  # 'bad' prior reads as 0 → max(0, 3)
    assert payload['listening_seconds'] == 5  # missing counter keeps prior max
    assert payload['proactive_cards_shown'] == 0
    assert payload['ptt_turns'] == 0
    assert payload['client_device_id'] == 'dev1'

    ds.upsert_desktop_daily_usage('u', '2026-10-18', 'UTC', 'dev1', {'watching_seconds': None})
    ds.upsert_desktop_daily_usage('u', '2026-10-18', 'UTC', 'dev1', None)
