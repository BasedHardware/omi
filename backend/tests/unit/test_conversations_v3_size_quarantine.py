"""A recording whose closure Firestore rejects for size must not freeze the owner's backlog (SCA-2918)."""

from collections.abc import MutableMapping
from copy import deepcopy
from functools import partial
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import InvalidArgument

from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import Conflict, UnlockedPage, service
from tests.unit.test_conversations_v3_derived_budget import claim, derived
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreCollection,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
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


@pytest.fixture
def lease(owner):
    """An unparked builder lease under token 'token', on the same in-memory rows as load and the sweep."""
    owner.rows[LEASE] = {'token': 'token', 'until': datetime.now(timezone.utc) + timedelta(hours=1)}
    return owner


def hold(*ids, ago=timedelta(0)):
    """A stored quarantine of ``ids``, set aside ``ago``."""
    at = datetime.now(timezone.utc) - ago
    return {store.SIZE_QUARANTINE_FIELD: list(ids), store.SIZE_QUARANTINE_AT_FIELD: {rid: at for rid in ids}}


def pending(lease, *ids, value=True):
    for rid in ids:
        lease.rows[C + rid] = {'id': rid, 'recording': True, 'v3_pending': value}


def test_a_size_park_sets_its_closure_aside_and_runs_the_next_seed_without_the_backoff(lease):
    pending(lease, 'a', 'b')
    token = 'token'
    held = lease.rows[LEASE]
    assert store.record_blocked('u', token, 'document_too_large', quarantine=('a', 'b'))
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    # Re-armed early attempt: the backoff does not hold the backlog outside the set-aside closure.
    assert store.backoff_state('u') == (None, 'document_too_large')
    store.mark_bounded_attempt('u', token)
    assert store.backoff_state('u')[0] is not None
    # Nothing new to set aside: the park spends the usual backoff.
    assert store.record_blocked('u', token, 'document_too_large', quarantine=('b',))
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert store.backoff_state('u')[0] is not None
    assert store.size_quarantined('u') == {'a', 'b'}


def test_held_ids_that_landed_or_were_deleted_are_pruned_so_the_list_never_silts_up(lease, monkeypatch):
    monkeypatch.setattr(store, 'SIZE_QUARANTINE_MAX', 2)
    pending(lease, 'a', 'b', 'c')
    token = 'token'
    held = lease.rows[LEASE]
    store.record_blocked('u', token, 'document_too_large', quarantine=('a', 'b'))
    pending(lease, 'a', value=False)  # Landed (or repaired).
    del lease.rows[C + 'b']  # Deleted.
    # The list was full, but both held ids settled: they make room for the new closure.
    assert store.record_blocked('u', token, 'document_too_large', quarantine=('c',))
    assert held[store.SIZE_QUARANTINE_FIELD] == ['c']


def test_a_failed_prune_read_keeps_the_list_and_still_records_the_backoff(lease, monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: calls.append(kw))
    pending(lease, 'a', 'b')
    lease.rows[LEASE].update(hold('a'))
    pending(lease, 'a', value=False)  # Settled, but the prune cannot read it.

    def unreadable(*a, **kw):
        raise RuntimeError('transient')

    monkeypatch.setattr(lease.strict, 'get_all', unreadable)
    with caplog.at_level('WARNING'):
        assert store.record_blocked('u', 'token', 'document_too_large')
    held = lease.rows[LEASE]
    assert held['v3_blocked_count'] == 1 and held['v3_blocked_reason'] == 'document_too_large'
    assert store.backoff_state('u')[0] is not None  # The park is recorded as without the quarantine.
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a']  # Kept until a prune can read it.
    assert 'event=v3_size_quarantine_prune outcome=error exception_type=RuntimeError' in caplog.messages
    assert calls == [
        {
            'component': 'conversations_v3',
            'from_mode': 'size_quarantine_prune',
            'to_mode': 'keep_held',
            'reason': 'unavailable',
            'outcome': 'degraded',
            'log': store.logger,
        }
    ]


@pytest.mark.parametrize('enabled', [True, False])
def test_with_the_switch_off_a_size_park_reads_only_its_lease(lease, monkeypatch, enabled):
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'on' if enabled else 'off')
    pending(lease, 'b')
    pending(lease, 'a', value=False)  # Settled: a prune would drop it.
    lease.rows[LEASE].update(hold('a'))
    stored = deepcopy(lease.rows[LEASE][store.SIZE_QUARANTINE_AT_FIELD])
    reads = []
    document_get = StrictFirestoreDocument.get

    def counted(self, transaction=None, **kw):
        reads.append((self.path[-1], transaction is not None))
        return document_get(self, transaction, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    assert store.record_blocked('u', 'token', 'document_too_large', quarantine=('b',))
    # Off: the park transaction's own lease read and nothing else, as before the quarantine shipped.
    expected = [('builder', False), ('a', False), ('builder', True)] if enabled else [('builder', True)]
    assert reads == expected
    # Off: no prune read and no quarantine write (the settled id stays as stored); on: pruned and replaced.
    assert lease.rows[LEASE][store.SIZE_QUARANTINE_FIELD] == (['b'] if enabled else ['a'])
    assert (lease.rows[LEASE][store.SIZE_QUARANTINE_AT_FIELD] == stored) is not enabled


def test_a_lapsed_hold_is_seeded_again_and_set_aside_afresh_if_still_oversize(lease, monkeypatch):
    calls = []
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: calls.append(kw['outcome']))
    pending(lease, 'a', 'b')
    lease.rows[LEASE].update(hold('b'))
    lease.rows[LEASE][store.SIZE_QUARANTINE_AT_FIELD]['a'] = datetime.now(timezone.utc) - store.SIZE_QUARANTINE_HOLD
    lease.rows[LEASE][store.SIZE_QUARANTINE_FIELD].append('a')  # Stored as ['b', 'a']: only the stamp changes.
    assert store.size_quarantined('u') == {'b'}  # The lapsed id no longer holds the owner back.
    # The re-attempt fails for size again: the lapsed id is set aside with a fresh hold.
    assert store.record_blocked('u', 'token', 'document_too_large', quarantine=('a',))
    stamps = lease.rows[LEASE][store.SIZE_QUARANTINE_AT_FIELD]
    assert lease.rows[LEASE][store.SIZE_QUARANTINE_FIELD] == ['b', 'a']
    assert datetime.now(timezone.utc) - stamps['a'] < timedelta(minutes=1)
    assert store.size_quarantined('u') == {'a', 'b'}
    assert calls == ['degraded']
    # An unrelated park drops a lapsed id (it is being re-attempted), keeping the live one.
    stamps['a'] -= store.SIZE_QUARANTINE_HOLD
    assert store.record_blocked('u', 'token', 'document_too_large')
    assert lease.rows[LEASE][store.SIZE_QUARANTINE_FIELD] == ['b']
    assert set(lease.rows[LEASE][store.SIZE_QUARANTINE_AT_FIELD]) == {'b'}


def test_an_unstamped_id_is_not_held():
    now = datetime.now(timezone.utc)
    assert store._held_ids({store.SIZE_QUARANTINE_FIELD: ['a']}, now) == frozenset()
    assert store._held_ids(hold('a', ago=timedelta(hours=23)), now) == {'a'}
    assert store._held_ids(hold('a', ago=store.SIZE_QUARANTINE_HOLD + timedelta(seconds=1)), now) == frozenset()


def test_the_quarantine_is_bounded_all_or_nothing_and_a_full_list_is_reported(lease, monkeypatch):
    calls = []
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: calls.append(kw['outcome']))
    pending(lease, 'a', 'b', 'c', 'd', 'e')
    token = 'token'
    held = lease.rows[LEASE]
    assert store.record_blocked('u', token, 'v3_derived_budget', quarantine=('a',))
    assert store.SIZE_QUARANTINE_FIELD not in held
    monkeypatch.setattr(store, 'SIZE_QUARANTINE_MAX', 3)
    store.record_blocked('u', token, 'document_too_large', quarantine=('a', 'b'))
    # A closure that no longer fits is not split: none of it is set aside and the owner backs off as before.
    store.record_blocked('u', token, 'document_too_large', quarantine=('c', 'd'))
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert store.backoff_state('u')[0] is not None
    assert calls == ['degraded', 'exhausted']  # The full list is not silent.
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'off')
    store.record_blocked('u', token, 'document_too_large', quarantine=('e',))
    assert held[store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert store.size_quarantined('u') == frozenset()


@pytest.mark.parametrize(
    'enabled,lapsed', [(True, False), (False, False), (True, True)], ids=['held', 'switch-off', 'lapsed']
)
def test_a_bounded_load_seeds_past_a_quarantined_oldest_recording(monkeypatch, enabled, lapsed):
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', 'on' if enabled else 'off')
    rows = backlog()
    rows[LEASE] = hold('r0', ago=store.SIZE_QUARANTINE_HOLD if lapsed else timedelta(0))
    enabled = enabled and not lapsed  # A lapsed hold is seeded again, as if never set aside.
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
    rows[LEASE] = hold('r0')
    recordings, _existing, _cache = store.load('u', pending_limit=1, firestore_client=MemoryQuery(rows))
    assert list(recordings) == ['r0']


def _commit_of(**rows):
    """A rejected commit: ``a`` and ``b`` claim ``da``; ``s`` is a time sibling feeding the unrelated ``dx``."""
    recordings = {
        'a': {'v3_pending': True, 'claims': [{'conversation_id': 'da'}]},
        'b': {'v3_pending': True, 'claims': [{'conversation_id': 'da'}]},
        'settled': {'v3_pending': False, 'claims': [{'conversation_id': 'da'}]},
        's': {'v3_pending': True, 'claims': [{'conversation_id': 'dx'}]},
        **rows,
    }
    planned = [{'id': 'da', 'v3_recording_ids': ['a', 'b', 'settled']}, {'id': 'dx', 'v3_recording_ids': ['s']}]
    return recordings, {}, planned


@pytest.mark.parametrize(
    'oversized,expected',
    [
        ('da', ('a', 'b')),  # The seed's own row: the seed and the pendings that share it.
        ('a', ('a', 'b')),  # The seed itself.
        ('settled', ('a', 'b')),  # A co-source the commit writes for the seed's row.
        ('dx', ()),  # Only a time sibling's row: no evidence against the seed.
        ('s', ()),
        (None, ()),  # Unnamed (a property-size error): never attributable.
    ],
)
def test_only_the_rejected_documents_seed_side_is_set_aside(oversized, expected):
    page = UnlockedPage(seeds=(1, 0), pending_ids=('a',))
    assert service._size_quarantine('document_too_large', 1, page, _commit_of(), oversized) == expected
    assert service._size_quarantine('v3_derived_budget', 1, page, _commit_of(), oversized) == ()
    assert service._size_quarantine('document_too_large', 8, page, _commit_of(), oversized) == ()
    two = UnlockedPage(seeds=(2, 0), pending_ids=('a', 'b'))
    assert service._size_quarantine('document_too_large', 1, two, _commit_of(), oversized) == ()
    # An unlocked seed beside the pending one no longer disqualifies; only its own documents are vetoed.
    unlocked = UnlockedPage(seeds=(1, 1), pending_ids=('a',), independent=frozenset({'du', 'u'}))
    assert service._size_quarantine('document_too_large', 1, unlocked, _commit_of(), oversized) == expected
    assert service._size_quarantine('document_too_large', 1, unlocked, _commit_of(), 'du') == ()


def test_nothing_the_open_window_reaches_transitively_is_charged_to_the_seed():
    """The open window's source ``o`` also claims the finished ``dz``, which the seed claims too: ``dz``
    loads on every pass through the open window, so a rejection naming it is not the seed's."""
    page = UnlockedPage(seeds=(1, 0), pending_ids=('a',), independent=frozenset({'do', 'o'}))
    recordings, existing, planned = _commit_of(
        a={'v3_pending': True, 'claims': [{'conversation_id': 'da'}, {'conversation_id': 'dz'}]},
        o={'v3_pending': False, 'claims': [{'conversation_id': 'do'}, {'conversation_id': 'dz'}]},
    )
    existing = {'do': {'id': 'do', 'v3_recording_ids': ['o']}, 'dz': {'id': 'dz', 'v3_recording_ids': ['o', 'a']}}
    commit = (recordings, existing, planned)
    assert service._size_quarantine('document_too_large', 1, page, commit, 'dz') == ()
    # ...and so is everything it reaches from there: the seed and the rows it shares with ``dz``'s sources.
    assert service._size_quarantine('document_too_large', 1, page, commit, 'da') == ()
    # Without that link, the seed's own row is attributable again.
    recordings['o']['claims'] = [{'conversation_id': 'do'}]
    existing['dz']['v3_recording_ids'] = ['a']
    assert service._size_quarantine('document_too_large', 1, page, commit, 'dz') == ('a', 'b')


class Rows(MutableMapping):
    """The in-memory rows keyed by StrictFirestore's path tuples, so its transactions and load's queries share
    one store: ('users', 'u', 'conversations', 'a') <-> '/users/u/conversations/a'."""

    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, path):
        return self.rows['/' + '/'.join(path)]

    def __setitem__(self, path, value):
        self.rows['/' + '/'.join(path)] = value

    def __delitem__(self, path):
        del self.rows['/' + '/'.join(path)]

    def __iter__(self):
        return (tuple(key.strip('/').split('/')) for key in self.rows)

    def __len__(self):
        return len(self.rows)


# The lease state machine's transactions run on StrictFirestore (reads before the first write, as Firestore
# enforces); load, has_pending and the sweep's queries run on MemoryQuery over the same rows.
STRICT = ('record_blocked', 'mark_bounded_attempt', 'clear_terminal_pending', 'backoff_state', 'size_quarantined')


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
    client = MemoryQuery(rows)
    strict = StrictFirestore()
    strict.rows = Rows(rows)
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
            conflict = Conflict('document_too_large')
            conflict.size_commit = (recordings, existing, planned)  # As the real _commit attaches it.
            raise conflict from InvalidArgument(
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
    for name in STRICT:
        monkeypatch.setattr(store, name, partial(getattr(store, name), firestore_client=strict))
    monkeypatch.setattr(StrictFirestoreSnapshot, 'update_time', 1, raising=False)
    oldest = store._oldest_pending
    # StrictFirestore models no queries: the terminal-pending scan reads the same rows through MemoryQuery.
    monkeypatch.setattr(
        store,
        '_oldest_pending',
        lambda coll, limit: oldest(
            client.document('/'.join(coll._path)) if isinstance(coll, StrictFirestoreCollection) else coll, limit
        ),
    )
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'account_deletion_document', lambda uid, firestore_client=None: strict.document('deletions/' + uid)
    )
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
    return SimpleNamespace(rows=rows, passes=passes, wakes=wakes, state=state, client=client, strict=strict)


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
@pytest.mark.parametrize(
    'quarantine,bounded', [('on', 'on'), ('off', 'on'), ('on', 'off')], ids=['skips', 'switch-off', 'bounded-off']
)
async def test_the_sweep_does_not_wake_an_owner_whose_only_stale_work_is_set_aside(
    owner, monkeypatch, quarantine, bounded
):
    rows = owner.rows
    rows[C + 'c']['v3_pending'] = False
    rows[LEASE].update(hold('a', 'b'))
    monkeypatch.setenv('CONVERSATIONS_V3_SIZE_QUARANTINE', quarantine)
    # With bounded pending off, load seeds held ids again, so the sweep must keep waking the owner (F6).
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', bounded)
    enabled = quarantine == bounded == 'on'
    monkeypatch.setattr(service, 'python_owns_finalization', lambda row: True)
    assert await service.sweep() == (0 if enabled else 1)
    assert len(owner.wakes) == (0 if enabled else 1)
    # Any other stale pending recording still wakes the owner.
    rows[C + 'c']['v3_pending'] = True
    owner.wakes.clear()
    assert await service.sweep() == 1 and len(owner.wakes) == 1


@pytest.mark.asyncio
async def test_a_repaired_recording_commits_once_its_hold_lapses(owner, monkeypatch):
    rows = owner.rows
    monkeypatch.setattr(service, 'python_owns_finalization', lambda row: True)
    assert await service.reconcile('u') == 'blocked'
    assert await service.reconcile('u') == 'committed'  # The independent seed.
    assert await service.sweep() == 0  # Only held work is left.
    owner.state.oversized = None  # The oversize row is repaired.
    for rid in ('a', 'b'):
        rows[LEASE][store.SIZE_QUARANTINE_AT_FIELD][rid] -= store.SIZE_QUARANTINE_HOLD
    # Once the hold lapses the sweep wakes the owner, the oldest held recording is seeded again, and commits.
    assert await service.sweep() == 1
    assert await service.reconcile('u') == 'committed'
    assert owner.passes[-1] == (['a', 'b'], ['da'])
    assert rows[C + 'a']['v3_pending'] is False and rows[C + 'b']['v3_pending'] is False


def unlocked_window(rows):
    """An unlocked window in the lease's index: the one-seed attempt seeds it beside the pending seed."""
    at = AT + timedelta(hours=12)
    rows[C + 'u'] = source('u', started_at=at, claims=[claim('du', at, 10)])
    rows[C + 'u']['v3_pending'] = False
    rows[C + 'du'] = derived('du', at, 10, ['u'], v3_unlocked=True)
    rows[LEASE]['unlocked_ids'] = ['du']


@pytest.mark.asyncio
async def test_an_oversize_pending_seed_beside_an_unlocked_window_still_drains(owner):
    unlocked_window(owner.rows)
    assert await service.reconcile('u') == 'blocked'
    assert 'du' in owner.passes[0][1]  # The unlocked window was seeded beside the pending seed.
    assert owner.rows[LEASE][store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert await service.reconcile('u') == 'committed'
    assert owner.rows[C + 'c']['v3_pending'] is False


@pytest.mark.asyncio
async def test_an_oversize_unlocked_window_is_never_charged_to_the_pending_seed(owner):
    unlocked_window(owner.rows)
    owner.state.oversized = 'du'
    assert await service.reconcile('u') == 'blocked'
    assert store.SIZE_QUARANTINE_FIELD not in owner.rows[LEASE]
    assert store.backoff_state('u')[0] is not None


@pytest.mark.asyncio
async def test_a_time_sibling_loaded_beside_the_seed_is_not_set_aside(owner):
    rows = owner.rows
    at = AT + timedelta(minutes=15)  # Inside load's time window around the seed, past the silence gap.
    rows[C + 's'] = source(
        's',
        started_at=at,
        finished_at=at + timedelta(seconds=10),
        claims=[claim('dx', at, 10)],
        v3_pending_since=AT + timedelta(hours=3),
    )
    rows[C + 'dx'] = derived('dx', at, 10, ['s'])
    assert await service.reconcile('u') == 'blocked'
    assert 's' in owner.passes[0][0]  # Loaded through the unrelated time-sibling row.
    assert rows[LEASE][store.SIZE_QUARANTINE_FIELD] == ['a', 'b']
    assert rows[C + 's']['v3_pending'] is True


@pytest.mark.asyncio
async def test_an_unnamed_size_rejection_parks_even_without_an_open_window(owner):
    owner.state.named = False
    assert await service.reconcile('u') == 'blocked'
    assert store.SIZE_QUARANTINE_FIELD not in owner.rows[LEASE]
    assert store.backoff_state('u')[0] is not None


@pytest.mark.asyncio
async def test_one_unreadable_lease_does_not_stop_the_sweep(owner, monkeypatch, caplog):
    owner.rows[C + 'c']['v3_pending'] = False
    owner.rows[LEASE].update(hold('a', 'b'))
    monkeypatch.setattr(service, 'python_owns_finalization', lambda row: True)

    def unreadable(uid, **kw):
        raise RuntimeError('transient')

    monkeypatch.setattr(store, 'size_quarantined', unreadable)
    labels = dict(
        component='conversations_v3',
        from_mode='size_quarantine_filter',
        to_mode='unfiltered_wake',
        reason='unavailable',
        outcome='recovered',
    )
    before = _fallbacks(**labels)
    with caplog.at_level('WARNING'):
        assert await service.sweep() == 1  # Treated as not quarantined: the owner is still woken.
    assert 'event=v3_size_quarantine_read outcome=error exception_type=RuntimeError' in caplog.messages
    # The fail-open wake is on the shared fallback counter under its own labels, none bucketed to "other".
    assert _fallbacks(**labels) == before + 1


def _fallbacks(**labels):
    from utils.metrics import OMI_FALLBACK_TOTAL

    return sum(
        sample.value
        for family in OMI_FALLBACK_TOTAL.collect()
        for sample in family.samples
        if sample.name == 'omi_fallback_total' and sample.labels == labels
    )


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


def test_a_new_quarantine_reports_a_degraded_fallback_once(lease, monkeypatch):
    calls = []
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: calls.append(kw))
    pending(lease, 'a')
    token = 'token'
    store.record_blocked('u', token, 'document_too_large', quarantine=('a',))
    store.record_blocked('u', token, 'document_too_large', quarantine=('a',))
    store.record_blocked('u', token, 'v3_derived_budget')
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
    rows[LEASE] = hold(*[f'q{i}' for i in range(33)])
    recordings, _existing, _cache = store.load(
        'u', pending_limit=1, unlocked_page=UnlockedPage(), firestore_client=MemoryQuery(rows)
    )
    assert list(recordings) == ['s']
    assert recordings['s'].get('_v3_page_continues') is True


@pytest.mark.asyncio
async def test_a_finished_row_the_open_windows_source_also_claims_is_never_charged_to_the_seed(owner):
    rows = owner.rows
    open_window(rows)
    at = AT + timedelta(hours=9)
    # The open window's source also claims the finished "dz", which the seed claims too (Codex r4713792971).
    rows[C + 'o']['claims'].append(claim('dz', at, 5))
    rows[C + 'a']['claims'].append(claim('dz', AT, 5))
    rows[C + 'dz'] = derived('dz', AT, 5, ['a', 'o'])
    owner.state.oversized = 'dz'
    assert await service.reconcile('u') == 'blocked'
    assert 'dz' in owner.passes[0][1] and 'o' in owner.passes[0][0]
    assert store.SIZE_QUARANTINE_FIELD not in rows[LEASE]
    assert store.backoff_state('u')[0] is not None


@pytest.mark.asyncio
async def test_a_time_neighbour_of_the_open_windows_source_is_never_charged_to_the_seed(owner):
    rows = owner.rows
    open_window(rows)
    at = AT + timedelta(hours=9) - timedelta(minutes=10)
    # "dn" is a finished row inside the open source's time-neighbour window, so every pass loads it through
    # the open window; the seed also claims it, but no claim joins it to the open window (Codex r4713922743).
    rows[C + 'a']['claims'].append(claim('dn', at, 5))
    rows[C + 'dn'] = derived('dn', at, 5, ['a'])
    owner.state.oversized = 'dn'
    assert await service.reconcile('u') == 'blocked'
    assert 'dn' in owner.passes[0][1] and 'o' in owner.passes[0][0]
    assert store.SIZE_QUARANTINE_FIELD not in rows[LEASE]
    assert store.backoff_state('u')[0] is not None


def test_a_time_queried_row_is_charged_only_to_the_windows_it_overlaps():
    neighbours = {}
    asked = [('a', AT, AT + timedelta(minutes=30)), ('b', AT + timedelta(hours=1), AT + timedelta(hours=2))]
    store._record_neighbour(
        neighbours,
        asked,
        {'id': 'x', 'started_at': AT + timedelta(minutes=5), 'finished_at': AT + timedelta(minutes=6)},
    )
    store._record_neighbour(neighbours, asked, {'id': 'y'})  # Undated: charged to every window that asked.
    assert neighbours == {'a': frozenset({'x', 'y'}), 'b': frozenset({'y'})}
    assert service._reached({'b'}, {}, {}, [], neighbours) == {'b', 'y'}


def test_the_commit_attaches_what_it_wrote_to_a_size_rejection(monkeypatch):
    from utils.conversations import lifecycle

    path = 'projects/p/databases/(default)/documents/users/u/conversations/da'

    def rejected(*a, **kw):
        raise InvalidArgument(
            f"Document '{path}' cannot be written because its size (1 bytes) exceeds the maximum allowed size"
        )

    monkeypatch.setattr(lifecycle, 'commit_v3_projection', rejected)
    recordings, existing, planned = {'a': {}}, {'da': {}}, [{'id': 'da'}]
    with pytest.raises(Conflict, match='document_too_large') as caught:
        service._commit('u', 'token', recordings, existing, planned, [])
    assert caught.value.size_commit == (recordings, existing, planned)
    assert service.size_error_document(caught.value.__cause__) == 'da'
