"""A recording whose closure Firestore rejects for size must not freeze the owner's backlog (SCA-2918)."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import InvalidArgument

from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import Conflict, UnlockedPage, service
from tests.unit.test_conversations_v3_claim_growth import UID, strict  # noqa: F401
from tests.unit.test_conversations_v3_derived_budget import claim, derived
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


def test_a_size_park_sets_its_closure_aside_and_runs_the_next_seed_without_the_backoff(strict):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    held = strict.rows[leases.lease_ref(strict, UID, 'builder').path]
    assert store.record_blocked(UID, token, 'document_too_large', quarantine=('a', 'b'), firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    # Re-armed early attempt: the backoff does not hold the backlog outside the set-aside closure.
    assert store.backoff_state(UID, firestore_client=strict) == (None, 'document_too_large')
    store.mark_bounded_attempt(UID, token, firestore_client=strict)
    assert store.backoff_state(UID, firestore_client=strict)[0] is not None
    # Nothing new to set aside: the park spends the usual backoff.
    assert store.record_blocked(UID, token, 'document_too_large', quarantine=('b',), firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert store.backoff_state(UID, firestore_client=strict)[0] is not None
    assert store.size_quarantined(UID, firestore_client=strict) == {'a', 'b'}


def test_the_quarantine_is_bounded_all_or_nothing_and_only_for_size_parks(strict, monkeypatch):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    held = strict.rows[leases.lease_ref(strict, UID, 'builder').path]
    assert store.record_blocked(UID, token, 'v3_derived_budget', quarantine=('a',), firestore_client=strict)
    assert store.SIZE_QUARANTINE_FIELD not in held
    monkeypatch.setattr(store, 'SIZE_QUARANTINE_MAX', 3)
    store.record_blocked(UID, token, 'document_too_large', quarantine=('a', 'b'), firestore_client=strict)
    # A closure that no longer fits is not split: none of it is set aside and the owner backs off as before.
    store.record_blocked(UID, token, 'document_too_large', quarantine=('c', 'd'), firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert store.backoff_state(UID, firestore_client=strict)[0] is not None
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'off')
    store.record_blocked(UID, token, 'document_too_large', quarantine=('e',), firestore_client=strict)
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert store.size_quarantined(UID, firestore_client=strict) == frozenset()


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
    [(('r0',), 0, ('r0', 'r1')), (('r0',), 1, ()), (('r0', 'r2'), 0, ())],
)
def test_a_lone_pending_seed_sets_aside_every_pending_source_of_its_closure(seeded, unlocked, expected):
    page = UnlockedPage(seeds=(len(seeded), unlocked), pending_ids=seeded)
    recordings = {'r0': {'v3_pending': True}, 'r1': {'v3_pending': True}, 'settled': {'v3_pending': False}}
    assert service._size_quarantine('document_too_large', 1, page, recordings) == expected
    assert service._size_quarantine('v3_derived_budget', 1, page, recordings) == ()
    assert service._size_quarantine('document_too_large', 8, page, recordings) == ()


class TxMemory(MemoryQuery):
    """MemoryQuery plus the point-transaction surface record_blocked, mark_bounded_attempt and
    clear_terminal_pending use, so the real lease state machine runs against the same rows as load."""

    def copy(self, **kw):
        fields = dict(
            rows=self.rows,
            path=self.path,
            filters=self.filters,
            orders=self.orders,
            cap=self.cap,
            after=self.after,
            calls=self.calls,
            projection=self.projection,
        )
        return TxMemory(**(fields | kw))

    def get(self, transaction=None):
        return super().get()

    def update(self, data):
        self.rows.setdefault(self.path, {}).update(deepcopy(data))


class Tx:
    def update(self, ref, data):
        ref.update(data)


def three_seeds():
    """``a`` and ``b`` share the oversize claimant ``da``; ``c`` hours later is independent."""
    now = datetime.now(timezone.utc)
    rows = {
        C + 'a': source('a', started_at=AT, claims=[claim('da', AT, 10)], v3_pending_since=AT),
        C
        + 'b': source(
            'b',
            started_at=AT + timedelta(seconds=20),
            finished_at=AT + timedelta(seconds=30),
            claims=[claim('da', AT + timedelta(seconds=20), 10)],
            v3_pending_since=AT + timedelta(hours=1),
        ),
        C + 'da': derived('da', AT, 30, ['a', 'b']),
        C
        + 'c': source(
            'c',
            started_at=AT + timedelta(hours=6),
            finished_at=AT + timedelta(hours=6, seconds=10),
            claims=[claim('dc', AT + timedelta(hours=6), 10)],
            v3_pending_since=AT + timedelta(hours=2),
        ),
        C + 'dc': derived('dc', AT + timedelta(hours=6), 10, ['c']),
        # The 12 owners' shape: parked on document_too_large, early attempt spent, backoff just over.
        LEASE: {
            'token': 'token',
            'until': now + timedelta(hours=1),
            'v3_blocked_reason': 'document_too_large',
            'v3_blocked_count': 10,
            'v3_backoff_until': now - timedelta(minutes=1),
            'v3_bounded_pending_attempted': True,
            'v3_bounded_pending_limit': None,
        },
    }
    return rows


@pytest.fixture
def owner(monkeypatch):
    rows = three_seeds()
    client = TxMemory(rows)
    passes, wakes = [], []
    # The document Firestore rejects for size, and whether its error names it (as the real one does).
    state = SimpleNamespace(oversized='da', named=True)

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def commit(uid, token, recordings, existing, planned, cache, **kw):
        loaded = sorted(recordings)
        passes.append((loaded, sorted(existing)))
        if state.oversized in existing or state.oversized in recordings:
            # Firestore rejects the oversize document: the transaction writes nothing.
            path = f'projects/p/databases/(default)/documents/users/u/conversations/{state.oversized}'
            text = f"Document '{path}' cannot be written because its size (1,048,611 bytes) exceeds the maximum allowed size"
            raise Conflict('document_too_large') from InvalidArgument(
                text if state.named else 'The value of property "transcript_segments" is longer than 1048487 bytes'
            )
        for rid in recordings:
            rows[C + rid]['v3_pending'] = False
        # The final batch's lease update (commit_projection) clears the park.
        rows[LEASE].update(v3_blocked_count=0, v3_backoff_until=None, v3_blocked_reason=None)
        return set()

    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store.firestore, 'transactional', lambda body: body)
    monkeypatch.setattr(store, 'run_preloaded_transaction_with_contention_retry', lambda c, fn, *a: fn(Tx(), *a))
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(store, 'account_deletion_document', lambda *a, **kw: client.document('deletion'))
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap: {**snap.to_dict(), '_v3_revision': 1} if snap.exists else None
    )
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'acquire', lambda *a, promote_llm=False: 'token')
    monkeypatch.setattr(leases, 'renew', lambda *a: None)
    monkeypatch.setattr(leases, 'release', lambda *a: None)
    for name, fake in {
        'outline_attempt': lambda *a, **kw: True,
        'save_outline': lambda *a, **kw: None,
        'adoptable': lambda *a: {},
        'merge_donors_have_tasks': lambda *a, **kw: False,
    }.items():
        monkeypatch.setattr(store, name, fake)
    monkeypatch.setattr(service, '_commit', commit)
    monkeypatch.setattr(service, 'enqueue', lambda uid, **kw: wakes.append(kw))
    monkeypatch.setattr(service, 'drain_processing', AsyncMock())
    monkeypatch.setattr(service.visibility, 'hydrate_recognition', lambda *a: None)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda uid, prompt: '{"conversations":[{"first_line":1,"title":"A plan","line":"A plan.","kind":"conversation"}]}',
    )
    return SimpleNamespace(rows=rows, passes=passes, wakes=wakes, state=state)


@pytest.mark.asyncio
async def test_a_shared_closure_stays_blocked_with_its_claims_while_an_independent_seed_commits(owner):
    rows = owner.rows
    before = {cid: deepcopy(rows[C + cid]) for cid in ('a', 'b', 'da')}

    # Pass 1 seeds the oldest recording; its closure follows the shared claimant to "b". Both are set aside
    # in one park, so "b" is never seeded into the same rejection on a later pass.
    assert await service.reconcile('u') == 'blocked'
    assert owner.passes == [(['a', 'b'], ['da'])]
    assert rows[LEASE][store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert rows[LEASE]['v3_blocked_reason'] == 'document_too_large'
    assert owner.wakes and owner.wakes[-1].get('wake_key') == 'token'  # The next seed runs on the post-park wake.

    # Pass 2 seeds the independent recording and commits; nothing pulls the set-aside closure back in.
    assert await service.reconcile('u') == 'committed'
    assert owner.passes[1] == (['c'], ['dc'])
    assert rows[C + 'c']['v3_pending'] is False

    # The shared closure is untouched and still pending, and the lease still names it as blocked after the
    # park cleared: a recovered owner is not a repaired recording.
    for cid, row in before.items():
        assert rows[C + cid] == row
    assert rows[C + 'a']['v3_pending'] is True and rows[C + 'b']['v3_pending'] is True
    assert rows[LEASE]['v3_blocked_reason'] is None
    assert rows[LEASE][store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert len(owner.passes) == 2  # The set-aside rows do not chain another pass.


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [True, False])
async def test_the_sweep_does_not_wake_an_owner_whose_only_stale_work_is_set_aside(owner, monkeypatch, enabled):
    rows = owner.rows
    rows[C + 'c']['v3_pending'] = False
    rows[LEASE][store.SIZE_QUARANTINE_FIELD] = ['a', 'b']
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'on' if enabled else 'off')
    monkeypatch.setattr(service, 'python_owns_finalization', lambda row: True)
    assert await service.sweep() == (0 if enabled else 1)
    assert len(owner.wakes) == (0 if enabled else 1)
    # Any other stale pending recording still wakes the owner.
    rows[C + 'c']['v3_pending'] = True
    owner.wakes.clear()
    assert await service.sweep() == 1 and len(owner.wakes) == 1


@pytest.mark.asyncio
async def test_a_one_seed_size_rejection_with_an_unlocked_seed_sets_nothing_aside(owner, monkeypatch):
    rows = owner.rows
    rows[C + 'da']['v3_unlocked'] = True
    rows[LEASE]['unlocked_ids'] = ['da']
    assert await service.reconcile('u') == 'blocked'
    assert store.SIZE_QUARANTINE_FIELD not in rows[LEASE]


def open_window(rows):
    """The lease's open window, which load() pulls in on its own on every pass."""
    rows[C + 'o'] = source('o', started_at=AT + timedelta(hours=9), claims=[claim('do', AT + timedelta(hours=9), 10)])
    rows[C + 'o']['v3_pending'] = False
    rows[C + 'do'] = derived('do', AT + timedelta(hours=9), 10, ['o'], status='in_progress')
    rows[LEASE]['open_id'] = 'do'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'oversized,named,expected',
    [
        ('do', True, None),  # The open window is the oversize document: no seed answers for it.
        ('o', True, None),  # So is the open window's own source.
        ('da', False, None),  # Unnamed (a property-size error) with an open window loaded: unattributable.
        ('da', True, ['a', 'b']),  # Named, and only the seed's closure holds it.
    ],
)
async def test_an_independently_loaded_open_window_is_never_charged_to_the_seed(owner, oversized, named, expected):
    open_window(owner.rows)
    owner.state.oversized, owner.state.named = oversized, named
    assert await service.reconcile('u') == 'blocked'
    assert 'do' in owner.passes[0][1]  # The open window was loaded beside the one pending seed.
    assert owner.rows[LEASE].get(store.SIZE_QUARANTINE_FIELD) == expected
    if expected is None:
        # The usual park: the owner backs off instead of walking healthy seeds into the same rejection.
        assert store.backoff_state('u')[0] is not None


def test_a_new_quarantine_reports_a_degraded_fallback_once(strict, monkeypatch):
    calls = []
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: calls.append(kw))
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    store.record_blocked(UID, token, 'document_too_large', quarantine=('a',), firestore_client=strict)
    store.record_blocked(UID, token, 'document_too_large', quarantine=('a',), firestore_client=strict)
    store.record_blocked(UID, token, 'v3_derived_budget', firestore_client=strict)
    assert calls == [
        {
            'component': 'conversations_v3',
            'from_mode': 'pending_retry',
            'to_mode': 'size_quarantine',
            'reason': 'document_size_limit',
            'outcome': 'degraded',
            'log': store.logger,
        }
    ]


def test_the_size_error_names_its_document_or_nothing():
    path = 'projects/p/databases/(default)/documents/users/u/conversations/da'
    named = InvalidArgument(
        f"Document '{path}' cannot be written because its size (1 bytes) exceeds the maximum allowed size"
    )
    assert service.size_error_document(named) == 'da'
    assert (
        service.size_error_document(InvalidArgument('The value of property "x" is longer than 1048487 bytes')) is None
    )
    assert service.size_error_document(InvalidArgument(f"Document '{path}' is locked")) is None
    assert service.size_error_document(None) is None


def test_quarantined_successors_cannot_hide_a_healthy_page_continuation():
    rows = {C + 's': source('s', started_at=AT, v3_pending_since=AT)}
    after = AT + timedelta(seconds=11)
    for i in range(33):
        rows[C + f'q{i}'] = source(f'q{i}', started_at=after, v3_pending_since=AT + timedelta(hours=1, seconds=i))
    rows[C + 'h'] = source('h', started_at=after + timedelta(seconds=1), v3_pending_since=AT + timedelta(hours=2))
    rows[LEASE] = {store.SIZE_QUARANTINE_FIELD: [f'q{i}' for i in range(33)]}
    recordings, _existing, _cache = store.load(
        'u', pending_limit=1, unlocked_page=UnlockedPage(), firestore_client=MemoryQuery(rows)
    )
    assert list(recordings) == ['s']
    assert recordings['s'].get('_v3_page_continues') is True
