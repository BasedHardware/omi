"""Clock contract: placement uses evidence, scheduling receives explicit arrival."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from models.recorded_span import RecordedClock, RecordedSpan
from utils.conversations.recorded_time import conversation_span, span_fields, write_span
from utils.episodes import service, timeline
from utils.episodes.moment import MomentInput
from database import episode_timeline, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

T0 = datetime(2026, 10, 29, tzinfo=timezone.utc)


def test_live_processing_wall_is_not_recording_end():
    row = dict(
        started_at=T0,
        finished_at=T0 + timedelta(hours=5),
        status='in_progress',
        transcript_segments=[{'start': 5, 'end': 20}],
    )
    span = conversation_span(row)
    assert (span.recorded_start, span.recorded_end) == (T0 + timedelta(seconds=5), T0 + timedelta(seconds=20))
    assert span.clock == RecordedClock.legacy
    assert conversation_span(dict(row, transcript_segments=[])).recorded_end == T0


def test_sync_receipt_proves_silent_tail_and_write_stamps_arrival():
    row = dict(
        started_at=T0,
        finished_at=T0 + timedelta(hours=5),
        sync_recorded_end_at=T0 + timedelta(seconds=30),
        sync_content_revision=1,
        transcript_segments=[{'start': 5, 'end': 20}],
    )
    stamped = write_span(row, arrival_at=T0 + timedelta(hours=6))
    assert stamped['recorded_end'] == T0 + timedelta(seconds=30)
    assert stamped['clock'] == RecordedClock.device
    assert stamped['arrival_at'] == T0 + timedelta(hours=6)
    assert write_span(dict(row, **stamped), arrival_at=T0 + timedelta(hours=7))['arrival_at'] == stamped['arrival_at']


def test_lazy_read_is_pure_and_does_not_consult_now():
    row = dict(started_at=T0, finished_at=T0 + timedelta(seconds=30), created_at=T0 + timedelta(hours=4))
    before = deepcopy(row)
    assert span_fields(row)['recorded_end'] == row['finished_at']
    assert row == before
    with pytest.raises(ValueError):
        RecordedSpan(recorded_start=T0, recorded_end=T0 - timedelta(seconds=1), clock='device')


def test_boundary_modules_cannot_read_ambient_wall_clock():
    root = Path(__file__).resolve().parents[2]
    files = [
        'utils/episodes/boundaries.py',
        'utils/episodes/boundary_runtime.py',
        'utils/episodes/policy.py',
        'utils/episodes/timeline.py',
        'utils/conversations/recorded_time.py',
        'models/conversation_continuity.py',
    ]
    for file in files:
        assert not re.search(r'\b(?:time\.time|datetime\.(?:now|utcnow))\s*\(', (root / file).read_text()), file


def test_episode_time_service_filters_half_open_windows(monkeypatch):
    rows = [
        dict(
            id='first', started_at=T0, last_activity_at=T0 + timedelta(minutes=10), status='closed', close_reason='gap'
        ),
        dict(
            id='next',
            started_at=T0 + timedelta(hours=1),
            last_activity_at=T0 + timedelta(hours=1, minutes=10),
            status='closed',
            close_reason='user',
        ),
    ]
    monkeypatch.setattr(episode_timeline, 'between', lambda *a, **k: list(reversed(rows)))
    monkeypatch.setattr(episodes, 'get_episode', lambda uid, eid, **k: next(r for r in rows if r['id'] == eid))
    assert timeline.episode_at('u', T0 + timedelta(minutes=39))['id'] == 'first'
    assert timeline.episode_at('u', T0 + timedelta(minutes=40)) is None
    assert timeline.episode_at('u', T0 - timedelta(seconds=1)) is None
    assert [r['id'] for r in timeline.episodes_between('u', T0, T0 + timedelta(hours=2))] == ['first', 'next']
    assert timeline.episodes_between('u', T0 + timedelta(minutes=40), T0 + timedelta(hours=1)) == []


@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_shuffled_arrivals_have_identical_recorded_episodes_and_reverse_membership(monkeypatch, order):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    store = StrictFirestore()
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda *a, **kw: [dict(v, id=k[-1]) for k, v in store.rows.items() if k[2] == 'episodes'],
    )
    inputs = [(0, 20), (30, 60), (3600, 3620)]
    for arrival, i in enumerate(order):
        start, end = [T0 + timedelta(seconds=s) for s in inputs[i]]
        store.rows[('users', 'u', 'conversations', str(i))] = dict(
            id=str(i), **write_span(dict(started_at=start, finished_at=end), arrival_at=T0 + timedelta(days=arrival))
        )
        episode_timeline.attach_recorded(
            'u',
            str(i),
            'omi',
            start,
            end,
            choose=timeline.choose_recorded_episode,
            new_episode={},
            firestore_client=store,
        )
    rows = [v for k, v in store.rows.items() if k[2] == 'episodes' and not v.get('recorded_merged_into')]
    shape = sorted((r['started_at'], r['last_activity_at'], sorted(r['conversation_ids'])) for r in rows)
    assert shape == [
        (T0, T0 + timedelta(seconds=60), ['0', '1']),
        (T0 + timedelta(hours=1), T0 + timedelta(seconds=3620), ['2']),
    ]
    for i in range(3):
        row = store.rows[('users', 'u', 'conversations', str(i))]
        assert row['episode_id'] == store.rows[('users', 'u', 'episode_links', str(i))]['episode_id']


def test_missing_capture_timeline_fails_before_acknowledging_held_audio(monkeypatch):
    from utils.sync import live_cap_hold

    hold = live_cap_hold.LiveHeldAudio.__new__(live_cap_hold.LiveHeldAudio)
    receiver = SimpleNamespace(
        _cap_decided_spans=[], host=SimpleNamespace(state=SimpleNamespace(conversation_sample_ranges=[]))
    )
    with pytest.raises(RuntimeError, match='requires recorded capture timeline'):
        hold.observe(receiver, b'\0' * 320, 16000, 0, False)
    assert receiver._cap_decided_spans == []


def test_llm_measurement_is_on_without_revision_reuse_and_has_bounded_labels(monkeypatch, caplog):
    from utils.sync import repeat_work_metrics as metrics

    monkeypatch.setattr(metrics, 'revision_reuse', lambda: False)
    before = metrics.PHASE_A_CALLS.labels('other', 'completed')._value.get()
    token = metrics._scope.set(('synthetic-user', SimpleNamespace(id='synthetic-conversation')))
    try:
        with caplog.at_level('INFO'):
            metrics.record_llm_call('completed', 'user-controlled-feature')
            metrics.record_survivor_refresh('synthetic-user', 'synthetic-conversation', 'synthetic-episode')
    finally:
        metrics._scope.reset(token)
    assert metrics.PHASE_A_CALLS.labels('other', 'completed')._value.get() == before + 1
    assert 'feature=other' in caplog.text
    assert 'synthetic-user' not in caplog.text and 'synthetic-episode' not in caplog.text


def test_live_moment_llm_measurement_uses_conversation_identity(monkeypatch, caplog):
    import hashlib
    from utils.sync import repeat_work_metrics as metrics

    monkeypatch.setattr(service, 'episodes_enabled_for', lambda uid: True)

    def process(*args, **kwargs):
        metrics.record_llm_call('completed', 'episode_incremental')
        return 'updated'

    monkeypatch.setattr(service, '_record_moment_once', process)
    moment = MomentInput('conversation-live', 'omi', [], T0, T0, 'pause')
    before = metrics.PHASE_A_CALLS.labels('episode_incremental', 'completed')._value.get()
    outer_scope = metrics._scope.get()
    with caplog.at_level('INFO'):
        assert service.record_moment('user-live', moment) == 'updated'
    assert metrics._scope.get() is outer_scope
    assert metrics.PHASE_A_CALLS.labels('episode_incremental', 'completed')._value.get() == before + 1
    assert hashlib.sha256(b'user-live\0conversation-live').hexdigest() in caplog.text
    assert 'conversation-live' not in caplog.text


@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_late_bridge_coalesces_silence_components_independent_of_arrival(monkeypatch, order):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    store = StrictFirestore()
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda *a, **kw: [dict(v, id=k[-1]) for k, v in store.rows.items() if k[2] == 'episodes'],
    )
    spans = [(0, 60), (3600, 3660), (1200, 2500)]
    for i in order:
        start, end = [T0 + timedelta(seconds=s) for s in spans[i]]
        store.rows[('users', 'u', 'conversations', str(i))] = {'id': str(i)}
        episode_timeline.attach_recorded(
            'u',
            str(i),
            'omi',
            start,
            end,
            choose=timeline.choose_recorded_episode,
            new_episode={},
            firestore_client=store,
        )
    rows = [v for k, v in store.rows.items() if k[2] == 'episodes' and not v.get('recorded_merged_into')]
    assert len(rows) == 1
    assert rows[0]['started_at'] == T0 and rows[0]['last_activity_at'] == T0 + timedelta(seconds=3660)
    assert sorted(rows[0]['conversation_ids']) == ['0', '1', '2']
    for i in range(3):
        assert store.rows[('users', 'u', 'conversations', str(i))]['episode_id'] == rows[0]['id']
    for key, value in store.rows.items():
        if key[2] == 'episodes' and value.get('recorded_merged_into'):
            assert episodes.get_episode('u', key[-1], firestore_client=store)['id'] == rows[0]['id']


def test_moment_boundaries_do_not_use_arrival_gaps():
    from utils.episodes.live import MomentTracker

    tracker = MomentTracker()
    segments = [{'id': 'speech', 'text': 'word ' * 30, 'start': 0, 'end': 1}]
    assert tracker.observe('u', segments, 'c', 'omi', arrival_at=1000, recorded_at=10) == []
    # A delayed delivery does not manufacture a recorded pause or interval.
    assert tracker.observe('u', segments, 'c', 'omi', arrival_at=2000, recorded_at=11) == []
    assert tracker._buffers['u'].last_wall == 11
    assert tracker._buffers['u'].last_arrival_at == 2000


@pytest.mark.parametrize('order', [list(range(5)), list(reversed(range(5))), [2, 4, 0, 3, 1]])
def test_four_hour_partition_is_independent_of_arrival_of_an_earlier_prefix(monkeypatch, order):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    store = StrictFirestore()
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda *a, **kw: [dict(v, id=k[-1]) for k, v in store.rows.items() if k[2] == 'episodes'],
    )
    for i in order:
        store.rows[('users', 'u', 'conversations', str(i))] = {'id': str(i)}
        episode_timeline.attach_recorded(
            'u',
            str(i),
            'omi',
            T0 + timedelta(hours=i),
            T0 + timedelta(hours=i + 1),
            choose=timeline.choose_recorded_episode,
            new_episode={},
            firestore_client=store,
        )
    rows = sorted(
        (v for k, v in store.rows.items() if k[2] == 'episodes' and not v.get('recorded_merged_into')),
        key=lambda row: row['started_at'],
    )
    assert [(row['started_at'], row['last_activity_at']) for row in rows] == [
        (T0, T0 + timedelta(hours=4)),
        (T0 + timedelta(hours=4), T0 + timedelta(hours=5)),
    ]
    assert [row['conversation_ids'] for row in rows] == [['0', '1', '2', '3'], ['4']]
    for i in range(5):
        assert store.rows[('users', 'u', 'conversations', str(i))]['episode_id'] == rows[i // 4]['id']


def test_attach_before_create_membership_is_adopted_without_a_ghost_row():
    from database import conversation_recorded_time

    store = StrictFirestore()
    store.rows[('users', 'u', 'episode_links', 'new')] = {'episode_id': 'existing-episode'}
    payload = {'id': 'new', 'status': 'in_progress', 'started_at': T0, 'created_at': T0}
    conversation_recorded_time.stamp_for_write(payload)
    assert ('users', 'u', 'conversations', 'new') not in store.rows
    assert conversation_recorded_time.create_if_absent('u', payload, firestore_client=store) == (True, False)
    saved = store.rows[('users', 'u', 'conversations', 'new')]
    assert saved['episode_id'] == 'existing-episode'
    assert saved['recorded_start'] == saved['recorded_end'] == T0
    assert saved['clock'] == 'live_capture' and saved['arrival_at'] is not None
    assert conversation_recorded_time.create_if_absent('u', payload, firestore_client=store) == (False, False)


def test_recorded_component_larger_than_membership_batch_commits_all_reverse_links(monkeypatch):
    store = StrictFirestore()
    facts = {
        f'c{i:02}': {
            'start': T0 + timedelta(seconds=30 * i),
            'end': T0 + timedelta(seconds=30 * i + 20),
            'source': 'omi',
        }
        for i in range(50)
    }
    store.rows[('users', 'u', 'episodes', 'original')] = dict(
        id='original',
        started_at=T0,
        last_activity_at=T0 + timedelta(seconds=1490),
        status='closed',
        close_reason='gap',
        recorded_members=facts,
        conversation_ids=list(facts),
        state_version=1,
    )
    for i in range(51):
        store.rows[('users', 'u', 'conversations', f'c{i:02}')] = {'id': f'c{i:02}'}
    monkeypatch.setattr(episodes, 'seal', lambda uid, row: dict(row))
    monkeypatch.setattr(episodes, 'unseal', lambda uid, row: row)
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda *a, **kw: [dict(v, id=k[-1]) for k, v in store.rows.items() if k[2] == 'episodes'],
    )
    read = episodes.read_memberships
    batches = []

    def bounded_read(transaction, client, uid, ids, *, admit_conversation_id=None):
        ids = list(ids)
        batches.append(len(ids))
        return read(transaction, client, uid, ids, admit_conversation_id=admit_conversation_id)

    monkeypatch.setattr(episodes, 'read_memberships', bounded_read)
    result = episode_timeline.attach_recorded(
        'u',
        'c50',
        'omi',
        T0 + timedelta(seconds=1500),
        T0 + timedelta(seconds=1520),
        choose=timeline.choose_recorded_episode,
        new_episode={},
        firestore_client=store,
    )
    assert sum(batches) == 51 and max(batches) <= 50
    assert len(result['conversation_ids']) == 51
    for i in range(51):
        assert store.rows[('users', 'u', 'conversations', f'c{i:02}')]['episode_id'] == result['id']
        assert store.rows[('users', 'u', 'episode_links', f'c{i:02}')]['episode_id'] == result['id']


def test_arrival_cannot_manufacture_a_missing_recorded_origin():
    assert (
        conversation_span({'created_at': T0, 'finished_at': T0 + timedelta(hours=5), 'status': 'in_progress'}) is None
    )


def test_new_import_stamps_real_arrival_instead_of_its_historical_created_date(monkeypatch):
    from database import conversation_recorded_time
    from models.conversation import Conversation

    arrived = T0 + timedelta(days=3)
    monkeypatch.setattr(conversation_recorded_time, 'datetime', SimpleNamespace(now=lambda zone: arrived))
    imported = Conversation(
        id='new-import',
        created_at=T0,
        started_at=T0,
        finished_at=T0 + timedelta(seconds=20),
        structured={},
        source='external_integration',
    )
    assert imported.arrival_at is None
    payload = imported.model_dump()
    conversation_recorded_time.stamp_for_write(payload)
    assert payload['arrival_at'] == arrived
    assert payload['recorded_start'] == T0 and payload['recorded_end'] == T0 + timedelta(seconds=20)
    assert payload['clock'] == 'imported'

    unknown = imported.model_copy(update={'started_at': None, 'finished_at': None}).model_dump()
    conversation_recorded_time.stamp_for_write(unknown)
    assert unknown['recorded_start'] is None and unknown['recorded_end'] is None
    assert unknown['arrival_at'] == arrived and unknown['clock'] == 'imported'


def test_timing_projection_never_serializes_display_fields():
    class Recording:
        started_at = T0
        transcript_segments = [SimpleNamespace(start=3, end=15)]
        status = 'in_progress'

        def model_dump(self):
            raise AssertionError('unrelated display serialization')

    span = conversation_span(Recording())
    assert (span.recorded_start, span.recorded_end) == (T0 + timedelta(seconds=3), T0 + timedelta(seconds=15))


@pytest.mark.parametrize('start,end', [(T0, None), (None, T0), (T0, T0 - timedelta(seconds=1))])
def test_invalid_explicit_span_does_not_fall_back_to_legacy_wall(start, end):
    assert (
        conversation_span(
            dict(recorded_start=start, recorded_end=end, started_at=T0, finished_at=T0 + timedelta(hours=3))
        )
        is None
    )


def test_cap_successor_uses_its_own_members_recorded_span():
    from database.episode_recorded_components import partition

    facts = {
        'long': {'start': T0, 'end': T0 + timedelta(hours=5)},
        'next': {'start': T0 + timedelta(hours=4, minutes=10), 'end': T0 + timedelta(hours=4, minutes=11)},
    }
    windows = partition('synthetic', facts)
    assert [(r['started_at'], r['last_activity_at'], r['conversation_ids']) for r in windows] == [
        (T0, T0 + timedelta(hours=4), ['long']),
        (T0 + timedelta(hours=4, minutes=10), T0 + timedelta(hours=4, minutes=11), ['next']),
    ]
