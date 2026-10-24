"""Count billed documents and prove exact raw snapshot parity across mutations."""

import copy
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from google.auth.credentials import AnonymousCredentials
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1.query import Query

from database import released_memory_projection as projection
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('MEMORY_RELEASED_WRITERS_COVERED', 'v1:unit-test')
    monkeypatch.delenv('MEMORY_RELEASED_PROJECTION', raising=False)
    monkeypatch.setattr(projection, 'MIN_CACHE_ROWS', 0)
    client = firestore.Client(project='demo-projection', credentials=AnonymousCredentials())
    state = SimpleNamespace(client=client, reads=0, scans=0, heads=0, token='v1', blocked=None, rows={}, hook=None)
    stamp = datetime(2026, 10, 23, tzinfo=timezone.utc)
    state.stamp = stamp

    def snapshot(path, data):
        return DocumentSnapshot(
            client.document(path), copy.deepcopy(data), data is not None, state.stamp, state.stamp, state.stamp
        )

    def get(ref, **kwargs):
        state.reads += 1
        state.heads += 1
        if state.hook:
            state.hook(state)
        data = None if state.token is None else {'schema': 1, 'token': state.token}
        if ref.path.endswith('/list_serving_versions/conversations') and data is not None:
            data = {'version': state.token}
        if state.blocked is not None and data is not None:
            data['blocked'] = state.blocked
        return snapshot(ref.path, data)

    def stream(query, **kwargs):
        state.scans += 1
        rows = [
            (path, data) for path, data in state.rows.items() if path.rsplit('/', 1)[0] == '/'.join(query._parent._path)
        ]
        state.reads += max(1, len(rows) + (query._offset or 0))
        return iter([snapshot(path, data) for path, data in rows])

    monkeypatch.setattr(DocumentReference, 'get', get)
    monkeypatch.setattr(Query, 'stream', stream)
    monkeypatch.setattr(projection, '_entries', projection.OrderedDict())
    monkeypatch.setattr(projection, '_small_queries', projection.OrderedDict())
    monkeypatch.setattr(projection, '_bytes', 0)
    state.query = client.collection('users/u/memory_items').limit(100)
    state.read = lambda **kwargs: projection.projected_stream_list(state.query, surface='canonical_scan', **kwargs)
    return state


def payloads(rows):
    return [(row.reference.path, row.to_dict(), row.update_time) for row in rows]


@pytest.fixture
def canonical_adapter():
    from utils.memory import canonical_memory_adapter

    return canonical_memory_adapter


def test_canonical_caller_rechecks_device_policy_on_a_warm_raw_page(store, canonical_adapter):
    from tests.unit.test_universal_memory_list_cursor import _canonical_scan_memory_item
    from utils.client_device import DeviceScopeRequest

    for index in range(3):
        identity, item = _canonical_scan_memory_item('u', f'm{index}', now=store.stamp, day=index)
        item = item.model_copy(update={'capture_device_ids': ['phone-a']})
        store.rows[f'users/u/memory_items/{identity}'] = item.model_dump(mode='python')
    first, _ = canonical_adapter.read_canonical_scan_page('u', db_client=store.client, now=store.stamp)
    assert sum(item is not None for item, _ in first) == 3
    before = store.reads
    scoped, _ = canonical_adapter.read_canonical_scan_page(
        'u',
        db_client=store.client,
        now=store.stamp,
        device_scope_request=DeviceScopeRequest(device_scope='current', client_device_id='phone-b'),
    )
    assert len(scoped) == 3 and all(item is None for item, _ in scoped)
    assert store.reads - before == 2 and store.scans == 1


def test_repeated_page_100_billed_reads_becomes_two_and_preserves_snapshots(store):
    store.rows = {f'users/u/memory_items/m{i}': {'content': str(i), 'nested': {'a': [1]}} for i in range(100)}
    first = store.read()
    assert store.reads == 102  # Source page plus before/after head.
    before = store.reads
    second = store.read()
    assert store.reads - before == 2
    assert store.scans == 1
    assert payloads(first) == payloads(second)
    second[0]._data['nested']['a'].append(2)
    assert store.read()[0].to_dict()['nested']['a'] == [1]


def test_cached_revision_metadata_preserves_firestore_nanoseconds(store):
    store.stamp = DatetimeWithNanoseconds(2026, 10, 23, nanosecond=123456789, tzinfo=timezone.utc)
    store.rows = {f'users/u/memory_items/{i}': {'n': i} for i in range(3)}
    first, second = store.read(), store.read()
    for rows in (first, second):
        assert rows[0].update_time.nanosecond == 123456789
        assert rows[0].create_time.nanosecond == 123456789
        assert rows[0].read_time.nanosecond == 123456789


@pytest.mark.parametrize('mutation', ['update', 'delete', 'override', 'legacy'])
def test_any_memory_domain_change_invalidates_cached_candidates(store, mutation):
    path = 'users/u/memory_items/a'
    store.rows[path] = {'status': 'active'}
    store.read()
    if mutation == 'delete':
        del store.rows[path]
    elif mutation == 'update':
        store.rows[path]['status'] = 'tombstoned'
    store.token = 'new-commit'
    assert payloads(store.read()) == payloads(list(store.query.stream()))
    assert store.scans == 3


def test_empty_result_is_invalidated_by_create(store):
    assert store.read() == []
    assert store.read() == []
    store.rows['users/u/memory_items/new'] = {'status': 'active'}
    store.token = 'created'
    assert len(store.read()) == 1


@pytest.mark.parametrize('mode', ['off', 'no-coverage', 'missing', 'blocked'])
def test_unproven_coverage_and_kill_switch_keep_old_path(store, monkeypatch, mode):
    if mode == 'off':
        monkeypatch.setenv('MEMORY_RELEASED_PROJECTION', 'off')
    elif mode == 'no-coverage':
        monkeypatch.delenv('MEMORY_RELEASED_WRITERS_COVERED')
    elif mode == 'missing':
        store.token = None
    else:
        store.blocked = True
    store.read()
    store.read()
    assert store.scans == 2
    assert not projection._entries


def test_hit_racing_a_delete_discards_the_cached_page(store):
    store.rows['users/u/memory_items/a'] = {'status': 'active'}
    store.read()

    def mutate(state):
        if state.heads == 4:
            state.token = 'deleted'
            state.rows.clear()

    store.hook = mutate
    assert store.read() == []
    assert store.scans == 2


def test_fill_racing_a_mutation_is_never_published(store):
    def mutate(state):
        state.token = str(state.heads)

    store.hook = mutate
    store.read()
    store.read()
    assert store.scans == 2
    assert not projection._entries


def test_unavailable_head_falls_back_and_never_hides_query_errors(store, monkeypatch):
    def broken(*args):
        raise RuntimeError('unavailable')

    monkeypatch.setattr(projection, '_head', broken)
    assert store.read() == []
    assert store.scans == 1

    def broken_stream(*args):
        raise ValueError('source failure')

    monkeypatch.setattr(projection, 'budgeted_stream_list', broken_stream)
    with pytest.raises(ValueError, match='source failure'):
        store.read()


def test_deadline_is_checked_on_warm_hits_and_head_reads_are_charged(store):
    store.read()
    budget = ListReadBudget(deadline_monotonic=24, max_documents=100, clock=lambda: 0)
    store.read(budget=budget)
    assert budget.docs_scanned == 2
    exhausted = ListReadBudget(deadline_monotonic=0, max_documents=100, clock=lambda: 1)
    with pytest.raises(ListReadBudgetExhausted):
        store.read(budget=exhausted)


def test_exact_query_account_database_and_field_mask_are_in_key(store):
    store.read()
    store.query = store.query.select(['status'])
    store.read()
    store.query = store.client.collection('users/other/memory_items').limit(100)
    store.read()
    assert store.scans == 3


def test_retention_and_size_are_bounded(store, monkeypatch):
    monkeypatch.setattr(projection, 'MAX_ENTRY_BYTES', 1)
    store.read()
    assert not projection._entries
    monkeypatch.setattr(projection, 'MAX_ENTRY_BYTES', 1024)
    monkeypatch.setattr(projection, 'TTL_SECONDS', -1)
    store.read()
    store.read()
    assert store.scans == 3


def test_small_queries_bypass_head_cost_after_first_observation(store, monkeypatch):
    monkeypatch.setattr(projection, 'MIN_CACHE_ROWS', 3)
    assert store.read() == []
    before = store.reads
    assert store.read() == []
    assert store.reads - before == 1
    assert not projection._entries


def test_coverage_epoch_rotation_never_reuses_pre_gap_payloads(store, monkeypatch):
    store.rows = {f'users/u/memory_items/{i}': {'n': i} for i in range(3)}
    store.read()
    store.rows['users/u/memory_items/0'] = {'n': 'changed-by-old-writer'}
    monkeypatch.setenv('MEMORY_RELEASED_WRITERS_COVERED', 'v1:post-gap')
    assert store.read()[0].to_dict()['n'] == 'changed-by-old-writer'
    assert store.scans == 2


def test_mcp_cards_reuse_p1_version_and_respect_its_kill_switch(store, monkeypatch):
    monkeypatch.setenv('OMI_LIST_VERSION_EPOCH', 'p1-coverage')
    store.token = 'a' * 32
    store.query = store.client.collection('users/u/conversations').limit(100)
    store.rows = {f'users/u/conversations/{i}': {'n': i} for i in range(100)}
    first = projection.projected_stream_list(store.query, surface='mcp_cards')
    before = store.reads
    assert payloads(projection.projected_stream_list(store.query, surface='mcp_cards')) == payloads(first)
    assert store.reads - before == 2
    store.rows.clear()
    monkeypatch.setenv('OMI_LIST_PROJECTION_WRITER_ENABLED', 'false')
    assert projection.projected_stream_list(store.query, surface='mcp_cards') == []


def test_offset_is_charged_only_when_the_source_query_runs(store):
    store.rows = {f'users/u/memory_items/{i}': {'n': i} for i in range(3)}
    query = store.query.offset(10)
    cold = ListReadBudget(deadline_monotonic=24, max_documents=100, clock=lambda: 0)
    list(projection.projected_stream_iter(query, cold, surface='canonical_scan', offset_reads=10))
    assert cold.docs_scanned == 15
    warm = ListReadBudget(deadline_monotonic=24, max_documents=100, clock=lambda: 0)
    list(projection.projected_stream_iter(query, warm, surface='canonical_scan', offset_reads=10))
    assert warm.docs_scanned == 2


def test_stream_partial_prefix_retains_existing_budget_semantics(store, monkeypatch):
    monkeypatch.setenv('MEMORY_RELEASED_PROJECTION', 'off')
    store.rows = {f'users/u/memory_items/{i}': {'n': i} for i in range(5)}
    budget = ListReadBudget(deadline_monotonic=24, max_documents=3, clock=lambda: 0)
    actual = []
    with pytest.raises(ListReadBudgetExhausted):
        for row in projection.projected_stream_iter(store.query, budget, surface='canonical_scan'):
            actual.append(row.to_dict())
    assert actual == [{'n': 0}, {'n': 1}, {'n': 2}]
    assert not projection._entries


@pytest.mark.parametrize('warm', [False, True])
def test_last_read_preserves_mcp_source_prefix_instead_of_spending_it_on_heads(store, monkeypatch, warm):
    monkeypatch.setenv('OMI_LIST_VERSION_EPOCH', 'p1-coverage')
    store.token = 'a' * 32
    store.query = store.client.collection('users/u/conversations').limit(100)
    store.rows = {f'users/u/conversations/{i}': {'n': i} for i in range(3)}
    if warm:
        list(projection.projected_stream_iter(store.query, surface='mcp_cards'))
    before = store.heads
    budget = ListReadBudget(deadline_monotonic=24, max_documents=1, clock=lambda: 0)
    actual = []
    with pytest.raises(ListReadBudgetExhausted):
        for row in projection.projected_stream_iter(store.query, budget, surface='mcp_cards'):
            actual.append(row.to_dict())
    assert actual == [{'n': 0}]
    assert store.heads == before


def test_sync_scrape_keeps_projection_and_existing_billing_authority_counters():
    config = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    filters = config['spec']['endpoints'][0]['metricRelabeling']
    for name in (
        'omi_memory_released_projection_total',
        'omi_firestore_billed_reads_by_caller_total',
        'omi_firestore_billed_reads_by_origin_total',
        'omi_fsr_leader_lease_total',
    ):
        assert any(rule['action'] == 'keep' and re.fullmatch(rule['regex'], name) for rule in filters)


def test_reimport_preserves_projection_and_origin_observations():
    from database import firestore_read_origin as origin
    from testing.import_isolation import load_module_fresh, stub_modules

    backend = Path(__file__).resolve().parents[2]
    overflow = origin.FIRESTORE_ORIGIN_LABEL_OVERFLOW
    events = projection.EVENTS.labels(surface='canonical_scan', outcome='miss', origin='unset')
    before_overflow = overflow._value.get()
    before_events = events._value.get()
    # Repeat the archive fixture lifecycle: Python modules are evicted/restored,
    # while the real process-wide Prometheus registry retains its collectors.
    for _ in range(2):
        with stub_modules({}):
            fresh_origin = load_module_fresh(
                'database.firestore_read_origin', str(backend / 'database/firestore_read_origin.py')
            )
            fresh_projection = load_module_fresh(
                'database.released_memory_projection', str(backend / 'database/released_memory_projection.py')
            )
            assert fresh_origin.FIRESTORE_ORIGIN_LABEL_OVERFLOW is overflow
            assert fresh_projection.EVENTS is projection.EVENTS
            fresh_origin.MAX_ORIGINS = 0
            with fresh_origin.read_origin('job:reimport_test'):
                assert fresh_origin.current_read_origin() == 'overflow'
            fresh_projection.EVENTS.labels(surface='canonical_scan', outcome='miss', origin='unset').inc()
    assert overflow._value.get() == before_overflow + 2
    assert events._value.get() == before_events + 2
