"""Shared meeting evidence retains its storage and polling guarantees."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.boundary_evidence import BoundarySignal
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes import boundaries, boundary_store

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ACCOUNT = 'fixture-owner-39'


@pytest.fixture
def store(monkeypatch):
    # Signal retention must use the same clock as the fixed recorded fixtures.
    monkeypatch.setattr(boundary_store, 'datetime', SimpleNamespace(now=lambda tz: NOW))
    db = StrictFirestore()
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


@pytest.mark.asyncio
async def test_calendar_poll_is_bounded():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from routers.listen.boundary_poll import poll_calendar

    controller = SimpleNamespace(clock=lambda: NOW, _active_calendar_meeting=AsyncMock())
    await poll_calendar(controller)
    await poll_calendar(controller)
    assert controller._active_calendar_meeting.await_count == 1
    controller.clock = lambda: NOW + timedelta(seconds=60)
    await poll_calendar(controller)
    assert controller._active_calendar_meeting.await_count == 2


def test_full_index_evicts_old_terminal_edges_but_preserves_active_signals(store):
    current = NOW
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


def test_seven_day_retention_evicts_expired_edges_with_the_explicit_store_clock(store):
    expired = signal(ended_at=NOW - timedelta(days=8)).model_copy(update={'started_at': NOW - timedelta(days=9)})
    boundary_store.record(ACCOUNT, [expired], firestore_client=store)
    assert boundary_store.signal_id(expired) not in boundary_store.windows(ACCOUNT, firestore_client=store)
    fresh = signal(ended_at=NOW + timedelta(minutes=20)).model_copy(update={'external_id': 'fresh-retention'})
    boundary_store.record(ACCOUNT, [fresh], firestore_client=store)
    assert boundary_store.signal_id(fresh) in boundary_store.windows(ACCOUNT, firestore_client=store)


def test_shared_reads_and_context_ingest_are_bounded_to_sixty_seconds(store, monkeypatch):
    from cachetools import TTLCache
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    clock = [0.0]
    monkeypatch.setattr(boundary_store, '_recent_windows', TTLCache(maxsize=8, ttl=60, timer=lambda: clock[0]))
    monkeypatch.setattr(boundary_store, '_seen_contexts', TTLCache(maxsize=8, ttl=60, timer=lambda: clock[0]))
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
    for _ in range(12):
        boundaries.ingest_context(ACCOUNT, row['external_data']['calendar_meeting_context'], firestore_client=store)
        assert boundary_store.windows(ACCOUNT, firestore_client=store)
    assert len(store.transactions) == 1
    assert len(reads) == 4  # deletion, state, payload, then one cached window read
    clock[0] = 61
    boundaries.ingest_context(ACCOUNT, row['external_data']['calendar_meeting_context'], firestore_client=store)
    assert boundary_store.windows(ACCOUNT, firestore_client=store)
    assert len(store.transactions) == 2
    assert len(reads) == 8


def test_shared_cache_is_owner_scoped_and_invalidated_by_writes(store):
    assert boundary_store.windows(ACCOUNT, firestore_client=store) == {}
    boundary_store.record(ACCOUNT, [signal()], firestore_client=store)
    assert len(boundary_store.windows(ACCOUNT, firestore_client=store)) == 1
    assert boundary_store.windows('another-synthetic-owner', firestore_client=store) == {}
    other = StrictFirestore()
    assert boundary_store.windows(ACCOUNT, firestore_client=other) == {}
    store.rows[('users', ACCOUNT, 'capture_boundary_state', 'v1')] = {'entries': {}}
    assert len(boundary_store.windows(ACCOUNT, firestore_client=store)) == 1


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
    'uid,stored',
    [('fixture-owner-39', True), ('fixture-owner-0', False)],
)
def test_shared_call_and_relevance_inputs_keep_the_production_sample(store, monkeypatch, uid, stored):
    from utils.conversations import call_metadata, relevance_media

    evidence = signal(ended_at=NOW + timedelta(minutes=20), meeting_link='https://meet.google.com/abc-defg-hij')
    assert boundary_store.record(uid, [evidence], firestore_client=store) == int(stored)
    assert relevance_media._boundaries(uid) == ([evidence] if stored else [])

    monkeypatch.setenv(call_metadata.FLAG, 'serve')
    conversation = SimpleNamespace(started_at=NOW, finished_at=NOW + timedelta(minutes=10), is_call=None)
    call_metadata.apply_call_metadata(uid, conversation)
    assert conversation.is_call is (True if stored else None)
    if stored:
        assert conversation.calendar_event_id == evidence.external_id
