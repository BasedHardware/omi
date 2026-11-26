"""A recording whose closure Firestore rejects for size must not freeze the owner's backlog (SCA-2918)."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import Conflict, UnlockedPage, outline, planner, service
from tests.unit.test_conversations_v3_claim_growth import UID, strict  # noqa: F401
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, source

C = '/users/u/conversations/'
LEASE = '/users/u/conversation_v3_leases/builder'


def backlog(n=3):
    rows = {}
    for i in range(n):
        start = AT + timedelta(hours=i)
        rows[C + f'r{i}'] = source(
            f'r{i}', started_at=start, finished_at=start + timedelta(seconds=10), v3_pending_since=start
        )
    return rows


def test_a_size_park_sets_its_one_seed_aside_and_runs_the_next_seed_without_the_backoff(strict):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    assert store.record_blocked(UID, token, 'document_too_large', quarantine='r0', firestore_client=strict)
    held = strict.rows[leases.lease_ref(strict, UID, 'builder').path]
    assert held[store.SIZE_QUARANTINE_FIELD] == ['r0']
    # Re-armed early attempt: the backoff does not hold the backlog behind the set-aside seed.
    assert store.backoff_state(UID, firestore_client=strict) == (None, 'document_too_large')
    store.mark_bounded_attempt(UID, token, firestore_client=strict)
    assert store.backoff_state(UID, firestore_client=strict)[0] is not None
    # The same seed is not listed twice, and a repeat spends the usual backoff.
    assert store.record_blocked(UID, token, 'document_too_large', quarantine='r0', firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['r0']
    assert store.backoff_state(UID, firestore_client=strict)[0] is not None


def test_the_quarantine_is_bounded_and_only_for_size_parks(strict, monkeypatch):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    held = strict.rows[leases.lease_ref(strict, UID, 'builder').path]
    assert store.record_blocked(UID, token, 'v3_derived_budget', quarantine='r0', firestore_client=strict)
    assert store.SIZE_QUARANTINE_FIELD not in held
    monkeypatch.setattr(store, 'SIZE_QUARANTINE_MAX', 2)
    for rid in ('r0', 'r1', 'r2'):
        store.record_blocked(UID, token, 'document_too_large', quarantine=rid, firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['r0', 'r1']
    assert store.backoff_state(UID, firestore_client=strict)[0] is not None  # A full list backs off as before.
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'off')
    store.record_blocked(UID, token, 'document_too_large', quarantine='r3', firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['r0', 'r1']


@pytest.mark.parametrize('enabled', [True, False])
def test_a_bounded_load_seeds_past_a_quarantined_oldest_recording(monkeypatch, enabled):
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'on' if enabled else 'off')
    rows = backlog()
    rows[LEASE] = {store.SIZE_QUARANTINE_FIELD: ['r0']}
    page = UnlockedPage()
    recordings, _existing, _cache = store.load(
        'u', pending_limit=1, unlocked_page=page, firestore_client=MemoryQuery(rows)
    )
    seed = 'r1' if enabled else 'r0'
    assert list(recordings) == [seed]
    assert page.pending_ids == (seed,) and page.seeds == (1, 0)
    assert page.quarantined == (frozenset({'r0'}) if enabled else frozenset())


def test_on_open_and_unpaged_loads_ignore_the_quarantine():
    rows = backlog()
    rows[LEASE] = {store.SIZE_QUARANTINE_FIELD: ['r0']}
    recordings, _existing, _cache = store.load('u', pending_limit=1, firestore_client=MemoryQuery(rows))
    assert list(recordings) == ['r0']


@pytest.mark.parametrize(
    'seeded,unlocked,expected',
    [(('r0',), 0, 'r0'), (('r0',), 1, None), (('r0', 'r1'), 0, None)],
)
def test_only_a_lone_pending_seed_is_set_aside(seeded, unlocked, expected):
    page = UnlockedPage(seeds=(len(seeded), unlocked), pending_ids=seeded)
    assert service._size_quarantine_seed('document_too_large', 1, page) == expected
    assert service._size_quarantine_seed('v3_derived_budget', 1, page) is None
    assert service._size_quarantine_seed('document_too_large', 8, page) is None


def _pass(monkeypatch, commit):
    """One live builder pass with a bounded one-seed load of ``r0`` and ``r1`` set aside earlier."""
    window_rows = backlog(1)
    recordings = {'r0': {**window_rows[C + 'r0'], '_v3_revision': 1}}
    parked = []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def load(*a, unlocked_page=None, **kw):
        unlocked_page.seeds, unlocked_page.pending_ids = (1, 0), ('r0',)
        unlocked_page.quarantined = frozenset({'r1'})
        return recordings, {}, []

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(leases, 'acquire', lambda *a, promote_llm=False: 'token')
    monkeypatch.setattr(leases, 'renew', lambda *a: None)
    monkeypatch.setattr(leases, 'release', lambda *a: None)
    for name, fake in {
        'outline_attempt': lambda *a, **kw: True,
        'save_outline': lambda *a, **kw: None,
        'adoptable': lambda *a: {},
        'merge_donors_have_tasks': lambda *a, **kw: False,
        'backoff_state': lambda *a: (None, 'document_too_large'),
        'clear_terminal_pending': lambda *a: None,
        'mark_bounded_attempt': lambda *a: None,
        'load': load,
        'record_blocked': lambda *a, **kw: parked.append((a, kw)),
    }.items():
        monkeypatch.setattr(store, name, fake)
    monkeypatch.setattr(service, '_commit', commit)
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: None)
    monkeypatch.setattr(service, 'drain_processing', AsyncMock())
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda uid, prompt: '{"conversations":[{"first_line":1,"title":"A plan","line":"A plan.","kind":"conversation"}]}',
    )
    return parked


@pytest.mark.asyncio
async def test_a_one_seed_size_rejection_parks_with_that_seed_set_aside(monkeypatch):
    def commit(*a, **kw):
        raise Conflict('document_too_large')

    parked = _pass(monkeypatch, commit)
    assert await service.reconcile('u') == 'blocked'
    ((args, kwargs),) = parked
    assert args[2] == 'document_too_large' and kwargs['quarantine'] == 'r0'


@pytest.mark.asyncio
async def test_set_aside_recordings_do_not_keep_the_pass_chain_hot(monkeypatch):
    seen = []
    _pass(monkeypatch, lambda *a, **kw: set())
    monkeypatch.setattr(service, 'has_pending', lambda uid, skip=(): seen.append(set(skip)) or bool(set() - set(skip)))
    assert await service.reconcile('u') == 'committed'
    assert seen == [{'r1'}]


def _with_audio(legacy):
    segments = [{'id': '0', 'start': 0, 'end': 1, 'text': 'speech ' * 30}]
    audio = {'id': 'f', 'duration': 60, 'chunk_timestamps': [AT.timestamp()], 'legacy_ids': legacy}
    return {'id': 'r', 'started_at': AT, 'transcript_segments': segments, 'audio_files': [audio]}


@pytest.mark.parametrize('enabled', [True, False])
def test_recording_aliases_leave_out_superseded_source_file_ids(monkeypatch, enabled):
    monkeypatch.setenv('CONVERSATIONS_V3_ALIAS_SLIM', 'on' if enabled else 'off')
    raw = _with_audio(['old-%d' % i for i in range(128)])
    groups = outline.stretches([raw], AT + timedelta(minutes=10))
    entry = {'first_line': 1, 'title': 'Topic', 'line': '', 'kind': 'conversation'}
    (window,) = planner.windows(groups, [[entry]])
    (alias,) = planner.build('synthetic', window, {'r': raw})['audio_files']
    assert alias['recording_id'] == 'r' and alias['recording_file_id'] == 'f'
    assert alias['chunk_timestamps'] == [AT.timestamp()]  # Playback and the model still read these.
    assert ('legacy_ids' in alias) is not enabled
    assert raw['audio_files'][0]['legacy_ids']  # The source recording keeps its own aliases.
