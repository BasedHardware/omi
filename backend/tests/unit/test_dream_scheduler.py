"""All-user rotation, work/hunt eligibility and reserved minute admission."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import DeadlineExceeded

from config.dream_agent import Caps, eligible
from database import dream_scheduler, dream_store, dream_turns
from tests.support.dream_firestore import DreamFirestore
from tests.unit.test_dream_harness_runtime import runtime, store, UID
from utils.llm.shaped_agent import Turn

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def test_due_queue_orders_backlog_and_staleness_independently_of_discovery(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    db = DreamFirestore()
    seen = []
    monkeypatch.setattr(dream_scheduler, 'discover', lambda database, now: seen.append(database))

    class Query:
        def where(self, *, filter):
            assert filter.field_path == 'due_at' and filter.op_string == '<='
            return self

        def order_by(self, field):
            assert field == 'due_at'
            return self

        def limit(self, count):
            assert count == 5000
            return self

        def stream(self, **kwargs):
            return [SimpleNamespace(id='old-backlog'), SimpleNamespace(id='due-hunt')]

    original = db.collection
    monkeypatch.setattr(db, 'collection', lambda name: Query() if name == 'dream_due' else original(name))
    page = dream_scheduler.candidates(limit=5000, now=NOW, firestore_client=db)
    assert page == ['old-backlog', 'due-hunt'] and seen == [db]
    assert not db.rows  # Unattempted work is retained by the queue, never cursor-skipped.


def test_staleness_and_backlog_priority_are_bounded():
    old = {'last_pass_at': NOW - timedelta(days=2), 'score': 1}
    fresh = {'last_pass_at': NOW, 'score': 500}
    assert dream_scheduler.priority(old, NOW) > dream_scheduler.priority(fresh, NOW)
    assert dream_scheduler.priority({'score': 500}, NOW)[0] == dream_scheduler.priority({'score': 500000}, NOW)[0]


@pytest.mark.parametrize('policy,allowed', [('all', True), ('paid', False), ('allowlist', False), ('unknown', False)])
def test_eligibility_defaults_and_optional_restrictions(monkeypatch, policy, allowed):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', policy)
    monkeypatch.delenv('DREAM_AGENT_UID_ALLOWLIST', raising=False)
    assert eligible('synthetic', {}) is allowed
    assert not eligible('dream-canary-synthetic', {})
    assert not eligible('synthetic', {'deleted': True})


def test_minute_ceiling_is_shared_and_owner_daily_usd_is_not_global(runtime):
    caps = Caps(tokens=96000, tokens_per_minute=100, daily_usd=0.0003)
    lease = dream_store.acquire(UID, caps, now=NOW)
    assert lease
    dream_turns.reserve(UID, lease['run_id'], 60, caps, now=NOW)
    with pytest.raises(ValueError, match='dream_minute_headroom'):
        dream_turns.reserve(UID, lease['run_id'], 41, caps, now=NOW)
    with pytest.raises(RuntimeError, match='dream_lease_lost'):
        dream_turns.reserve(UID, 'stale-run', 1, caps, now=NOW)
    dream_turns.reserve(UID, lease['run_id'], 41, caps, now=NOW + timedelta(minutes=1))
    settled = Turn(tokens=20, prompt_tokens=15, cached_tokens=5)
    settled.cost_status = 'priced'
    settled.cost_micro_usd = 200
    dream_turns.settle(UID, lease['run_id'], settled)
    day = lease['day']
    assert runtime.rows[('dream_users', UID, 'spend', day)]['observed_usd'] == pytest.approx(0.0002)
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] == pytest.approx(0.0002)
    runtime.rows[('users', 'other')] = {}
    runtime.rows[('dream_users', 'other')] = {'score': 1}
    runtime.rows[('dream_users', 'other', 'dirty', dream_store.dirty_id('conversations', 'synthetic'))] = {
        'collection': 'conversations',
        'id': 'synthetic',
        'version': 'synthetic-version',
        'last_changed_at': NOW,
    }
    runtime.rows[('dream_global_spend', day + '-0')] = {'reserved_usd': 3}
    assert dream_store.acquire('other', caps, now=NOW) is not None
    dream_store.finish(UID, lease, {'tokens': 20, 'usage_unknown': True}, success=True, now=NOW)
    runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] = caps.daily_usd
    assert dream_store.acquire(UID, caps, now=NOW + timedelta(seconds=1)) is None


def test_empty_backlog_hunt_is_daily_and_stale_lease_reclaim_is_1740_seconds(runtime):
    lease = dream_store.acquire(UID, Caps(tokens=96000), now=NOW)
    assert lease and lease['hunt']
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(seconds=1740)) is None
    replacement = dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(seconds=1741))
    assert replacement and replacement['run_id'] != lease['run_id']
    dream_store.finish(UID, replacement, {'tokens': 10, 'usage_unknown': False}, success=True, now=NOW)
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW + timedelta(hours=2)) is None


def test_dirty_priority_orders_backlog_and_staleness_not_user_document_id(runtime):
    old = {'last_pass_at': NOW - timedelta(days=2), 'score': 1}
    new = {'last_pass_at': NOW - timedelta(days=1), 'score': 1}
    busy = {'last_pass_at': NOW - timedelta(days=1), 'score': 20}
    assert dream_scheduler.due_time(old, NOW) < dream_scheduler.due_time(new, NOW)
    assert dream_scheduler.due_time(busy, NOW) < dream_scheduler.due_time(new, NOW)


@pytest.mark.parametrize(
    'raw,bucket,hours',
    [
        ('', 'light', 24),
        ('', 'heavy', 6),
        ('2', 'light', 2),
        ('2', 'heavy', 2),
        ('48', 'light', 24),
        ('0', 'light', 24),
        ('x', 'heavy', 6),
    ],
)
def test_hunt_interval_override_only_shortens(monkeypatch, raw, bucket, hours):
    from config.dream_agent import hunt_interval

    monkeypatch.setenv('DREAM_AGENT_HUNT_INTERVAL_HOURS', raw)
    assert hunt_interval(bucket) == timedelta(hours=hours)
    assert dream_scheduler.due_time({'last_pass_at': NOW, 'size_bucket': bucket}, NOW) == NOW + timedelta(hours=hours)


def test_short_hunt_interval_and_high_pass_cap_admit_repeat_hunts(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_HUNT_INTERVAL_HOURS', '1')
    caps = Caps(tokens=96000, passes=48)
    for hour in range(4):
        lease = dream_store.acquire(UID, caps, now=NOW + timedelta(hours=hour))
        assert lease and lease['hunt']
        dream_store.finish(
            UID, lease, {'tokens': 10, 'usage_unknown': False}, success=True, now=NOW + timedelta(hours=hour)
        )
    assert dream_store.acquire(UID, caps, now=NOW + timedelta(hours=3, minutes=30)) is None


def test_allowlist_discovery_reads_only_listed_owners(monkeypatch):
    store = DreamFirestore()
    store.collection('users').document('listed-owner').set({'plan': 'free'})
    store.collection('users').document('other-owner').set({'plan': 'free'})
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', 'listed-owner,missing-owner')
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)

    def scan(**kwargs):
        raise AssertionError('allowlist discovery must not scan users')

    monkeypatch.setattr(dream_scheduler, 'candidate_page', scan)
    dream_scheduler.discover(store, NOW)
    assert store.collection('dream_due').document('listed-owner').get().exists
    assert not store.collection('dream_due').document('other-owner').get().exists
    assert not store.collection('dream_due').document('missing-owner').get().exists
    assert not store.collection('dream_scheduler').document('discovery').get().exists


def test_discovery_failure_returns_due_rows_and_logs_once(monkeypatch, caplog):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    db = DreamFirestore()

    def explode(database, now):
        raise DeadlineExceeded('synthetic 504 from dream_users bulk get')

    monkeypatch.setattr(dream_scheduler, 'discover', explode)
    fallbacks = []
    monkeypatch.setattr(dream_scheduler, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    class Query:
        def where(self, *, filter):
            return self

        def order_by(self, field):
            return self

        def limit(self, count):
            return self

        def stream(self, **kwargs):
            return [SimpleNamespace(id='already-due')]

    original = db.collection
    monkeypatch.setattr(db, 'collection', lambda name: Query() if name == 'dream_due' else original(name))
    with caplog.at_level('WARNING', logger='database.dream_scheduler'):
        page = dream_scheduler.candidates(limit=5000, now=NOW, firestore_client=db)
    assert page == ['already-due']
    warnings = [record.getMessage() for record in caplog.records if 'dream_discovery_failed' in record.getMessage()]
    assert warnings == ['dream_discovery_failed stage=discover class=DeadlineExceeded']
    assert fallbacks == [
        {
            'component': 'firestore_read',
            'from_mode': 'dream_discovery',
            'to_mode': 'queue_only',
            'reason': 'timeout',
            'outcome': 'degraded',
            'log': dream_scheduler.logger,
        }
    ]


def synthetic_page(count):
    return [SimpleNamespace(id='owner-%03d' % index, to_dict=lambda: {}) for index in range(count)]


def page_of(pairs):
    return [SimpleNamespace(id=uid, to_dict=lambda data=data: data) for uid, data in pairs]


def test_discover_commits_pages_in_bounded_chunks(monkeypatch):
    store = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **kwargs: synthetic_page(250))
    batches = []
    original = store.get_all

    def get_all(refs, **kwargs):
        batches.append((refs[0].path[0], len(refs)))
        return original(refs, **kwargs)

    monkeypatch.setattr(store, 'get_all', get_all)
    dream_scheduler.discover(store, NOW, pages=1)
    assert [size for collection, size in batches if collection == 'dream_due'] == [100, 100, 50]
    assert [size for collection, size in batches if collection == 'dream_users'] == [100, 100, 50]
    assert len(store.transactions) == 3
    assert [len(transaction.sets) for transaction in store.transactions] == [100, 100, 51]
    assert all(('dream_due', 'owner-%03d' % index) in store.rows for index in range(250))
    assert store.rows[('dream_scheduler', 'discovery')] == {'after': 'owner-249'}


def test_failed_chunk_keeps_cursor_and_retains_idempotent_progress(monkeypatch):
    store = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **kwargs: synthetic_page(250))
    original = store.get_all
    dream_users_batches = []

    def get_all(refs, **kwargs):
        if refs[0].path[0] == 'dream_users':
            dream_users_batches.append(len(refs))
            if len(dream_users_batches) == 2:
                raise DeadlineExceeded('synthetic 504 on the second chunk')
        return original(refs, **kwargs)

    monkeypatch.setattr(store, 'get_all', get_all)
    with pytest.raises(DeadlineExceeded):
        dream_scheduler.discover(store, NOW, pages=1)
    assert ('dream_scheduler', 'discovery') not in store.rows  # failed page never advances the cursor
    assert ('dream_due', 'owner-000') in store.rows  # committed chunks stay; replay skips them
    assert ('dream_due', 'owner-100') not in store.rows


def test_discovery_budget_stops_before_any_page(monkeypatch, caplog):
    store = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')

    def scan(**kwargs):
        pytest.fail('budget exhaustion must not start a new page')

    monkeypatch.setattr(dream_scheduler, 'candidate_page', scan)
    fallbacks = []
    monkeypatch.setattr(dream_scheduler, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    with caplog.at_level('WARNING', logger='database.dream_scheduler'):
        dream_scheduler.discover(store, NOW, budget_seconds=0.0)
    assert ('dream_scheduler', 'discovery') not in store.rows
    stopped = [record.getMessage() for record in caplog.records if 'dream_discovery_stopped' in record.getMessage()]
    assert stopped == ['dream_discovery_stopped stage=page class=BudgetExhausted']
    assert fallbacks and fallbacks[0]['to_mode'] == 'partial_scan' and fallbacks[0]['reason'] == 'timeout'


def test_discovery_budget_stop_midpage_keeps_cursor(monkeypatch, caplog):
    store = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **kwargs: synthetic_page(150))
    clock = {'now': 0.0}

    def advancing_monotonic():
        clock['now'] += 50.0
        return clock['now']

    monkeypatch.setattr(dream_scheduler.time, 'monotonic', advancing_monotonic)
    with caplog.at_level('WARNING', logger='database.dream_scheduler'):
        dream_scheduler.discover(store, NOW, budget_seconds=120.0)
    assert ('dream_scheduler', 'discovery') not in store.rows  # partial page never advances the cursor
    assert ('dream_due', 'owner-000') in store.rows and ('dream_due', 'owner-100') not in store.rows
    stopped = [record.getMessage() for record in caplog.records if 'dream_discovery_stopped' in record.getMessage()]
    assert stopped == ['dream_discovery_stopped stage=chunk class=BudgetExhausted']


def test_discovery_states_reads_cover_only_eligible_unqueued_rows(monkeypatch):
    store = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    page = page_of(
        [
            ('eligible-queued', {}),
            ('eligible-fresh', {}),
            ('gone-queued', {'deleted': True}),
            ('gone-fresh', {'deleted': True}),
        ]
    )
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **kwargs: page)
    store.collection('dream_due').document('eligible-queued').set({'due_at': NOW - timedelta(days=3)})
    store.collection('dream_due').document('gone-queued').set({'due_at': NOW})
    state = {'last_pass_at': NOW - timedelta(days=2), 'score': 1}
    store.collection('dream_users').document('eligible-queued').set(dict(state, score=999))
    store.collection('dream_users').document('eligible-fresh').set(state)
    store.collection('dream_users').document('gone-queued').set(state)
    state_batches = []
    original = store.get_all

    def get_all(refs, **kwargs):
        if refs and refs[0].path[0] == 'dream_users':
            state_batches.append([ref.id for ref in refs])
        return original(refs, **kwargs)

    monkeypatch.setattr(store, 'get_all', get_all)
    dream_scheduler.discover(store, NOW, pages=1)
    assert state_batches == [['eligible-fresh']]  # queued and ineligible owners are never state-read
    assert store.rows[('dream_due', 'eligible-fresh')]['due_at'] == dream_scheduler.due_time(state, NOW)
    assert store.rows[('dream_due', 'eligible-queued')]['due_at'] == NOW - timedelta(days=3)  # no clobber
    assert ('dream_due', 'gone-queued') not in store.rows  # stale queue row deleted
    assert ('dream_due', 'gone-fresh') not in store.rows
    assert store.rows[('dream_scheduler', 'discovery')] == {'after': 'gone-fresh'}


@pytest.mark.parametrize(
    'users',
    [
        {'ineligible-a': {'deleted': True}, 'ineligible-b': {'deletion_requested_at': NOW}},
        {'queued-a': {}, 'queued-b': {}},
    ],
)
def test_discovery_skips_states_read_when_no_rows_qualify(monkeypatch, users):
    store = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **kwargs: page_of(list(users.items())))
    for uid in users:
        if uid.startswith('queued-'):
            store.collection('dream_due').document(uid).set({'due_at': NOW - timedelta(hours=1)})
    state_reads = []
    original = store.get_all

    def get_all(refs, **kwargs):
        if refs and refs[0].path[0] == 'dream_users':
            state_reads.append([ref.id for ref in refs])
        return original(refs, **kwargs)

    monkeypatch.setattr(store, 'get_all', get_all)
    dream_scheduler.discover(store, NOW, pages=1)
    assert state_reads == []  # no dream_users bulk read at all
    queued = [uid for uid in users if uid.startswith('queued-')]
    if queued:
        assert all(store.rows[('dream_due', uid)]['due_at'] == NOW - timedelta(hours=1) for uid in queued)
    else:
        assert not [path for path in store.rows if path[0] == 'dream_due']
    assert store.rows[('dream_scheduler', 'discovery')] == {'after': list(users)[-1]}
