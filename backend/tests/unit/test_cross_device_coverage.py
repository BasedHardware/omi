"""Generated token streams only: cross-device folds and exact custody fences."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import refactor_modes
from database import capture_coverage as ledger_db, capture_groups as groups_db, capture_speech
from database import conversations as conversations_db
from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.capture import coverage, coverage_alignment as alignment, coverage_crossdevice as cross
from utils.conversations import duplicate_capture

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def tokens(scene, line):
    return ' '.join(f'w{scene}{line}{index:03d}' for index in range(16))


def row(index, source='omi', scene=1, **extra):
    return {
        'id': str(UUID(int=index)),
        'source': source,
        'status': 'completed',
        'created_at': T0,
        'started_at': T0,
        'finished_at': T0 + timedelta(seconds=200),
        'client_device_id': str(UUID(int=index + 100)),
        'transcript_segments': [
            {'start': start, 'end': start + 8, 'text': tokens(scene, line), 'speaker_id': index}
            for line, start in enumerate((20, 60, 100))
        ],
        'capture_evidence': {'capture_root': str(UUID(int=index + 200)), 'channel': 'mono', 'clock_epoch': '0'},
        **extra,
    }


def key(row):
    return CaptureKey(**row['capture_evidence'], device_id=row['client_device_id'])


def path(owner, cid):
    return ('users', owner, 'conversations', cid)


@pytest.fixture
def harness(monkeypatch):
    owner = str(UUID(int=1))
    store = StrictFirestore()
    monkeypatch.setenv(coverage.FLAG, 'serve')
    monkeypatch.setattr(ledger_db, '_client', lambda: store)
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(
        cross,
        'get_shared_speech_snapshot',
        lambda owner, cid: capture_speech.get_shared_speech_snapshot(owner, cid, firestore_client=store),
    )
    monkeypatch.setattr(
        conversations_db,
        'get_conversations_finished_after',
        lambda owner, **kw: [
            deepcopy(value) for p, value in store.rows.items() if p[:3] == ('users', owner, 'conversations')
        ][: kw['limit']],
    )
    monkeypatch.setattr(conversations_db, 'link_duplicate_capture', lambda *a: False)
    return owner, store


def add(harness, *rows, frames=True):
    owner, store = harness
    for value in rows:
        store.rows[path(owner, value['id'])] = deepcopy(value)
        if frames:
            coverage.record(
                owner,
                key(value),
                CoverageRecord(conversation_id=value['id'], origin='live', ranges=[FrameRange(start=10, end=30)]),
            )


@pytest.mark.parametrize('count', [2, 3])
@pytest.mark.parametrize('last', [0, 1])
def test_finalizer_repeated_speech_pendant_watch_phone_one_event(harness, count, last):
    owner, store = harness
    rows = [row(10, 'omi'), row(11, 'apple_watch'), row(12, 'phone')][:count]
    # Longer secondary and conflicting speakers do not win over the pendant.
    rows[1]['finished_at'] += timedelta(seconds=30)
    add(harness, *rows)
    before = deepcopy(store.rows)
    duplicate_capture.link_duplicate_captures(owner, rows[last])
    groups = [store.rows[path(owner, r['id'])]['capture_group'] for r in rows]
    assert len({g['id'] for g in groups}) == 1
    assert {g['primary_id'] for g in groups} == {rows[0]['id']}
    # The existing client event-list projection shows one primary; original
    # recordings remain reachable and retain every byte of transcript/audio.
    visible = [r for r, g in zip(rows, groups) if r['id'] == g['primary_id']]
    assert len(visible) == 1 and len(visible[0]['transcript_segments']) == 3
    for r in rows:
        stored = deepcopy(store.rows[path(owner, r['id'])])
        stored.pop('capture_group')
        assert stored == before[path(owner, r['id'])]
    for secondary in rows[1:]:
        result = coverage.query(owner, key(secondary), [FrameRange(start=0, end=40)])
        assert result.covering_conversation_id == rows[0]['id']
        assert result.covered == [FrameRange(start=10, end=30)]
        assert result.uncovered == [FrameRange(start=0, end=10), FrameRange(start=30, end=40)]
        events = coverage.committed_events(owner, key(secondary), [FrameRange(start=0, end=40)])
        assert len(events) == 1 and events[0].conversation_id == rows[0]['id']
        assert events[0].capture_root == key(secondary).capture_root
        assert (events[0].source_start, events[0].source_end) == (10, 30)
    transactions = len(store.transactions)
    duplicate_capture.link_duplicate_captures(owner, rows[last])
    assert len({store.rows[path(owner, r['id'])]['capture_group']['id'] for r in rows}) == 1
    assert all(not tx.has_written for tx in store.transactions[transactions:])


@pytest.mark.parametrize('mode', ['shadow', 'off', 'typo'])
def test_non_serving_preserves_output_and_withholds_receipts(harness, monkeypatch, mode, caplog):
    owner, store = harness
    # Same source/different devices avoids the incumbent cross-source grouping.
    first, second = row(10), row(11)
    add(harness, first, second)
    before = deepcopy(store.rows)
    transactions = len(store.transactions)
    monkeypatch.setenv(coverage.FLAG, mode)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE_SHADOW_PERCENT', '100')
    with caplog.at_level('INFO'):
        assert cross.reconcile(owner, first['id'], [second['id']]) is False
    assert store.rows == before
    assert coverage.committed_events(owner, key(second), [FrameRange(start=10, end=30)]) == []
    if mode != 'off':
        assert 'would_fold=True' in caplog.text and 'duplicate_line_rate=1.0000' in caplog.text
        assert owner not in caplog.text
        assert all(tokens(1, i) not in caplog.text for i in range(3))
    else:
        assert len(store.transactions) == transactions


def test_unsampled_shadow_reads_no_snapshots(harness, monkeypatch):
    owner, _ = harness
    first, second = row(10), row(11)
    add(harness, first, second)
    monkeypatch.setenv(coverage.FLAG, 'shadow')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE_SHADOW_PERCENT', '0')
    monkeypatch.setattr(cross, 'get_shared_speech_snapshot', lambda *a: pytest.fail('unsampled shadow read'))
    assert cross.reconcile(owner, first['id'], [second['id']]) is False


def test_digest_cohort_serves_while_host_is_shadow(harness, monkeypatch):
    owner, store = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    monkeypatch.setenv(coverage.FLAG, 'shadow')
    monkeypatch.setenv(coverage.FLAG + '_SERVE_UID_SHA256S', refactor_modes.uid_digest(owner))
    assert cross.reconcile(owner, first['id'], [second['id']])
    assert store.rows[path(owner, first['id'])]['capture_group']['primary_id'] == first['id']


@pytest.mark.parametrize(
    'case', ['other_room', 'unique_tail', 'same_device', 'outside', 'one_line', 'unplaced', 'lock']
)
def test_false_fold_classes_keep_both(harness, case):
    owner, store = harness
    first, second = row(10), row(11, 'apple_watch')
    if case == 'other_room':
        second = row(11, 'apple_watch', scene=2)
    elif case == 'unique_tail':
        second['transcript_segments'].append({'start': 150, 'end': 158, 'text': tokens(2, 0)})
    elif case == 'same_device':
        second['source'] = first['source']
        second['client_device_id'] = first['client_device_id']
    elif case == 'outside':
        second['started_at'] += timedelta(seconds=300)
        second['finished_at'] += timedelta(seconds=300)
    elif case == 'one_line':
        second['transcript_segments'] = second['transcript_segments'][:1]
    elif case == 'unplaced':
        second['transcript_segments'][0]['audio_alignment'] = 'unplaced'
    else:
        second['is_locked'] = True
    add(harness, first, second)
    assert cross.reconcile(owner, first['id'], [second['id']])
    assert all('capture_group' not in store.rows[path(owner, r['id'])] for r in (first, second))
    assert coverage.query(owner, key(second), [FrameRange(start=10, end=30)]).covering_conversation_id == second['id']


@pytest.mark.parametrize('case', ['snr', 'confidence', 'missing', 'pendant', 'same_host'])
def test_quality_ranking(case):
    first, second = row(10, 'phone'), row(11, 'desktop')
    if case == 'snr':
        first['audio_quality'] = {'snr_db': 5, 'word_confidence': 1}
        second['audio_quality'] = {'snr_db': 12, 'word_confidence': 0.8}
    elif case == 'confidence':
        first['audio_quality'] = {'word_confidence': 0.7}
        second['audio_quality'] = {'word_confidence': 0.9}
    elif case == 'missing':
        second['audio_quality'] = {'snr_db': 0}
    elif case == 'same_host':
        first['client_device_id'] = second['client_device_id']
    else:
        first['audio_quality'] = {'snr_db': 100}
        second['source'] = 'omi'
    assert alignment.align(first, second).would_fold
    expected = first['id'] if case == 'same_host' else second['id']
    assert alignment.align(first, second).primary_id == expected


@pytest.mark.parametrize('mutation', ['separate', 'deleted', 'discarded', 'edit', 'corrected', 'primary', 'lock'])
def test_alias_invalidated_by_current_authority(harness, mutation):
    owner, store = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    cross.reconcile(owner, first['id'], [second['id']])
    primary = store.rows[path(owner, first['id'])]
    if mutation == 'separate':
        groups_db.leave_capture_group(owner, second['id'], sticky=True)
    elif mutation in ('deleted', 'discarded'):
        primary[mutation] = True
    elif mutation == 'edit':
        primary['transcript_segments'][0]['text'] = tokens(3, 0)
    elif mutation == 'corrected':
        primary['has_transcript_corrections'] = True
    elif mutation == 'primary':
        primary['capture_group']['primary_id'] = second['id']
    else:
        primary['is_locked'] = True
    assert coverage.query(owner, key(second), [FrameRange(start=10, end=30)]).covering_conversation_id == second['id']


def test_no_committed_secondary_frames_no_cross_device_custody(harness):
    owner, store = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second, frames=False)
    cross.reconcile(owner, first['id'], [second['id']])
    assert store.rows[path(owner, second['id'])]['capture_group']
    assert not coverage.query(owner, key(second), [FrameRange(start=10, end=30)]).covered
    assert coverage.committed_events(owner, key(second), [FrameRange(start=10, end=30)]) == []


def test_api_query_names_primary_and_is_owner_scoped(harness, monkeypatch):
    from utils.capture import coverage_endpoint

    owner, _ = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    cross.reconcile(owner, first['id'], [second['id']])
    app = FastAPI()
    app.include_router(coverage_endpoint.router)
    monkeypatch.setattr(coverage_endpoint, '_limit', lambda owner: None)
    app.dependency_overrides[coverage_endpoint.auth.get_current_user_uid] = lambda: owner
    params = {**key(second).model_dump(exclude_none=True), 'start': [10], 'end': [30]}
    with TestClient(app) as client:
        response = client.get('/v2/capture-coverage', params=params)
        assert response.status_code == 200
        assert response.json()['covering_conversation_id'] == first['id']
        app.dependency_overrides[coverage_endpoint.auth.get_current_user_uid] = lambda: str(UUID(int=999))
        assert client.get('/v2/capture-coverage', params=params).json()['covered'] == []


def test_late_pendant_replaces_watch_primary_and_rewrites_alias(harness):
    owner, store = harness
    watch, phone, pendant = row(11, 'apple_watch'), row(12, 'phone'), row(10)
    add(harness, watch, phone)
    cross.reconcile(owner, watch['id'], [phone['id']])
    assert coverage.query(owner, key(phone), [FrameRange(start=10, end=30)]).covering_conversation_id == watch['id']
    add(harness, pendant)
    cross.reconcile(owner, pendant['id'], [watch['id'], phone['id']])
    for secondary in (watch, phone):
        assert store.rows[path(owner, secondary['id'])]['capture_group']['primary_id'] == pendant['id']
        assert (
            coverage.query(owner, key(secondary), [FrameRange(start=10, end=30)]).covering_conversation_id
            == pendant['id']
        )
    groups_db.leave_capture_group(owner, pendant['id'], sticky=True)
    assert store.rows[path(owner, phone['id'])]['capture_group']['primary_id'] == watch['id']
    # Old aliases to the departed primary are never proof for custody.
    assert coverage.query(owner, key(phone), [FrameRange(start=10, end=30)]).covering_conversation_id == phone['id']


def test_ordinary_ledger_retry_preserves_shared_proof_and_key_partition(harness):
    owner, _ = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    cross.reconcile(owner, first['id'], [second['id']])
    coverage.record(
        owner,
        key(second),
        CoverageRecord(conversation_id=second['id'], origin='live', ranges=[FrameRange(start=10, end=30)]),
    )
    assert coverage.query(owner, key(second), [FrameRange(start=10, end=30)]).covering_conversation_id == first['id']
    for field in ('capture_root', 'device_id', 'recording_session_id', 'clock_epoch', 'channel'):
        changed = key(second).model_copy(update={field: str(UUID(int=888))})
        assert not coverage.query(owner, changed, [FrameRange(start=10, end=30)]).covered


@pytest.mark.parametrize('race', ['text', 'window', 'quality', 'separate'])
def test_transaction_refuses_changed_alignment_or_membership(harness, monkeypatch, race):
    owner, store = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    join = groups_db.join_capture_group

    def racing_join(*args, **kwargs):
        current = store.rows[path(owner, first['id'])]
        if race == 'text':
            current['transcript_segments'][0]['text'] = tokens(3, 0)
        elif race == 'window':
            current['finished_at'] += timedelta(seconds=10)
        elif race == 'quality':
            current['audio_quality'] = {'snr_db': 20}
        else:
            current['capture_group_exclusions'] = [second['id']]
        return join(*args, **kwargs)

    monkeypatch.setattr(groups_db, 'join_capture_group', racing_join)
    cross.reconcile(owner, first['id'], [second['id']])
    assert not store.rows[path(owner, second['id'])].get('capture_group')
    assert coverage.query(owner, key(second), [FrameRange(start=10, end=30)]).covering_conversation_id == second['id']


def test_missing_or_unconfirmed_primary_never_creates_alias(harness):
    owner, _ = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    assert not ledger_db.record_shared(
        owner,
        key(second),
        primary_id=first['id'],
        secondary_id=second['id'],
        group_id=str(UUID(int=909)),
        fingerprints={r['id']: groups_db.transcript_fingerprint(r) for r in (first, second)},
        window={'started_at': T0, 'finished_at': second['finished_at']},
    )
    assert not ledger_db.read_shared(owner, key(second))


def test_partial_same_room_does_not_hide_unique_primary_or_secondary_speech():
    first, second = row(10), row(11, 'apple_watch')
    # A long capture contains two unrelated rooms. Two smaller captures cannot
    # become one event by transitively matching distinct scenes within it.
    unrelated = row(12, 'phone', scene=2)
    first['transcript_segments'].extend(deepcopy(unrelated['transcript_segments']))
    assert alignment.align(first, second).would_fold
    assert alignment.align(first, unrelated).would_fold
    assert not alignment.align(second, unrelated).would_fold


def test_alignment_overflow_keeps_all_speech(monkeypatch):
    monkeypatch.setattr(alignment, 'MAX_ALIGNMENT_WORK', 1)
    decision = alignment.align(row(10), row(11, 'apple_watch'))
    assert not decision.would_fold and decision.reason == 'alignment_bounds'


def test_duplicate_line_rate_includes_unrelated_candidate_lines():
    decision = alignment.align(row(10), row(11, 'apple_watch', scene=2))
    assert decision.secondary_lines == 3 and decision.duplicate_lines == 0
    assert decision.duplicate_line_rate == 0


def test_snapshot_failure_keeps_captures_and_logs_no_request_data(harness, monkeypatch, caplog):
    owner, store = harness
    first, second = row(10), row(11, 'apple_watch')
    add(harness, first, second)
    before = deepcopy(store.rows)

    def fail(*args):
        raise RuntimeError(owner + tokens(1, 0))

    monkeypatch.setattr(cross, 'get_shared_speech_snapshot', fail)
    with caplog.at_level('INFO'):
        assert cross.reconcile(owner, first['id'], [second['id']])
    assert store.rows == before
    assert 'cross_device_fold outcome=error' in caplog.text
    assert owner not in caplog.text and tokens(1, 0) not in caplog.text


def test_long_capture_cannot_bridge_two_different_rooms_into_one_group(harness):
    owner, store = harness
    primary, room_a, room_b = row(10), row(11, 'apple_watch'), row(12, 'phone', scene=2)
    primary['transcript_segments'].extend(deepcopy(room_b['transcript_segments']))
    add(harness, primary, room_a)
    cross.reconcile(owner, primary['id'], [room_a['id']])
    assert store.rows[path(owner, room_a['id'])]['capture_group']
    add(harness, room_b)
    cross.reconcile(owner, room_b['id'], [primary['id']])
    assert not store.rows[path(owner, room_b['id'])].get('capture_group')
    assert len(store.rows[path(owner, primary['id'])]['capture_group']['members']) == 2
    assert coverage.query(owner, key(room_b), [FrameRange(start=10, end=30)]).covering_conversation_id == room_b['id']
