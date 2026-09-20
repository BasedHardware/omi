"""Regression for live-flap stubs stealing offline capture assignment.

2026-09-19 backend-sync logs (image 7d8a0093e) showed 7-13 lookup candidates,
empty live records every ~35 seconds with started/finished only ~1 us apart.
Failed STT/reconnects minted the stubs; each ordered 60-second WAL adopted a
DIFFERENT nearest stub. Jobs were legacy backfill/unbound_capture_time, without
explicit targets or turnstile timeouts. This replay also covers partial flaps
where reconnects supply distinct missing or empty client conversation IDs.
"""

from copy import deepcopy
from datetime import timedelta

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_capture_continuity import arrival_order, capture, signature
from utils.transcribe_decisions import decide_existing_conversation_action, ConversationLifecycleAction
from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations


def live_stub(cid, timestamp, state=0):
    row = chunk(cid, timestamp)
    row.update(
        created_at=row['started_at'],
        finished_at=row['started_at'] + timedelta(microseconds=1),
        transcript_segments=[],
        photos=[],
        has_photos=False,
        status='in_progress' if state == 0 else 'completed',
        discarded=state == 2,
    )
    return row


def speech_timeline(with_boundaries):
    rows = []
    timestamp = 1000
    for i in range(45):
        if i:
            gap = (120 if i == 15 else 180) if with_boundaries and i in (15, 30) else (119 if i % 5 == 0 else 57)
            timestamp = rows[-1]['finished_at'].timestamp() + gap
        row = chunk(f'wal-{i:03}', timestamp, text=f'Speech interval {i}.')
        row['finished_at'] = row['started_at'] + timedelta(seconds=3)
        row['transcript_segments'][0]['end'] = 3
        rows.append(row)
    return rows


def realtime_reference(rows):
    groups = []
    for row in rows:
        if (
            not groups
            or decide_existing_conversation_action(
                seconds_since_last_segment=(row['started_at'] - groups[-1][-1]['finished_at']).total_seconds(),
                conversation_creation_timeout=120,
            )
            == ConversationLifecycleAction.process_and_create_new
        ):
            groups.append([])
        groups[-1].append(row)
    return [
        (
            group[0]['started_at'],
            group[-1]['finished_at'],
            [
                (row['started_at'].timestamp(), row['finished_at'].timestamp(), row['transcript_segments'][0]['text'])
                for row in group
            ],
        )
        for group in groups
    ]


def replay(order, rows, *, reconnect_targets=False):
    store = StrictFirestore()
    stubs = [
        live_stub(f'live-{i:03}', 1000 + i * 35, i % 3)
        for i in range(int((rows[-1]['finished_at'].timestamp() - 1000) / 35) + 1)
    ]
    originals = {('users', 'u', 'conversations', row['id']): row for row in stubs}
    store.rows.update(deepcopy(originals))
    for i in order:
        row = deepcopy(rows[i])
        nearest = min(stubs, key=lambda stub: abs((stub['started_at'] - row['started_at']).total_seconds()))
        group = i // 5
        target = (f'live-{group * 8:03}' if group % 2 else f'missing-{group}') if reconnect_targets else None
        if reconnect_targets:
            row['sync_capture_id'] = target
        result, _, _ = intake(store, row, candidate_id=nearest['id'], target_id=target)
        assert not result['sync_live_target']
    assert {key: store.rows[key] for key in originals} == originals
    assert not any(key[-1].startswith('missing-') for key in store.rows)
    active = [row for row in conversations(store) if row.get('sync_content_revision')]
    assert sum(len(row['transcript_segments']) for row in active) == 45
    sync_only = StrictFirestore()
    for row in active:
        sync_only.rows[('users', 'u', 'conversations', row['id'])] = row
    return signature(sync_only)


@pytest.mark.parametrize('seed', range(12))
@pytest.mark.parametrize('reconnect_targets', [False, True])
@pytest.mark.parametrize('with_boundaries', [False, True])
def test_sync_speech_partition_equals_realtime_reference(seed, reconnect_targets, with_boundaries):
    """Headline parity: 119s joins, 120s/180s split, despite stubs and job order."""
    rows = speech_timeline(with_boundaries)
    expected = realtime_reference(rows)
    assert len(expected) == (3 if with_boundaries else 1)
    assert replay(arrival_order(seed), rows, reconnect_targets=reconnect_targets) == expected


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('content', ['empty', 'speech', 'photo'])
def test_explicit_target_requires_real_content_through_storage_codecs(monkeypatch, level, content):
    from database import conversations as db

    store = StrictFirestore()
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    stub = live_stub('live', 1000)
    if content == 'speech':
        stub['transcript_segments'] = chunk('speech', 1000)['transcript_segments']
    if content == 'photo':
        stub['has_photos'] = True
    encoded = db._prepare_conversation_for_write(stub, 'u', level)
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(encoded)
    # Large gap proves only a real live target can override temporal assignment.
    row, created, _ = db.assign_sync_conversation('u', capture(44), target_id='live', firestore_client=store)
    if content == 'empty':
        assert created and row['id'] == 'chunk-044' and not row['sync_live_target']
        assert store.rows[('users', 'u', 'conversations', 'live')] == encoded
    else:
        assert not created and row['id'] == 'live' and row['sync_live_target']
        assert len(row['transcript_segments']) == (2 if content == 'speech' else 1)
        assert row['has_photos'] == (content == 'photo')


def test_existing_sync_target_is_only_a_temporal_hint():
    store = StrictFirestore()
    first, _, _ = intake(store, capture(0))
    far, created, _ = intake(store, capture(44), target_id=first['id'])
    assert created and far['id'] != first['id'] and not far['sync_live_target']
    # The target does not override the survivor rule in a real bridge either.
    intake(store, capture(4))
    joined, created, _ = intake(store, capture(2), target_id='chunk-004')
    assert not created and joined['id'] == first['id']
    assert joined['sync_merged_from'] == ['chunk-004']


@pytest.mark.parametrize('target_id', [None, 'new-reconnect'])
def test_retry_lineage_cannot_be_bypassed_with_new_target(target_id):
    store = StrictFirestore()
    intake(store, capture(0))
    intake(store, capture(4))
    intake(store, capture(2))
    store.rows[('users', 'u', 'conversations', 'chunk-000')]['deleted'] = True
    before = deepcopy(store.rows)
    with pytest.raises(ValueError, match='lineage was deleted'):
        intake(store, capture(4), target_id=target_id)
    assert store.rows == before


@pytest.mark.parametrize('absorbed', [False, True])
def test_missing_target_cannot_overwrite_user_managed_retry_anchor(absorbed):
    store = StrictFirestore()
    intake(store, capture(0))
    if absorbed:
        intake(store, capture(4))
        intake(store, capture(2))
    store.rows[('users', 'u', 'conversations', 'chunk-000')]['user_title'] = 'Keep my title'
    before = deepcopy(store.rows)
    with pytest.raises(ValueError, match='user managed'):
        intake(store, capture(4 if absorbed else 0), target_id='missing-reconnect')
    assert store.rows == before
