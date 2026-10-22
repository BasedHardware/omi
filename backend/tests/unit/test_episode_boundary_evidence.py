"""Meeting edges are shared by storage, conversation, episode and merge policy."""

from datetime import datetime, timedelta, timezone

import pytest

from models.boundary_evidence import BoundarySignal
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes import boundaries, boundary_store, boundary_runtime, policy, service

NOW = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
ACCOUNT = 'test-account'


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE_SHADOW_PERCENT', '100')
    db = StrictFirestore()
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'serve')
    monkeypatch.setattr(boundary_store, 'get_firestore_client', lambda: db)
    return db


def signal(**updates):
    return BoundarySignal(kind='calendar_event', external_id='event-test', started_at=NOW, **updates)


def test_evidence_is_idempotent_and_late_retry_cannot_reopen(store):
    assert boundary_store.record(ACCOUNT, [signal()], firestore_client=store) == 1
    assert boundary_store.record(ACCOUNT, [signal()], firestore_client=store) == 0
    closed = signal(ended_at=NOW + timedelta(minutes=20))
    assert boundary_store.record(ACCOUNT, [closed], firestore_client=store) == 1
    assert boundary_store.record(ACCOUNT, [signal()], firestore_client=store) == 0
    windows = boundary_store.windows(ACCOUNT, firestore_client=store)
    assert next(iter(windows.values()))['ended_at'] == closed.ended_at
    assert boundary_store.load(ACCOUNT, list(windows), firestore_client=store) == [closed]
    payloads = [row for path, row in store.rows.items() if path[-2] == 'capture_boundary_signals']
    assert 'external_id' not in payloads[0]
    moved = signal().model_copy(
        update={'started_at': NOW + timedelta(minutes=1), 'ended_at': NOW + timedelta(minutes=40)}
    )
    assert boundary_store.record(ACCOUNT, [moved], firestore_client=store) == 1
    assert boundary_store.load(ACCOUNT, [boundary_store.signal_id(moved)], firestore_client=store) == [moved]


@pytest.mark.parametrize(
    'mode,closes,merges', [('serve', 'close', False), ('shadow', 'legacy', True), ('off', 'legacy', True)]
)
def test_boundary_closes_conversation_and_fences_merge_only_in_serve(store, monkeypatch, mode, closes, merges):
    boundary_store.record(ACCOUNT, [signal()], firestore_client=store)
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', mode)
    left = {'started_at': NOW - timedelta(minutes=5), 'finished_at': NOW}
    right = {'started_at': NOW + timedelta(minutes=1)}
    assert boundaries.conversation_decision(ACCOUNT, left, NOW + timedelta(seconds=1), firestore_client=store) == closes
    assert boundaries.merge_allowed(ACCOUNT, left, right, firestore_client=store) is merges


def test_no_split_inside_a_signal_but_end_and_quiet_are_hard(store):
    boundary_store.record(ACCOUNT, [signal(ended_at=NOW + timedelta(minutes=30))], firestore_client=store)
    row = {'started_at': NOW, 'finished_at': NOW + timedelta(minutes=10)}
    assert boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(minutes=11), firestore_client=store) == 'hold'
    assert (
        boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(minutes=25), firestore_client=store) == 'close'
    )
    row['finished_at'] = NOW + timedelta(minutes=29)
    assert (
        boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(minutes=30), firestore_client=store) == 'close'
    )


def test_episode_start_closes_previous_and_opens_meeting_without_model_call(store, monkeypatch):
    boundary_store.record(ACCOUNT, [signal()], firestore_client=store)
    assert callable(service.new_episode)  # Warm the existing model stack during collection, outside the call budget.
    previous = {'id': 'episode-test', 'started_at': NOW - timedelta(minutes=10)}
    changes = []
    monkeypatch.setattr(boundary_runtime.episodes_db, 'get_current_episode', lambda *a, **k: previous)
    monkeypatch.setattr(boundary_runtime.episodes_db, 'close_episode', lambda *a, **k: changes.append(('close', a[2])))
    monkeypatch.setattr(boundary_runtime.episodes_db, 'commit_moment', lambda *a, **k: changes.append(('open', k)))
    assert boundary_runtime.apply_signal_edges(ACCOUNT, now=NOW, firestore_client=store) == 'opened'
    assert changes[0] == ('close', 'boundary')
    assert changes[1][1]['new_episode']['started_at'] == NOW
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'shadow')
    changes.clear()
    assert boundary_runtime.apply_signal_edges(ACCOUNT, now=NOW, firestore_client=store) == 'shadow'
    assert changes == []


def test_episode_policy_holds_even_if_legacy_would_split_inside_meeting(store):
    boundary_store.record(ACCOUNT, [signal()], firestore_client=store)
    facts = policy.MomentFacts('conversation-test', 'omi', NOW + timedelta(minutes=2), NOW + timedelta(minutes=3))
    chosen = boundary_runtime.decision(
        ACCOUNT, {'started_at': NOW}, facts, policy.Boundary('close', 'hard_cap'), firestore_client=store
    )
    assert chosen.action == 'continue'


def test_calendar_and_screen_context_produce_signals():
    context = {'start_time': NOW.isoformat(), 'duration_minutes': 30, 'calendar_event_id': 'event-test'}
    calendar = boundaries.context_signal(context)
    assert calendar.kind == 'calendar_event'
    assert calendar.ended_at == NOW + timedelta(minutes=30)
    assert boundaries.context_signal({**context, 'calendar_source': 'screen_activity'}).kind == 'screen_meeting'


def test_distinct_screen_windows_get_distinct_identities():
    first = {'start_time': NOW.isoformat(), 'duration_minutes': 30, 'calendar_event_id': 'screen-activity'}
    later = {**first, 'start_time': (NOW + timedelta(hours=3)).isoformat()}
    for extra in ({}, {'calendar_source': 'screen_activity'}):
        a = boundaries.context_signal({**first, **extra})
        b = boundaries.context_signal({**later, **extra})
        assert a.external_id is None and b.external_id is None
        assert boundary_store.signal_id(a) != boundary_store.signal_id(b)
    calendar = boundaries.context_signal({**first, 'calendar_event_id': 'event-test'})
    assert calendar.external_id == 'event-test'


def test_account_erasure_fences_new_evidence(store):
    store.rows[('account_deletions', ACCOUNT)] = {'wipe_status': 'pending'}
    assert boundary_store.record(ACCOUNT, [signal()], firestore_client=store) == 0
    assert len(store.rows) == 1


def test_quiet_rule_ends_the_signal_so_later_ambient_capture_is_not_a_meeting(store):
    boundary_store.record(ACCOUNT, [signal()], firestore_client=store)
    row = {'started_at': NOW, 'finished_at': NOW + timedelta(minutes=1)}
    assert (
        boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(minutes=16), firestore_client=store) == 'close'
    )
    known = boundary_store.windows(ACCOUNT, firestore_client=store)
    assert boundaries.active(known, NOW + timedelta(minutes=17)) == []
    later = {'started_at': NOW + timedelta(minutes=17), 'finished_at': NOW + timedelta(minutes=18)}
    assert (
        boundaries.conversation_decision(ACCOUNT, later, NOW + timedelta(minutes=19), firestore_client=store)
        == 'legacy'
    )


@pytest.mark.asyncio
async def test_calendar_poll_is_bounded_and_off_mode_does_no_lookup(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from routers.listen.boundary_poll import poll_calendar

    controller = SimpleNamespace(clock=lambda: NOW, _active_calendar_meeting=AsyncMock())
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'shadow')
    await poll_calendar(controller)
    await poll_calendar(controller)
    assert controller._active_calendar_meeting.await_count == 1
    controller.clock = lambda: NOW + timedelta(seconds=60)
    await poll_calendar(controller)
    assert controller._active_calendar_meeting.await_count == 2
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'off')
    controller.clock = lambda: NOW + timedelta(seconds=120)
    await poll_calendar(controller)
    assert controller._active_calendar_meeting.await_count == 2


@pytest.mark.asyncio
async def test_off_mode_never_offloads_boundary_storage(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from routers.listen.boundary_poll import conversation_action, merge_permitted, ingest_calendar

    controller = SimpleNamespace(host=SimpleNamespace(persistence=SimpleNamespace(call=AsyncMock())))
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'off')
    assert await conversation_action(controller, {}) == 'legacy'
    assert await merge_permitted(controller, {})
    await ingest_calendar(controller, {})
    controller.host.persistence.call.assert_not_awaited()


def test_full_index_evicts_old_terminal_edges_but_preserves_active_signals(store):
    current = datetime.now(timezone.utc)
    state = ('users', ACCOUNT, 'capture_boundary_state', 'v1')
    store.rows[state] = {
        'entries': {
            f'old-{i:03}': {'started_at': current - timedelta(hours=6), 'ended_at': current - timedelta(hours=5)}
            for i in range(boundary_store.MAX_SIGNALS)
        }
    }
    fresh = BoundarySignal(kind='phone_call', external_id='fresh-test', started_at=current)
    assert boundary_store.record(ACCOUNT, [fresh], firestore_client=store) == 1
    known = boundary_store.windows(ACCOUNT, firestore_client=store)
    assert len(known) == boundary_store.MAX_SIGNALS
    assert boundary_store.signal_id(fresh) in known
    assert 'old-000' not in known


def test_shadow_tick_reads_and_context_ingest_are_bounded_to_sixty_seconds(store, monkeypatch):
    from cachetools import TTLCache
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    clock = [0.0]
    monkeypatch.setattr(boundary_store, '_shadow_windows', TTLCache(maxsize=8, ttl=60, timer=lambda: clock[0]))
    monkeypatch.setattr(boundary_store, '_seen_contexts', TTLCache(maxsize=8, ttl=60, timer=lambda: clock[0]))
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'shadow')
    original = StrictFirestoreDocument.get
    reads = []

    def counted(ref, *args, **kwargs):
        reads.append(ref.path)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    row = {
        'started_at': NOW,
        'finished_at': NOW,
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'context',
                'start_time': NOW.isoformat(),
                'duration_minutes': 30,
            }
        },
    }
    for tick in range(12):
        assert (
            boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(seconds=tick * 5), firestore_client=store)
            == 'legacy'
        )
    assert len(store.transactions) == 1
    assert len(reads) == 4  # deletion, state, payload, then one cached window read
    clock[0] = 61
    boundaries.conversation_decision(ACCOUNT, row, NOW + timedelta(seconds=61), firestore_client=store)
    assert len(store.transactions) == 2
    assert len(reads) == 8


def test_shadow_cache_is_owner_scoped_invalidated_by_writes_and_bypassed_in_serve(store, monkeypatch):
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'shadow')
    assert boundary_store.windows(ACCOUNT, firestore_client=store) == {}
    boundary_store.record(ACCOUNT, [signal()], firestore_client=store)
    assert len(boundary_store.windows(ACCOUNT, firestore_client=store)) == 1
    assert boundary_store.windows('another-synthetic-owner', firestore_client=store) == {}
    other = StrictFirestore()
    assert boundary_store.windows(ACCOUNT, firestore_client=other) == {}
    store.rows[('users', ACCOUNT, 'capture_boundary_state', 'v1')] = {'entries': {}}
    assert len(boundary_store.windows(ACCOUNT, firestore_client=store)) == 1
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'serve')
    assert boundary_store.windows(ACCOUNT, firestore_client=store) == {}


def test_noncalendar_start_is_still_immutable(store):
    original = signal().model_copy(update={'kind': 'desktop_meeting'})
    boundary_store.record(ACCOUNT, [original], firestore_client=store)
    with pytest.raises(ValueError, match='immutable'):
        boundary_store.record(
            ACCOUNT, [original.model_copy(update={'started_at': NOW + timedelta(seconds=1)})], firestore_client=store
        )


def test_saved_context_cannot_rewind_an_authoritative_calendar_reschedule(store):
    original = {'calendar_event_id': 'scheduled', 'start_time': NOW.isoformat(), 'duration_minutes': 30}
    moved = {**original, 'start_time': (NOW + timedelta(minutes=10)).isoformat()}
    boundaries.ingest_context(ACCOUNT, original, firestore_client=store)
    boundaries.ingest_context(ACCOUNT, moved, firestore_client=store, allow_reschedule=True)
    boundaries.ingest_context(ACCOUNT, original, firestore_client=store)
    key = boundary_store.signal_id(boundaries.context_signal(original))
    assert boundary_store.load(ACCOUNT, [key], firestore_client=store)[0].started_at == NOW + timedelta(minutes=10)


@pytest.mark.parametrize(
    'mode,sample,writes', [('off', '100', 0), ('shadow', '0', 0), ('shadow', '100', 1), ('serve', '0', 1)]
)
def test_boundary_shadow_writes_are_sampled(store, monkeypatch, mode, sample, writes):
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', mode)
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE_SHADOW_PERCENT', sample)
    assert boundary_store.record(ACCOUNT, [signal()], firestore_client=store) == writes
    assert bool(store.rows) == bool(writes)
