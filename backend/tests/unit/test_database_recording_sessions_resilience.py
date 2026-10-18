"""#19111 — identifier validation, whitespace coercion, NotFound swallow, and
partial-document resilience for recording_sessions.

A whitespace uid or session id used to reach Firestore's document() and raise
`A document id must not be empty` (or build a path under '   '); a partial
session doc missing conversation_id raised a bare KeyError; a concurrent purge
of the conversation raised NotFound instead of returning False.
"""

import sys
from unittest.mock import MagicMock

sys.path.insert(
    0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__file__)))
)

import pytest
from google.api_core.exceptions import NotFound

import database.recording_sessions as rs

BAD_IDS = ['', '   ', '\t\n', None, 42]


class _Snap:
    def __init__(self, exists=True, data=None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return self._data


class _Doc:
    def __init__(self, snap=None, txn_gets=None):
        self._snap = snap or _Snap(False)
        self._txn_gets = txn_gets or []

    def get(self, transaction=None):
        return self._txn_gets.pop(0) if self._txn_gets else self._snap

    def collection(self, name):
        return _Collection(self)


class _Collection:
    def __init__(self, doc):
        self._doc = doc

    def document(self, _id=None):
        return self._doc


class _Client:
    def __init__(self, doc, txn=None):
        self._doc = doc

    def collection(self, name):
        return _Collection(self._doc)

    def transaction(self):
        return MagicMock()


# --- identifier validation ---


def test_create_or_get_rejects_bad_identifiers():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            rs.create_or_get_recording_session(bad, 'sess-1', 'conv-1')
        with pytest.raises(ValueError):
            rs.create_or_get_recording_session('u', bad, 'conv-1')
        with pytest.raises(ValueError):
            rs.create_or_get_recording_session('u', 'sess-1', bad)


def test_get_recording_session_rejects_bad_identifiers():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            rs.get_recording_session(bad, 'sess-1', firestore_client=MagicMock())
        with pytest.raises(ValueError):
            rs.get_recording_session('u', bad, firestore_client=MagicMock())


def test_record_lifecycle_event_rejects_bad_identifiers():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            rs.record_lifecycle_event(bad, 's', 'c', 'processing')
        with pytest.raises(ValueError):
            rs.record_lifecycle_event('u', bad, 'c', 'processing')
        with pytest.raises(ValueError):
            rs.record_lifecycle_event('u', 's', bad, 'processing')


def test_whitespace_session_id_coerces_to_none_in_tombstone():
    # '   ' must not reach _session_ref — it becomes None and only the
    # conversation path is built.
    conv_doc = _Doc(snap=_Snap(True, {'status': 'in_progress'}))
    client = _Client(conv_doc)
    built = []
    real_session_ref = rs._session_ref
    rs._session_ref = lambda *a, **k: (built.append(a) or real_session_ref(*a, **k))
    try:
        rs.tombstone_and_delete_empty_conversation('u', 'conv-1', '   ', firestore_client=client)
    finally:
        rs._session_ref = real_session_ref
    assert built == []


def test_tombstone_rejects_bad_uid_and_conversation():
    for bad in BAD_IDS:
        with pytest.raises(ValueError):
            rs.tombstone_and_delete_empty_conversation(bad, 'conv-1', None)
        with pytest.raises(ValueError):
            rs.tombstone_and_delete_empty_conversation('u', bad, None)


# --- concurrent-delete NotFound ---


def test_tombstone_swallows_notfound_from_concurrent_purge():
    class _DeadTxn:
        def get(self, *a, **k):
            raise NotFound('row purged mid-transaction')

    class _TxnFactory:
        def transaction(self):
            return _DeadTxn()

    class _Client2:
        def collection(self, name):
            return _Collection(_Doc())

        def transaction(self):
            raise NotFound('gone')

    # NotFound raised before the txn body runs
    assert rs.tombstone_and_delete_empty_conversation('u', 'conv-1', None, firestore_client=_Client2()) is False


# --- partial document ---


def test_binding_defaults_missing_conversation_id():
    binding = rs._binding({'lifecycle_phase': 'processing'}, 'sess-1', mapping_conflict=False)
    assert binding['conversation_id'] == ''
    assert binding['lifecycle_phase'] == 'processing'


# --- happy path preserved ---


def test_whitespace_get_still_validates_then_reads():
    doc = _Doc(snap=_Snap(True, {'uid': 'u', 'recording_session_id': 's-1', 'conversation_id': 'c-1'}))
    out = rs.get_recording_session(' u ', ' s-1 ', firestore_client=_Client(doc))
    assert out['conversation_id'] == 'c-1'
