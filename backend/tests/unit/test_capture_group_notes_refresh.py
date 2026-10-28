"""The capture-group primary notes refresh: once per revision, fenced, best effort.

The refresh is the (b) half of the design: the primary stays the longest window,
and its notes are regenerated with the members' meeting context when grouping
delivered that context after the primary was already summarized. These tests pin
the claim/idempotency fencing and the never-fail contract.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from utils.conversations import capture_group_notes_refresh as refresh
from utils.conversations.processing_trigger import ProcessingTrigger

T0 = datetime(2026, 10, 28, 4, 43, tzinfo=timezone.utc)
UID = 'capture-group-notes-user'

GROUP = {
    'id': 'group-1',
    'primary_id': 'pendant',
    'revision': 3,
    'members': [
        {'id': 'pendant', 'source': 'omi'},
        {'id': 'half-b', 'source': 'desktop'},
    ],
}

MEMBER_CONTEXT = {
    'calendar_event_id': 'evt-1',
    'title': 'Weekly sync',
    'participants': [{'name': 'Nik Shevchenko'}],
    'start_time': T0.isoformat(),
    'duration_minutes': 30,
    'calendar_source': 'system_calendar',
}


def store_row(cid, *, group=None, context=None, **extra):
    row = {
        'id': cid,
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'language': 'en',
        'capture_group': group,
        'external_data': {'calendar_meeting_context': context} if context else {},
    }
    row.update(extra)
    return row


@pytest.fixture
def store(monkeypatch):
    """Dict-backed reads plus a controllable attention claim; records every call."""
    rows: dict[str, dict] = {}
    calls = {'claim': None, 'owns': None, 'finish': None, 'processed': None}
    monkeypatch.delenv('CAPTURE_GROUP_PRIMARY_NOTES_REFRESH_ENABLED', raising=False)

    def raw_snapshot(uid, cid, field_paths=None, firestore_client=None):
        return rows.get(cid)

    monkeypatch.setattr(refresh.conversations_db, 'get_conversation_raw_snapshot', raw_snapshot)
    monkeypatch.setattr(refresh.conversations_db, 'get_conversation', lambda uid, cid, **kw: rows.get(cid))
    monkeypatch.setattr(refresh, 'deserialize_conversation', lambda row: SimpleNamespace(language=row.get('language')))

    def claim(uid, cid, attention_id=None, expected_generation=None, idempotency_key=None, restart_succeeded=False):
        calls['claim'] = (uid, cid, idempotency_key, restart_succeeded)
        return ({'operation_id': 'op-1', 'conversation_id': cid, 'claim_id': 'c', 'generation': 'g'}, True)

    monkeypatch.setattr(refresh.attention_db, 'claim', claim)

    def owns(uid, op):
        calls['owns'] = True
        return True

    monkeypatch.setattr(refresh.attention_db, 'owns_live_claim', owns)

    def finish(uid, op, state, attention_id=None):
        calls['finish'] = state

    monkeypatch.setattr(refresh.attention_db, 'finish', finish)

    def process(uid, language, conversation, **kwargs):
        calls['processed'] = (uid, language, kwargs.get('trigger'))
        kwargs['persistence_observer'](True)
        return conversation

    monkeypatch.setattr(refresh, 'process_conversation', process)
    return SimpleNamespace(rows=rows, calls=calls)


def test_refreshes_primary_once_per_group_revision(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=None)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is True
    assert store.calls['claim'] == (UID, 'pendant', 'capture-group-notes:group-1:3', True)
    assert store.calls['processed'] == (UID, 'en', ProcessingTrigger.CAPTURE_GROUP)
    assert store.calls['finish'] == 'succeeded'


def test_refresh_targets_the_primary_when_a_member_finalized(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=None)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'half-b') is True
    assert store.calls['claim'][1] == 'pendant'
    assert store.calls['processed'][0:1] == (UID,)


def test_no_refresh_without_a_group_or_without_member_context(store):
    store.rows['solo'] = store_row('solo')
    assert refresh.refresh_primary_notes(UID, 'solo') is False
    assert store.calls['claim'] is None
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] is None


def test_no_refresh_once_the_primary_stores_the_member_context(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=MEMBER_CONTEXT)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] is None


def test_kill_switch_disables_the_refresh(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_GROUP_PRIMARY_NOTES_REFRESH_ENABLED', 'off')
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] is None


def test_discarded_deleted_or_unfinished_primaries_are_skipped(store):
    for state in ({'discarded': True}, {'deleted': True}, {'status': 'processing'}):
        store.rows['pendant'] = store_row('pendant', group=GROUP, **state)
        store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
        assert refresh.refresh_primary_notes(UID, 'pendant') is False
        assert store.calls['claim'] is None


def test_unowned_or_rejected_claims_never_process(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    monkeypatch.setattr(
        refresh.attention_db,
        'claim',
        lambda *a, **kw: ({'operation_id': 'op-x'}, False),
    )
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['processed'] is None and store.calls['finish'] is None

    def rejected(*a, **kw):
        raise refresh.attention_db.ClaimRejected('not_retryable')

    monkeypatch.setattr(refresh.attention_db, 'claim', rejected)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['processed'] is None


def test_a_failed_refresh_marks_the_attempt_failed_and_never_raises(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)

    def explode(uid, language, conversation, **kwargs):
        raise RuntimeError('llm down')

    monkeypatch.setattr(refresh, 'process_conversation', explode)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['finish'] == 'failed'


def test_a_fenced_persistence_marks_the_attempt_failed(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)

    def fenced(uid, language, conversation, **kwargs):
        kwargs['persistence_observer'](False)
        return conversation

    monkeypatch.setattr(refresh, 'process_conversation', fenced)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['finish'] == 'failed'


def test_read_failures_never_raise(store, monkeypatch):
    def explode(uid, cid, field_paths=None, firestore_client=None):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(refresh.conversations_db, 'get_conversation_raw_snapshot', explode)
    assert refresh.refresh_primary_notes(UID, 'anything') is False
    assert store.calls['claim'] is None
