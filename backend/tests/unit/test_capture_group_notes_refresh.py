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
        {'id': 'pendant', 'source': 'omi', 'evidence': {'method': 'overlap_shared_speech_v1'}},
        {'id': 'half-b', 'source': 'desktop', 'evidence': {'method': 'overlap_shared_speech_v1'}},
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


def store_row(cid, *, group=None, context=None, visibility='shared', role='meeting', **extra):
    row = {
        'id': cid,
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'language': 'en',
        'capture_group': group,
        'source': 'omi' if cid == 'pendant' else 'desktop',
        'visibility': visibility,
        'screenshot_sharing_enabled': True,
        'external_data': {
            **({'calendar_meeting_context': context} if context else {}),
            **({'conversation_role': role} if role else {}),
        },
    }
    row.update(extra)
    return row


@pytest.fixture
def store(monkeypatch):
    """Dict-backed reads plus a controllable attention claim; records every call."""
    rows: dict[str, dict] = {}
    calls = {'claim': [], 'owns': 0, 'finish': [], 'processed': []}
    states: dict[str, dict] = {}
    operation_number = 0
    monkeypatch.delenv('CAPTURE_GROUP_PRIMARY_NOTES_REFRESH_ENABLED', raising=False)

    def raw_snapshot(uid, cid, field_paths=None, firestore_client=None):
        return rows.get(cid)

    monkeypatch.setattr(refresh.conversations_db, 'get_conversation_raw_snapshot', raw_snapshot)
    monkeypatch.setattr(refresh.conversations_db, 'get_conversation', lambda uid, cid, **kw: rows.get(cid))
    monkeypatch.setattr(
        refresh,
        'deserialize_conversation',
        lambda row: SimpleNamespace(language=row.get('language'), external_data=dict(row.get('external_data') or {})),
    )

    def claim(uid, cid, attention_id=None, expected_generation=None, idempotency_key=None, restart_succeeded=False):
        nonlocal operation_number
        calls['claim'].append((uid, cid, idempotency_key, restart_succeeded))
        operation_number += 1
        return (
            {'operation_id': f'op-{operation_number}', 'conversation_id': cid, 'claim_id': 'c', 'generation': 'g'},
            True,
        )

    monkeypatch.setattr(refresh.attention_db, 'claim', claim)

    def owns(uid, op):
        calls['owns'] += 1
        return True

    monkeypatch.setattr(refresh.attention_db, 'owns_live_claim', owns)

    def finish(uid, op, state, attention_id=None):
        calls['finish'].append(state)

    monkeypatch.setattr(refresh.attention_db, 'finish', finish)

    def process(uid, language, conversation, **kwargs):
        calls['processed'].append((uid, language, kwargs.get('trigger'), kwargs.get('capture_group_refresh_fence')))
        assert kwargs['defer_derived_effects'] is True
        receipt = conversation.external_data[refresh.NOTES_REVISION_FIELD]
        assert receipt['group_id'] == 'group-1'
        kwargs['persistence_observer'](True)
        fence = kwargs['capture_group_refresh_fence']
        state = states.setdefault(fence[0], {})
        state['seen_evidence_fingerprints'] = sorted(
            set(state.get('seen_evidence_fingerprints', ())) | set(state['in_progress']['evidence_fingerprints'])
        )
        state['member_fingerprints'] = state['in_progress']['member_fingerprints']
        state['last_successful_revision'] = fence[1]
        state['in_progress'] = None
        return conversation

    monkeypatch.setattr(refresh, 'process_conversation', process)

    def get_state(uid, group_id):
        return states.get(group_id, {})

    def reserve(uid, group_id, primary_id, revision, member_fingerprints, *, max_refreshes):
        state = states.setdefault(group_id, {})
        primary = rows.get(primary_id) or {}
        current_group = primary.get('capture_group') or {}
        if current_group.get('id') != group_id or current_group.get('revision') != revision:
            return None
        if int(state.get('refresh_count') or 0) >= max_refreshes or state.get('in_progress'):
            return None
        prior = state.get('member_fingerprints') or {}
        seen = set(state.get('seen_evidence_fingerprints') or [])
        evidence = sorted(
            {
                fingerprint
                for mid, fingerprint in member_fingerprints.items()
                if prior.get(mid) != fingerprint and fingerprint not in seen
            }
        )
        if not evidence:
            return None
        reservation = {
            'id': f'reservation-{state.get("refresh_count", 0) + 1}',
            'group_id': group_id,
            'revision': revision,
            'primary_id': primary_id,
            'evidence_fingerprints': evidence,
            'member_fingerprints': dict(member_fingerprints),
        }
        state['refresh_count'] = int(state.get('refresh_count') or 0) + 1
        state['in_progress'] = reservation
        return reservation

    def release(uid, group_id, reservation_id):
        state = states.get(group_id) or {}
        if (state.get('in_progress') or {}).get('id') == reservation_id:
            state['in_progress'] = None
            return True
        return False

    monkeypatch.setattr(refresh.refresh_state_db, 'get_state', get_state)
    monkeypatch.setattr(refresh.refresh_state_db, 'claim_refresh', reserve)
    monkeypatch.setattr(refresh.refresh_state_db, 'release_refresh', release)
    monkeypatch.setattr(refresh, 'load_screen_frame_evidence', lambda uid, cid: ())
    return SimpleNamespace(rows=rows, calls=calls, states=states)


def test_refreshes_primary_once_per_group_revision(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=None)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is True
    assert store.calls['claim'] == [(UID, 'pendant', None, True)]
    assert store.calls['processed'][0][0:3] == (UID, 'en', ProcessingTrigger.CAPTURE_GROUP)
    assert store.calls['processed'][0][3][0:2] == ('group-1', 3)
    assert store.calls['finish'] == ['succeeded']


def test_refresh_targets_the_primary_when_a_member_finalized(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=None)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'half-b') is True
    assert store.calls['claim'][0][1] == 'pendant'
    assert store.calls['processed'][0][0] == UID


def test_no_refresh_without_a_group_or_without_member_context(store):
    store.rows['solo'] = store_row('solo')
    assert refresh.refresh_primary_notes(UID, 'solo') is False
    assert store.calls['claim'] == []
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] == []


def test_no_refresh_once_the_primary_stores_the_member_context(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=MEMBER_CONTEXT)
    store.rows['pendant']['external_data'][refresh.NOTES_REVISION_FIELD] = {'group_id': 'group-1', 'revision': 3}
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    member_fingerprint = refresh._meeting_evidence_fingerprints(
        UID, store.rows['pendant'], {'half-b': store.rows['half-b']}
    )['half-b']
    store.states['group-1'] = {
        'refresh_count': 1,
        'member_fingerprints': {'half-b': member_fingerprint},
        'seen_evidence_fingerprints': [member_fingerprint],
    }
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] == []


def test_second_desktop_half_with_same_roster_still_refreshes_screen_evidence(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP, context=MEMBER_CONTEXT)
    store.rows['pendant']['external_data'][refresh.NOTES_REVISION_FIELD] = {'group_id': 'group-1', 'revision': 2}
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'half-b') is True


def test_missing_full_row_releases_owned_claim(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    monkeypatch.setattr(refresh.conversations_db, 'get_conversation', lambda *a, **kw: None)
    assert refresh.refresh_primary_notes(UID, 'half-b') is False
    assert store.calls['finish'] == ['failed']


def test_kill_switch_disables_the_refresh(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_GROUP_PRIMARY_NOTES_REFRESH_ENABLED', 'off')
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] == []


def test_discarded_deleted_or_unfinished_primaries_are_skipped(store):
    for state in ({'discarded': True}, {'deleted': True}, {'status': 'processing'}):
        store.rows['pendant'] = store_row('pendant', group=GROUP, **state)
        store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
        assert refresh.refresh_primary_notes(UID, 'pendant') is False
        assert store.calls['claim'] == []


def test_unowned_or_rejected_claims_never_process(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    monkeypatch.setattr(
        refresh.attention_db,
        'claim',
        lambda *a, **kw: ({'operation_id': 'op-x'}, False),
    )
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['processed'] == [] and store.calls['finish'] == []

    def rejected(*a, **kw):
        raise refresh.attention_db.ClaimRejected('not_retryable')

    monkeypatch.setattr(refresh.attention_db, 'claim', rejected)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['processed'] == []


def test_a_failed_refresh_marks_the_attempt_failed_and_never_raises(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)

    def explode(uid, language, conversation, **kwargs):
        raise RuntimeError('llm down')

    monkeypatch.setattr(refresh, 'process_conversation', explode)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['finish'] == ['failed']


def test_a_fenced_persistence_marks_the_attempt_failed(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)

    def fenced(uid, language, conversation, **kwargs):
        kwargs['persistence_observer'](False)
        return conversation

    monkeypatch.setattr(refresh, 'process_conversation', fenced)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['finish'] == ['failed']


def test_frame_only_joining_member_is_refresh_eligible(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=None)
    monkeypatch.setattr(
        refresh,
        'load_screen_frame_evidence',
        lambda uid, cid: (
            SimpleNamespace(
                frame_id='frame-1',
                captured_at=T0,
                role='strip',
                names=('Nik Shevchenko',),
                summary='Google Meet call',
            ),
        ),
    )
    assert refresh.refresh_primary_notes(UID, 'half-b') is True
    assert store.calls['processed']


def test_nonmeeting_or_non_desktop_member_context_does_not_trigger_refresh(store):
    group = {
        **GROUP,
        'members': [
            GROUP['members'][0],
            {'id': 'watch', 'source': 'watch', 'evidence': {'method': 'shared_speech'}},
        ],
    }
    store.rows['pendant'] = store_row('pendant', group=group)
    store.rows['watch'] = store_row('watch', group=group, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] == []


def test_private_member_context_does_not_trigger_refresh(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT, visibility='private')
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] == []


def test_legacy_call_group_never_refreshes(store):
    legacy = {**GROUP, 'kind': 'desktop_pendant_call'}
    store.rows['pendant'] = store_row('pendant', group=legacy)
    store.rows['half-b'] = store_row('half-b', group=legacy, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is False
    assert store.calls['claim'] == []


def test_duplicate_evidence_fingerprint_does_not_refresh_again(store):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'pendant') is True
    joined = {
        **GROUP,
        'revision': 4,
        'members': GROUP['members'] + [{'id': 'half-c', 'source': 'desktop', 'evidence': {'method': 'shared_speech'}}],
    }
    store.rows['pendant']['capture_group'] = joined
    store.rows['half-b']['capture_group'] = joined
    store.rows['half-c'] = store_row('half-c', group=joined, context=MEMBER_CONTEXT)
    assert refresh.refresh_primary_notes(UID, 'half-c') is False
    assert len(store.calls['processed']) == 1
    assert len(store.calls['claim']) == 1


def test_refresh_budget_caps_paid_attempts_per_group(store):
    joined = {
        **GROUP,
        'revision': 4,
        'members': GROUP['members'] + [{'id': 'half-c', 'source': 'desktop', 'evidence': {'method': 'shared_speech'}}],
    }
    store.rows['pendant'] = store_row('pendant', group=joined)
    store.rows['half-b'] = store_row('half-b', group=joined, context=MEMBER_CONTEXT)
    store.rows['half-c'] = store_row('half-c', group=joined, context={**MEMBER_CONTEXT, 'calendar_event_id': 'evt-2'})
    store.states['group-1'] = {'refresh_count': refresh.MAX_REFRESHES_PER_GROUP}
    assert refresh.refresh_primary_notes(UID, 'half-c') is False
    assert store.calls['claim'] == []


def test_newer_revision_waiting_on_older_claim_is_requeued(store, monkeypatch):
    store.rows['pendant'] = store_row('pendant', group=GROUP)
    store.rows['half-b'] = store_row('half-b', group=GROUP, context=MEMBER_CONTEXT)
    joined = {
        **GROUP,
        'revision': 4,
        'members': GROUP['members']
        + [{'id': 'half-c', 'source': 'desktop', 'evidence': {'method': 'overlap_shared_speech_v1'}}],
    }
    active = {'value': False}
    operation_number = {'value': 0}

    def claim(uid, cid, attention_id=None, expected_generation=None, idempotency_key=None, restart_succeeded=False):
        store.calls['claim'].append((uid, cid, idempotency_key, restart_succeeded))
        if active['value']:
            return ({'operation_id': 'busy', 'conversation_id': cid}, False)
        operation_number['value'] += 1
        active['value'] = True
        return (
            {
                'operation_id': f'op-{operation_number["value"]}',
                'conversation_id': cid,
                'claim_id': 'c',
                'generation': 'g',
            },
            True,
        )

    def finish(uid, operation, state, attention_id=None):
        store.calls['finish'].append(state)
        active['value'] = False

    monkeypatch.setattr(refresh.attention_db, 'claim', claim)
    monkeypatch.setattr(refresh.attention_db, 'finish', finish)
    process_calls = {'count': 0}

    def race_process(uid, language, conversation, **kwargs):
        process_calls['count'] += 1
        store.calls['processed'].append(
            (uid, language, kwargs.get('trigger'), kwargs.get('capture_group_refresh_fence'))
        )
        if process_calls['count'] == 1:
            store.rows['pendant']['capture_group'] = joined
            store.rows['half-b']['capture_group'] = joined
            store.rows['half-c'] = store_row(
                'half-c', group=joined, context={**MEMBER_CONTEXT, 'calendar_event_id': 'evt-2'}
            )
            # This newer request sees the old conversation claim and returns;
            # it must not attach a revision key to that active attempt.
            assert refresh.refresh_primary_notes(UID, 'half-c') is False
            kwargs['persistence_observer'](False)
        else:
            kwargs['persistence_observer'](True)
            state = store.states['group-1']
            state['seen_evidence_fingerprints'] = sorted(
                set(state.get('seen_evidence_fingerprints', ())) | set(state['in_progress']['evidence_fingerprints'])
            )
            state['member_fingerprints'] = state['in_progress']['member_fingerprints']
            state['in_progress'] = None
        return conversation

    monkeypatch.setattr(refresh, 'process_conversation', race_process)
    assert refresh.refresh_primary_notes(UID, 'pendant') is True
    assert [call[3][1] for call in store.calls['processed']] == [3, 4]
    assert all(call[2] is None for call in store.calls['claim'])
    assert store.calls['finish'] == ['failed', 'succeeded']


def test_read_failures_never_raise(store, monkeypatch):
    def explode(uid, cid, field_paths=None, firestore_client=None):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(refresh.conversations_db, 'get_conversation_raw_snapshot', explode)
    assert refresh.refresh_primary_notes(UID, 'anything') is False
    assert store.calls['claim'] == []
