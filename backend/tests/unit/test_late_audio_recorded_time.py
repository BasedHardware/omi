"""Recorded-time regressions: upload clocks cannot own audio or live timers."""

from datetime import datetime, timedelta, timezone
import pytest
from utils.episodes import finalize as episode_finalize
from config import episodes as config
from config import recorded_time as flags
from database import episode_timeline, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, intake
from utils.conversations.recorded_time import is_late, recorded_span
from utils.episodes import service, timeline
from utils.sync import late_audio

T0 = datetime(2026, 10, 29, 1, 4, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=4)


def test_recorded_end_ignores_four_hour_upload_delay():
    span = recorded_span(T0, [{'start': 0, 'end': 20}, {'start': 30, 'end': 40}])
    assert span == (T0, T0 + timedelta(seconds=40))
    assert is_late(span, NOW)
    assert (
        recorded_span(T0, [{'start': 0, 'end': float('nan')}, {'start': 0, 'end': 2, 'audio_alignment': 'unplaced'}])
        is None
    )


@pytest.mark.parametrize(
    'switch', ['LATE_AUDIO_SYNC_INTAKE_ENABLED', 'EPISODE_RECORDED_TIME_ENABLED', 'EPISODE_LIVE_TIMER_START_ENABLED']
)
def test_switches_ship_on_and_roll_back(monkeypatch, switch):
    fn = {
        'LATE_AUDIO_SYNC_INTAKE_ENABLED': flags.late_audio_intake_enabled,
        'EPISODE_RECORDED_TIME_ENABLED': flags.recorded_episodes_enabled,
        'EPISODE_LIVE_TIMER_START_ENABLED': flags.live_timer_start_enabled,
    }[switch]
    monkeypatch.delenv(switch, raising=False)
    assert fn()
    monkeypatch.setenv(switch, 'false')
    assert not fn()


def test_old_chunks_ignore_different_current_live_stamps_and_merge(monkeypatch):
    monkeypatch.delenv('LATE_AUDIO_SYNC_INTAKE_ENABLED', raising=False)
    store = StrictFirestore()
    for i in range(2):
        live = chunk(f'live-{i}', NOW.timestamp() + i * 60)
        live.update(status='in_progress', created_at=NOW)
        store.rows[('users', 'u', 'conversations', live['id'])] = live
    first, _, _ = intake(store, chunk('old-1', T0.timestamp()), target_id='live-0')
    second, created, _ = intake(store, chunk('old-2', T0.timestamp() + 30), target_id='live-1')
    assert first['id'] == second['id'] == 'old-1'
    assert not created
    assert second['finished_at'] == T0 + timedelta(seconds=39.5)
    assert second['started_at'] == T0
    assert len(second['transcript_segments']) == 2
    assert all(store.rows[('users', 'u', 'conversations', f'live-{i}')]['started_at'] >= NOW for i in range(2))


def test_late_listen_batches_use_real_temporal_assignment_and_retry_enrichment(monkeypatch):
    store = StrictFirestore()
    marks, attachments = [], []
    monkeypatch.setattr(late_audio.lifecycle, 'ingest_sync_conversation', lambda uid, incoming: intake(store, incoming))
    monkeypatch.setattr(late_audio.outbox, 'mark', lambda *a, **k: marks.append((a, k)))
    monkeypatch.setattr(episode_finalize, 'schedule_synced_intake_attach', lambda *a: attachments.append(a))
    row = {
        'id': 'live-generation',
        'source': 'omi',
        'started_at': T0,
        'client_device_id': 'pendant',
        'data_protection_level': 'standard',
    }
    a = [
        {
            'id': 'a',
            'start': 0.0,
            'end': 20.0,
            'text': 'We agreed to meet on Friday to review the release plan.',
            'speaker_id': 0,
        }
    ]
    b = [
        {
            'id': 'b',
            'start': 30.0,
            'end': 40.0,
            'text': 'Please bring the completed checklist for the team to review.',
            'speaker_id': 0,
        }
    ]
    first = late_audio.ingest_late_transcript('u', row, a)
    second = late_audio.ingest_late_transcript('u', dict(row, id='next-live-generation'), b)
    retry = late_audio.ingest_late_transcript('u', row, a)
    assert first['id'] == second['id'] == retry['id']
    assert second['finished_at'] == T0 + timedelta(seconds=40)
    assert len(second['transcript_segments']) == len(retry['transcript_segments']) == 2
    assert len(marks) == len(attachments) == 3
    assert not second['sync_live_target']


def _episode(key, start, end, status='closed', reason='gap'):
    return dict(
        id=key,
        started_at=start,
        last_activity_at=end,
        closed_at=end if status == 'closed' else None,
        status=status,
        close_reason=reason,
        conversation_ids=[],
        state_version=1,
    )


def test_timeline_finds_older_closed_owner_despite_a_newer_live_episode():
    old = _episode('old', T0, T0 + timedelta(minutes=22))
    live = _episode('live', NOW, NOW + timedelta(minutes=5), 'live')
    assert timeline.choose_recorded_episode([live, old], T0 + timedelta(minutes=5), T0 + timedelta(minutes=6)) == old
    assert timeline.choose_recorded_episode([old, live], NOW + timedelta(minutes=1), NOW + timedelta(minutes=2)) == live
    assert timeline.choose_recorded_episode([old], T0 + timedelta(minutes=52), T0 + timedelta(minutes=53)) is None


def test_four_hour_cap_and_thirty_minute_quiet_contract():
    assert config.MAX_EPISODE_SECONDS == 4 * 60 * 60
    assert config.CLOSE_GAP_SECONDS == 30 * 60
    old = _episode('old', T0, T0 + timedelta(hours=3, minutes=59))
    assert timeline.choose_recorded_episode([old], T0 + timedelta(hours=4), T0 + timedelta(hours=4)) is None
    assert (
        timeline.choose_recorded_episode([old], T0 + timedelta(hours=4, seconds=1), T0 + timedelta(hours=4, seconds=1))
        is None
    )


@pytest.fixture
def timeline_store(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    store = StrictFirestore()
    # Isolate policy/storage CAS here; query semantics and real contention are
    # covered separately. This fixture is deliberately not a query emulator.
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda uid, start, finish, **kw: [
            dict(v, id=k[-1]) for k, v in store.rows.items() if len(k) == 4 and k[2] == 'episodes'
        ],
    )
    return store


def _attach(store, cid, start, end):
    return episode_timeline.attach_recorded(
        'u',
        cid,
        'omi',
        start,
        end,
        choose=timeline.choose_recorded_episode,
        new_episode=service.new_episode(
            conversation_id=cid, started_at=start, last_activity_at=end, calendar_identity=None, now=NOW
        ),
        firestore_client=store,
    )


def test_late_episode_is_closed_and_never_changes_live_pointer(timeline_store):
    store = timeline_store
    store.rows[('users', 'u', 'episode_links', 'current')] = {'episode_id': 'live'}
    store.rows[('users', 'u', 'episodes', 'live')] = episodes.seal('u', _episode('live', NOW, NOW, 'live'))
    first = _attach(store, 'old-a', T0, T0 + timedelta(seconds=20))
    second = _attach(store, 'old-b', T0 + timedelta(seconds=30), T0 + timedelta(seconds=40))
    assert first['id'] == second['id']
    assert second['status'] == 'closed'
    assert second['started_at'] == T0 and second['closed_at'] == T0 + timedelta(seconds=40)
    assert store.rows[('users', 'u', 'episode_links', 'current')] == {'episode_id': 'live'}
    assert episodes.get_episode('u', 'live', firestore_client=store)['last_activity_at'] == NOW
    assert (
        timeline.episode_owning_recorded_time('u', T0 + timedelta(seconds=5), firestore_client=store)['id']
        == first['id']
    )


def test_late_parallel_audio_can_join_live_by_recorded_overlap(timeline_store):
    store = timeline_store
    store.rows[('users', 'u', 'episodes', 'live')] = episodes.seal(
        'u', _episode('live', T0, T0 + timedelta(minutes=20), 'live')
    )
    joined = _attach(store, 'offline', T0 + timedelta(minutes=5), T0 + timedelta(minutes=6))
    assert joined['id'] == 'live' and joined['status'] == 'live'
    assert joined['last_activity_at'] == T0 + timedelta(minutes=20)


def test_live_timer_wire_is_current_episode_start_and_has_rollback(monkeypatch):
    episode = _episode('live', T0, T0, 'live')
    assert service.to_wire(episode)['timer_started_at'] == T0
    monkeypatch.setenv('EPISODE_LIVE_TIMER_START_ENABLED', 'false')
    assert service.to_wire(episode)['timer_started_at'] is None


@pytest.mark.parametrize('arrival_order', ['forward', 'reverse', 'interleaved'])
def test_morning_shape_34_fragments_replayed_through_sync_intake(monkeypatch, timeline_store, arrival_order):
    """22m recorded speech arrives 2–4h late, with a new live stamp on every fragment.

    Synthetic speech replaces private content; 29 ambiguous continuations would
    independently fail the synthetic discard scorer. A six-minute early
    silence makes two conversations; the 30m episode gap makes one occasion.
    """
    store = timeline_store
    monkeypatch.setattr(late_audio.lifecycle, 'ingest_sync_conversation', lambda uid, incoming: intake(store, incoming))
    monkeypatch.setattr(late_audio.outbox, 'mark', lambda *a, **kw: None)
    c = service.Collaborators(firestore_client=store, now=lambda: NOW)
    # No provider calls: recovery content stays in the real member conversations.
    # Exercise production repointing, including closed episodes, on each append.
    monkeypatch.setattr(service, '_record_recovered', lambda *a: 'skipped_applied')
    monkeypatch.setattr(
        episode_finalize,
        'schedule_synced_intake_attach',
        lambda uid, cid, row: service._attach_synced(uid, cid, row, c),
    )
    store.rows[('users', 'u', 'episode_links', 'current')] = {'episode_id': 'current-live'}
    store.rows[('users', 'u', 'episodes', 'current-live')] = episodes.seal(
        'u', _episode('current-live', NOW, NOW, 'live')
    )
    offsets = [0, 20] + [400 + i * 29 for i in range(32)]
    order = list(range(34))
    if arrival_order == 'reverse':
        order.reverse()
    if arrival_order == 'interleaved':
        order = order[::2] + order[1::2]
    from utils.conversations.relevance import decide_relevance
    from utils.conversations.processing_trigger import ProcessingTrigger

    def fragment_text(i):
        return (
            f'For checklist item {i}, the team agreed to review the release plan on Friday.'
            if i < 5
            else 'Coming over there in a second, and then we can carry on with that.'
        )

    calls = {'isolated': 0, 'occasion': 0}

    def relevance(texts, *, protected, slot, discard=True):
        def model(*_):
            calls[slot] += 1
            return discard

        return decide_relevance(
            trigger=ProcessingTrigger.SYNC_UPDATE,
            texts=texts,
            speech_seconds=18,
            has_photos=False,
            user_kept=False,
            exempt=False,
            trusted_wake_word=False,
            model_discards=model,
            calendar_retains=lambda: False,
            occasion_retains=lambda: protected or None,
        )

    # Identical synthetic scorer, 34 isolated assessments: 29 discards and 5 keeps.
    baseline = [relevance([fragment_text(i)], protected=False, slot='isolated', discard=i >= 5) for i in range(34)]
    assert sum(d.discard for d in baseline) == 29
    assert calls['isolated'] == 34
    for arrival, i in enumerate(order):
        captured = T0 + timedelta(seconds=offsets[i])
        uploaded = T0 + timedelta(hours=2, seconds=arrival * 220)
        row = {
            'id': f'live-stamp-{i}',
            'source': 'omi',
            'client_device_id': 'pendant',
            'started_at': captured,
            'created_at': uploaded,
            'finished_at': uploaded,
            'data_protection_level': 'standard',
        }
        segments = [
            {
                'id': f'fragment-{i}',
                'start': 0.0,
                'end': 18.0,
                'speaker_id': 0,
                'text': fragment_text(i),
            }
        ]
        assert is_late(recorded_span(captured, segments), uploaded)
        late_audio.ingest_late_transcript('u', row, segments)
    kept = [
        row for key, row in store.rows.items() if len(key) == 4 and key[2] == 'conversations' and not row.get('deleted')
    ]
    assert len(kept) == 2
    assert sum(len(row['transcript_segments']) for row in kept) == 34
    assert all(not row['discarded'] for row in kept)
    # Finalization assesses the canonical spans, not their 34 arrival fragments.
    # Episode ownership supplies context before either paid discard tier.
    from types import SimpleNamespace
    from utils.conversations.relevance_io import occasion_retention

    monkeypatch.setattr(episodes, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(service.conversations_db, 'get_firestore_client', lambda: store)
    for row in kept:
        reason = occasion_retention('u', SimpleNamespace(**row))
        assert reason == 'occasion_member'
        assert not relevance([s['text'] for s in row['transcript_segments']], protected=reason, slot='occasion').discard
    assert calls == {'isolated': 34, 'occasion': 0}  # 34 fewer discard LLM calls.
    assert sorted(s['text'] for row in kept for s in row['transcript_segments']) == sorted(
        fragment_text(i) for i in range(34)
    )
    for row in kept:
        assert row['finished_at'] == row['started_at'] + timedelta(
            seconds=max(s['end'] for s in row['transcript_segments'])
        )
        assert (row['finished_at'] - row['started_at']).total_seconds() < 22 * 60
    old = [
        row
        for key, row in store.rows.items()
        if len(key) == 4 and key[2] == 'episodes' and key[-1] != 'current-live' and not row.get('recorded_merged_into')
    ]
    assert len(old) == 1
    assert set(old[0]['conversation_ids']) == {row['id'] for row in kept}
    assert (
        sum(
            len(store.rows[('users', 'u', 'conversations', cid)]['transcript_segments'])
            for cid in old[0]['conversation_ids']
        )
        == 34
    )
    assert old[0]['status'] == 'closed' and old[0]['started_at'] == T0
    assert old[0]['last_activity_at'] == old[0]['closed_at'] == T0 + timedelta(seconds=offsets[-1] + 18)
    assert store.rows[('users', 'u', 'episode_links', 'current')] == {'episode_id': 'current-live'}
    assert episodes.get_episode('u', 'current-live', firestore_client=store)['last_activity_at'] == NOW


@pytest.fixture(scope='module')
def transcript_module():
    from routers.listen import transcripts

    return transcripts


def test_listen_persistence_uses_late_intake_before_live_writes(monkeypatch, transcript_module):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from models.conversation import Conversation
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment
    from routers.listen.transcripts import TranscriptProcessor

    store = StrictFirestore()
    monkeypatch.setattr(late_audio.lifecycle, 'ingest_sync_conversation', lambda uid, incoming: intake(store, incoming))
    monkeypatch.setattr(late_audio.outbox, 'mark', lambda *a, **kw: None)
    monkeypatch.setattr(episode_finalize, 'schedule_synced_intake_attach', lambda *a: None)
    processor = TranscriptProcessor.__new__(TranscriptProcessor)

    async def call(fn, *a, **kw):
        return fn(*a, **kw)

    processor.host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(capture_timeline_v2=False),
        persistence=SimpleNamespace(call=call),
    )
    processor.cache = SimpleNamespace(protection_level='standard')
    original = Conversation(
        id='socket-live',
        created_at=NOW,
        started_at=T0,
        finished_at=NOW,
        source='omi',
        structured=Structured(title=''),
        transcript_segments=[],
    )
    segment = TranscriptSegment(
        id='late-word',
        start=0,
        end=20,
        text='We agreed on Friday to review the test results together.',
        speaker_id=0,
        is_user=False,
    )
    saved, _, _ = asyncio.run(processor._update_live_conversation(original, [segment], [], NOW, T0))
    assert saved.id != 'socket-live'
    assert saved.started_at == T0 and saved.finished_at == T0 + timedelta(seconds=20)
    processor._deliver_segments = AsyncMock()
    asyncio.run(processor._deliver_live_updates(saved, saved.transcript_segments, [], [segment], original.id))
    processor._deliver_segments.assert_not_called()


def test_live_route_returns_authoritative_timer_without_capture_fallback(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import episodes as router
    from utils.other import endpoints as auth

    monkeypatch.setattr(router, '_admitted', lambda *a: True)
    monkeypatch.setattr(router.service, 'live_episode', lambda uid: _episode('current', T0, T0, 'live'))
    monkeypatch.setattr(router.service, 'last_closed_episode', lambda *a, **kw: None)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'synthetic'
    response = TestClient(app).get('/v1/episodes/live')
    assert response.status_code == 200
    data = response.json()
    assert data['episode']['timer_started_at'] == data['episode']['started_at'] == T0.isoformat().replace('+00:00', 'Z')


def test_recorded_quiet_close_stays_thirty_minutes_even_when_finalize_runs_late(timeline_store):
    store = timeline_store
    row = _episode('live', T0, T0, 'live')
    row['conversation_ids'] = ['c']
    store.rows[('users', 'u', 'episodes', 'live')] = episodes.seal('u', row)
    store.rows[('users', 'u', 'episode_links', 'current')] = {'episode_id': 'live'}
    c = service.Collaborators(firestore_client=store, now=lambda: NOW)
    assert service._close_for_finalize('u', row, 'c', 'capture_end', c, T0 + timedelta(minutes=15)) == 'continued'
    assert service._close_for_finalize('u', row, 'c', 'capture_end', c, NOW) == 'closed'
    closed = episodes.get_episode('u', 'live', firestore_client=store)
    assert closed['closed_at'] == T0 + timedelta(minutes=30)
    assert closed['last_activity_at'] == T0


def test_live_ownership_rotates_at_exactly_four_hours():
    live = _episode('live', T0, T0 + timedelta(hours=3, minutes=59), 'live')
    assert timeline.choose_recorded_episode([live], T0 + timedelta(hours=4), T0 + timedelta(hours=4)) is None


def test_realtime_transport_does_not_open_arrival_time_episode_for_late_speech(monkeypatch):
    import asyncio
    from utils.episodes import live

    monkeypatch.setattr(live.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(
        live.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **kw: {'started_at': T0, 'source': 'omi'}
    )
    calls = []
    monkeypatch.setattr(episode_finalize, 'schedule_synced_intake_attach', lambda *a: calls.append(a))

    def reject(*a, **kw):
        raise AssertionError('historical speech reached live tracker')

    monkeypatch.setattr(live.tracker, 'observe', reject)
    asyncio.run(
        live.on_realtime_segments('u', [{'start': 10, 'end': 20, 'text': 'Synthetic recorded speech.'}], 'c', 'omi')
    )
    assert len(calls) == 1
    assert calls[0][2]['finished_at'] == T0 + timedelta(seconds=20)


def test_recorded_origin_reads_are_bounded_and_refresh_after_one_minute(monkeypatch):
    from utils.episodes import live

    counter = live._SessionCounter(cap=2)
    clock = [0.0]
    monkeypatch.setattr(live.time, 'monotonic', lambda: clock[0])
    counter.remember_origin('u', 'a', {'started_at': T0})
    clock[0] = 59
    assert counter.recorded_origin('u', 'a') == {'started_at': T0}
    clock[0] = 60
    assert counter.recorded_origin('u', 'a') is None
    for key in ('a', 'b', 'c'):
        counter.remember_origin('u', key, {'started_at': T0})
    assert counter.recorded_origin('u', 'a') is None
    assert len(counter._origins) == 2
    counter.clear()
    assert counter.recorded_origin('u', 'c') is None


@pytest.mark.parametrize('empty', [False, True])
def test_sync_target_processing_end_never_extends_recorded_extent_or_search(empty):
    store = StrictFirestore()
    target = chunk('target', T0.timestamp())
    target.update(status='in_progress', created_at=NOW, finished_at=NOW)
    if empty:
        target['transcript_segments'] = []
    store.rows[('users', 'u', 'conversations', 'target')] = target
    # A later sync recording inside the bogus upload-time extent must stay out.
    future = chunk('unrelated', (T0 + timedelta(hours=2)).timestamp())
    future.update(sync_content_revision=1)
    store.rows[('users', 'u', 'conversations', 'unrelated')] = future
    result, _, _ = intake(store, chunk('offline', T0.timestamp() + 30), target_id='target')
    assert result['id'] == ('offline' if empty else 'target')
    assert result['finished_at'] == T0 + timedelta(seconds=39.5)
    assert len(result['transcript_segments']) == (1 if empty else 2)
    assert not store.rows[('users', 'u', 'conversations', 'unrelated')].get('deleted')
    assert 'unrelated' not in result['sync_merged_from']


def test_recorded_audio_tail_survives_later_append_and_retry():
    store = StrictFirestore()
    first = chunk('a', T0.timestamp())
    first['finished_at'] = T0 + timedelta(seconds=70)  # audio continues after last recognized word
    assert intake(store, first)[0]['finished_at'] == T0 + timedelta(seconds=70)
    second = chunk('b', T0.timestamp() + 30)
    result = intake(store, second)[0]
    assert result['finished_at'] == result['sync_recorded_end_at'] == T0 + timedelta(seconds=70)
    assert intake(store, second)[0]['finished_at'] == T0 + timedelta(seconds=70)


def test_sync_extent_rollback_restores_live_target_wall_clock(monkeypatch):
    monkeypatch.setenv('LATE_AUDIO_SYNC_INTAKE_ENABLED', 'false')
    store = StrictFirestore()
    target = chunk('target', T0.timestamp())
    target.update(status='in_progress', finished_at=NOW)
    store.rows[('users', 'u', 'conversations', 'target')] = target
    result, _, _ = intake(store, chunk('offline', T0.timestamp() + 30), target_id='target')
    assert result['finished_at'] == NOW


def test_wal_for_empty_upload_socket_joins_already_transcribed_recording():
    store = StrictFirestore()
    first, _, _ = intake(store, chunk('transcribed', T0.timestamp()))
    socket = chunk('socket', T0.timestamp())
    socket.update(status='in_progress', created_at=NOW, finished_at=NOW, transcript_segments=[])
    store.rows[('users', 'u', 'conversations', 'socket')] = socket
    row, created, _ = intake(store, chunk('wal', T0.timestamp() + 30), target_id='socket')
    assert row['id'] == first['id'] and not created
    assert len(row['transcript_segments']) == 2
    assert row['finished_at'] == T0 + timedelta(seconds=39.5)
    assert store.rows[('users', 'u', 'conversations', 'socket')]['transcript_segments'] == []


def test_stale_capture_origin_cannot_bind_old_wal_to_new_live_speech():
    store = StrictFirestore()
    target = chunk('live', T0.timestamp())
    target.update(status='in_progress', created_at=NOW, finished_at=NOW + timedelta(seconds=10))
    target['transcript_segments'][0].update(start=4 * 3600, end=4 * 3600 + 10)
    store.rows[('users', 'u', 'conversations', 'live')] = target
    result, _, _ = intake(store, chunk('old', T0.timestamp() + 30), target_id='live')
    assert result['id'] == 'old'
    assert result['finished_at'] == T0 + timedelta(seconds=39.5)
    assert store.rows[('users', 'u', 'conversations', 'live')]['transcript_segments'] == target['transcript_segments']


def test_five_hour_offline_capture_forms_two_capped_closed_windows(timeline_store):
    store = timeline_store
    row = _attach(store, 'long', T0, T0 + timedelta(hours=5))
    windows = row['_recorded_windows']
    assert len(windows) == 2
    assert windows[0]['close_reason'] == 'hard_cap' and windows[1]['close_reason'] == 'gap'
    assert [(w['started_at'], w['last_activity_at']) for w in windows] == [
        (T0, T0 + timedelta(hours=4)),
        (T0 + timedelta(hours=4), T0 + timedelta(hours=5)),
    ]
    assert all(w['status'] == 'closed' and w['conversation_ids'] == ['long'] for w in windows)
    retry = _attach(store, 'long', T0, T0 + timedelta(hours=5))
    assert [w['id'] for w in retry['_recorded_windows']] == [w['id'] for w in windows]
    assert (
        timeline.episode_owning_recorded_time('u', T0 + timedelta(hours=4, minutes=30), firestore_client=store)['id']
        == windows[1]['id']
    )
    assert ('users', 'u', 'episode_links', 'current') not in store.rows


def test_late_append_rotates_at_existing_episode_start_plus_four_hours(timeline_store):
    store = timeline_store
    _attach(store, 'earlier', T0, T0 + timedelta(minutes=20))
    row = _attach(store, 'continued', T0 + timedelta(minutes=20), T0 + timedelta(hours=4, minutes=10))
    windows = row['_recorded_windows']
    assert len(windows) == 2
    assert windows[0]['last_activity_at'] == windows[1]['started_at'] == T0 + timedelta(hours=4)
    assert windows[1]['last_activity_at'] == T0 + timedelta(hours=4, minutes=10)


def test_capped_recovery_places_each_segment_once_and_keeps_unplaced_content(timeline_store):
    from utils.episodes.recorded_recovery import record_windows

    store = timeline_store
    placed = _attach(store, 'long', T0, T0 + timedelta(hours=5))
    row = dict(
        started_at=T0,
        finished_at=T0 + timedelta(hours=5),
        source='omi',
        transcript_segments=[
            dict(id='before', start=4 * 3600 - 10, end=4 * 3600 + 10, text='Words across the cap.'),
            dict(id='after', start=4 * 3600 + 30, end=4 * 3600 + 40, text='Words in the next window.'),
            dict(id='unknown', start=-1, end=-1, audio_alignment='unplaced', text='Unplaced words are retained.'),
        ],
    )
    seen = []

    def record(uid, moment, c, *, member_episode_id):
        seen.append((member_episode_id, moment))
        return 'applied'

    assert (
        record_windows('u', 'long', row, placed['_recorded_windows'], None, record, now=T0 + timedelta(hours=8))
        == 'applied'
    )
    first, second = placed['_recorded_windows']
    assert {s['id'] for eid, moment in seen if eid == first['id'] for s in moment.segments} == {'before', 'unknown'}
    assert {s['id'] for eid, moment in seen if eid == second['id'] for s in moment.segments} == {'after'}
    assert len([s for _, moment in seen for s in moment.segments]) == 3
    assert seen[0][1].ended_at <= T0 + timedelta(hours=4)


def test_capped_donor_repoint_preserves_every_historical_window(timeline_store):
    store = timeline_store
    placed = _attach(store, 'donor', T0, T0 + timedelta(hours=5))
    c = service.Collaborators(firestore_client=store, now=lambda: T0 + timedelta(hours=8))
    service._repoint_sync_donors('u', 'survivor', {'sync_merged_from': ['donor']}, c)
    for window in placed['_recorded_windows']:
        stored = episodes.get_episode('u', window['id'], firestore_client=store)
        assert stored['conversation_ids'] == ['survivor']
        assert stored['status'] == 'closed'


def test_recorded_idle_close_cannot_extend_beyond_four_hour_cap():
    row = _episode('e', T0, T0 + timedelta(hours=4), 'live')
    assert service._idle_closed_at(row, T0 + timedelta(hours=8)) == T0 + timedelta(hours=4)


def test_only_fresh_live_speech_resumes_a_silence_closed_historical_occasion(timeline_store):
    store = timeline_store
    original = _attach(store, 'offline', T0, T0 + timedelta(minutes=20))
    c = service.Collaborators(firestore_client=store, now=lambda: T0 + timedelta(minutes=21))
    assert service._attach_once('u', 'live', 'omi', T0 + timedelta(minutes=21), c) == 'joined'
    owner = episodes.get_current_episode('u', firestore_client=store)
    assert owner['id'] == original['id'] and owner['started_at'] == T0
    assert owner['last_activity_at'] == T0 + timedelta(minutes=21)


def test_direct_late_attach_cannot_open_or_resume_a_live_episode(timeline_store):
    store = timeline_store
    c = service.Collaborators(firestore_client=store, now=lambda: T0 + timedelta(minutes=10))
    assert service._attach_once('u', 'offline', 'omi', T0, c) == 'recorded'
    assert episodes.get_current_episode('u', firestore_client=store) is None
    assert service._attach_once('u', 'offline-2', 'omi', T0 + timedelta(minutes=1), c) == 'recorded'
    assert episodes.get_current_episode('u', firestore_client=store) is None


def test_invalid_unbounded_capture_fails_before_any_timeline_write(timeline_store):
    store = timeline_store
    with pytest.raises(episodes.EpisodeConflict, match='recorded_capture_window_exhausted'):
        _attach(store, 'invalid', T0, T0 + timedelta(days=365))
    assert store.rows == {}


def test_long_fresh_batch_uses_recorded_end_to_determine_liveness(timeline_store):
    store = timeline_store
    ended = T0 + timedelta(minutes=3)
    c = service.Collaborators(firestore_client=store, now=lambda: ended, tz_name='UTC')
    assert service._attach_once('u', 'fresh', 'omi', T0, c, ended_at=ended) == 'opened'
    assert episodes.get_current_episode('u', firestore_client=store)['started_at'] == T0


def test_first_sync_finalization_reconciles_all_capped_windows(monkeypatch, timeline_store):
    store = timeline_store
    row = dict(
        started_at=T0,
        finished_at=T0 + timedelta(hours=5),
        source='omi',
        transcript_segments=[
            dict(id=f's{i}', start=i * 60, end=i * 60 + 18, text='We agreed to review the release plan on Friday.')
            for i in range(300)
        ],
    )
    c = service.Collaborators(firestore_client=store, now=lambda: T0 + timedelta(hours=8))
    monkeypatch.setattr(service, '_record_recovered', lambda *a: 'skipped_applied')
    seen = []
    monkeypatch.setattr(service, '_reconcile', lambda uid, episode, *a: seen.append(episode['id']) or 'finalized')
    assert service._on_finalized('u', 'long', row, 'sync_update', None, c) == 'finalized'
    assert len(seen) == len(set(seen)) == 2
    assert set(seen) == {e['id'] for e in episode_timeline.member_episodes('u', 'long', firestore_client=store)}


def test_fresh_capture_after_user_close_opens_a_new_occasion(timeline_store):
    store = timeline_store
    old = _attach(store, 'old', T0, T0 + timedelta(minutes=20))
    raw = store.rows[('users', 'u', 'episodes', old['id'])]
    raw['close_reason'] = 'user'
    c = service.Collaborators(firestore_client=store, now=lambda: T0 + timedelta(minutes=21), tz_name='UTC')
    assert service._attach_once('u', 'fresh', 'omi', T0 + timedelta(minutes=21), c) == 'opened'
    assert episodes.get_current_episode('u', firestore_client=store)['id'] != old['id']
    assert episodes.get_episode('u', old['id'], firestore_client=store)['status'] == 'closed'
