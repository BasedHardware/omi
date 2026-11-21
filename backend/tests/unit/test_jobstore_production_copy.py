"""Production mirror integration: lazy admission, current cohort, erasure and parity boundaries."""

from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from copy import deepcopy

import pytest
from psycopg import sql

from database import batch_pipeline_shadow_hook as hook
from database import batch_pipeline_store
from database.batch_pipeline_privacy import privacy_owner_key
from database.jobstore import connection, copy_connections, dual_store, index_config, serving_parity
from database.jobstore.dual_store import DualStore
from database.jobstore.index_store import IndexStore
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.staging_fence import jobstore_mirror_factory_admits, jobstore_shadow_admits

NAMESPACE = 'batch_pipeline_prod'
PROD_ENV = {
    'OMI_DEPLOYMENT': 'prod',
    'OMI_ENV_STAGE': 'prod',
    'GOOGLE_CLOUD_PROJECT': 'based-hardware',
    'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware',
    'OMI_FIRESTORE_DATA_PLANE_PROJECT': 'based-hardware',
    'FIRESTORE_DATABASE_ID': '(default)',
    'JOBSTORE_SHADOW_NAMESPACES': NAMESPACE,
    'JOBSTORE_PRODUCTION_MIRROR': 'on',
    'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '10000',
    'JOBSTORE_PG_HOST': 'synthetic-target-never-dialed',
    'JOBSTORE_PG_DATABASE': 'synthetic-database',
    'JOBSTORE_PG_USER': 'synthetic-runtime',
    'BATCH_JOBSTORE_MODE': 'shadow',
}


class Conn:
    def __init__(self, shadow):
        self.shadow, self.result = shadow, []

    def execute(self, query, params=None):
        text = query.as_string(None) if isinstance(query, sql.Composable) else str(query)
        self.shadow.statements.append((text, params))
        self.result = []
        # Only owner-census SQL needs results; normal copy reads/writes use
        # Shadow's document seam. Match the current SQL's owner predicates.
        if text.startswith('SELECT key FROM jobs'):
            self.result = [
                (key,)
                for (table, key), doc in self.shadow.rows.items()
                if table == 'jobs' and (doc.get('owner_key') == params[1] or doc.get('owner_id') == params[2])
            ]
        elif text.startswith('SELECT key FROM results'):
            self.result = [
                (key,)
                for (table, key), doc in self.shadow.rows.items()
                if table == 'results' and (doc.get('owner_key') == params[1] or doc.get('owner_id') == params[2])
            ]
        elif text.startswith('SELECT tbl, key FROM docs'):
            self.result = [
                (table, key)
                for (table, key), doc in self.shadow.rows.items()
                if table in params[1] and (doc.get('owner_key') == params[2] or doc.get('owner_id') == params[3])
            ]
        elif text.startswith('SELECT key FROM docs') and "tbl = 'gpus'" in text:
            self.result = [(key,) for table, key in self.shadow.rows if table == 'gpus']
        return self

    def fetchall(self):
        return self.result

    @contextmanager
    def transaction(self):
        before = deepcopy(self.shadow.rows)
        try:
            yield
        except BaseException:
            self.shadow.rows = before
            raise


class Pool:
    def __init__(self, shadow):
        self.shadow, self.connections, self.closed = shadow, 0, False

    @contextmanager
    def connection(self, timeout=30, **kwargs):
        assert timeout > 0
        self.connections += 1
        yield Conn(self.shadow)

    def close(self):
        self.closed = True


class Shadow:
    def __init__(self):
        self.namespace = NAMESPACE
        self.rows, self.upserts, self.deletes, self.statements = {}, [], [], []
        self.pool = Pool(self)

    def read_doc(self, conn, table, key):
        return deepcopy(self.rows.get((table, key), {}))

    def write_doc(self, conn, table, key, doc):
        self.upserts.append((table, key, deepcopy(doc)))
        self.rows[(table, key)] = deepcopy(doc)

    def delete_doc(self, conn, table, key):
        self.deletes.append((table, key))
        self.rows.pop((table, key), None)


@pytest.fixture
def production(monkeypatch):
    for name in ('FIRESTORE_EMULATOR_HOST', 'GCLOUD_PROJECT', 'GCP_PROJECT', 'FIREBASE_PROJECT_ID'):
        monkeypatch.delenv(name, raising=False)
    for name in (
        'JOBSTORE_SHADOW_WRITES',
        'JOBSTORE_INDEX_READS',
        'JOBSTORE_INDEX_QUERIES',
        'JOBSTORE_SHADOW_QUERY_PARITY',
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in PROD_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(dual_store, '_SHADOWED', {})
    monkeypatch.setattr(copy_connections, '_pools', None)
    monkeypatch.setattr(index_config, '_INDEXED', {})
    primary, shadow = SimStore(CustomerData(), namespace=NAMESPACE), Shadow()
    mirror = DualStore(primary, shadow, inline=True)
    return primary, shadow, mirror


def owner():
    # Pick a synthetic owner that leaves a 1-bps cohort, using the stable public
    # admission domain rather than relying on a particular hash fixture.
    for number in range(100):
        uid = f'synthetic-copy-owner-{number}'
        key = privacy_owner_key(uid)
        bucket = int(hashlib.sha256(f'omi:jobstore-production-mirror:v1:{key}'.encode()).hexdigest(), 16) % 10000
        if bucket > 0:
            return uid, key
    raise AssertionError('no synthetic nonzero cohort bucket')


def test_factory_admits_lazy_production_handle_without_admitting_namespace_rows(production, monkeypatch):
    primary, _, _ = production
    dials = []

    def connector(*args):
        def dial():
            dials.append(args)
            pytest.fail('lazy production factory attempted a connection')

        return dial

    monkeypatch.setattr(connection, 'iam_connector', connector)
    monkeypatch.setattr(dual_store.importlib.util, 'find_spec', lambda name: object())
    assert jobstore_mirror_factory_admits(NAMESPACE)
    assert not jobstore_shadow_admits(NAMESPACE)
    store = hook.shadow_from_env(primary)
    assert isinstance(store, DualStore) and store.primary is primary
    assert dual_store._SHADOWED[NAMESPACE] is store and dials == []
    store.shadow.pool.close()


def test_factory_handle_still_requires_owner_and_omits_shared_rows(production):
    primary, shadow, mirror = production
    _, key = owner()
    primary.rows.update(
        {
            ('jobs', 'selected'): {'owner_key': key, 'state': 'ready', 'repair_lineage': 'private'},
            ('jobs', 'unknown'): {'state': 'ready'},
            ('control', 'shared'): {'owners': [key], 'active': True},
            ('gpus', 'gpu'): {'owner_key': key, 'segment_id': 'private-segment'},
        }
    )
    with shadow.pool.connection() as conn, conn.transaction():
        mirror.copy_current(conn, sorted(primary.rows))
    assert set(shadow.rows) == {('jobs', 'selected')}
    assert shadow.rows[('jobs', 'selected')] == {'owner_key': key, 'state': 'ready'}
    statements = [query for query, _ in shadow.statements]
    assert 'pg_advisory_xact_lock_shared' in statements[0]
    assert all('pg_advisory_xact_lock(' in query for query in statements[1:])


@pytest.mark.parametrize('change', ['shrink', 'writes_off', 'mirror_off', 'mode_off'])
@pytest.mark.parametrize('queued_kind', ['refresh', 'txn'])
def test_queued_copy_rechecks_live_policy_and_retires_retained_rows(production, monkeypatch, change, queued_kind):
    primary, shadow, mirror = production
    uid, key = owner()
    primary.customer.add_user(uid)
    address = ('jobs', 'queued')
    primary.rows[address] = {'owner_key': key, 'version': 2}
    shadow.rows[address] = {'owner_key': key, 'version': 1}
    mirror.inline = False
    monkeypatch.setattr(mirror, '_ensure_worker', lambda: None)  # controlled executor boundary
    if queued_kind == 'refresh':
        mirror.refresh([address])
    else:
        mirror.run(lambda tx: tx.put(*address, {'owner_id': uid, 'owner_key': key, 'version': 3}))
    assert mirror._queue.qsize() == 1
    if change == 'shrink':
        monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', '1')
    elif change == 'mode_off':
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    else:
        monkeypatch.setenv('JOBSTORE_SHADOW_WRITES' if change == 'writes_off' else 'JOBSTORE_PRODUCTION_MIRROR', 'off')
    kind, first, second = mirror._queue.get_nowait()
    try:
        if kind == 'refresh':
            mirror.refresh_now(first)
        else:
            mirror.mirror(first, second)
    finally:
        mirror._queue.task_done()
    assert address not in shadow.rows and shadow.upserts == []
    assert shadow.deletes == [address]


def test_cold_outside_transaction_hook_constructs_and_populates_prod_copy(production, monkeypatch):
    primary, shadow, mirror = production
    _, key = owner()
    primary.rows[('jobs', 'cold')] = {'owner_key': key, 'version': 1}
    built = []

    def configured(actual_primary):
        assert actual_primary is primary
        built.append(actual_primary.namespace)
        return mirror

    class FirestoreFactory:
        def __new__(cls, namespace):
            assert namespace == NAMESPACE
            return primary

    monkeypatch.setattr(batch_pipeline_store, 'FirestoreStore', FirestoreFactory)
    monkeypatch.setattr(dual_store, '_configured_copy', configured)
    hook.mirror_refresh(NAMESPACE, [('jobs', 'cold')])
    assert built == [NAMESPACE] and dual_store._SHADOWED[NAMESPACE] is mirror
    assert shadow.rows[('jobs', 'cold')] == {'owner_key': key, 'version': 1}


def test_captured_shared_excluded_and_unknown_payloads_never_enter_async_queue(production, monkeypatch):
    primary, _, mirror = production
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', '5000')
    candidates = [privacy_owner_key(f'synthetic-capture-owner-{n}') for n in range(100)]
    key = next(key for key in candidates if jobstore_shadow_admits(NAMESPACE, owner_key=key))
    excluded = next(key for key in candidates if not jobstore_shadow_admits(NAMESPACE, owner_key=key))
    primary.rows[('control', 'shared')] = {'owners': [key], 'private_payload': 'shared-secret'}
    primary.rows[('jobs', 'unknown')] = {'private_payload': 'unknown-secret'}
    primary.rows[('jobs', 'excluded')] = {'owner_key': excluded, 'private_payload': 'excluded-secret'}
    primary.rows[('jobs', 'selected')] = {'owner_key': key, 'value': 'selected'}
    mirror.inline = False
    monkeypatch.setattr(mirror, '_ensure_worker', lambda: None)
    addresses = sorted(set(primary.rows) | {('control', 'absent-shared'), ('jobs', 'absent-unknown')})
    result = mirror.run(lambda tx: [tx.get(*address) for address in addresses])
    assert len(result) == 6  # primary caller still gets its real transaction reads
    kind, reads, writes = mirror._queue.get_nowait()
    mirror._queue.task_done()
    assert kind == 'txn' and writes == []
    assert reads == {('jobs', 'selected'): {'owner_key': key, 'value': 'selected'}}
    assert all(secret not in repr(reads) for secret in ('shared-secret', 'unknown-secret', 'excluded-secret'))


@pytest.mark.parametrize('cached', [True, False])
def test_privacy_purge_reaches_retained_target_with_all_mirror_controls_off(production, monkeypatch, cached):
    primary, shadow, mirror = production
    uid, key = owner()
    shadow.rows[('jobs', 'erased')] = {'owner_key': key, 'owner_id': uid}
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    monkeypatch.setenv('JOBSTORE_SHADOW_WRITES', 'off')
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR', 'off')
    monkeypatch.setenv('JOBSTORE_SHADOW_NAMESPACES', '')
    monkeypatch.setattr(dual_store, 'PURGE_SETTLE_S', 0)
    built = []
    if cached:
        dual_store._SHADOWED[NAMESPACE] = mirror
    else:

        def configured(actual_primary):
            built.append(actual_primary.namespace)
            return mirror

        monkeypatch.setattr(dual_store, '_configured_copy', configured)
    assert not jobstore_mirror_factory_admits(NAMESPACE)
    assert hook.purge_owner(NAMESPACE, uid) >= 1
    assert ('jobs', 'erased') not in shadow.rows and shadow.upserts == []
    assert built == ([] if cached else [NAMESPACE])
    assert not shadow.pool.closed  # cold and cached handles now borrow process-owned pools
    assert any('pg_advisory_xact_lock(hashtextextended' in query for query, _ in shadow.statements)


def test_previously_handed_out_index_falls_back_after_production_config_kill(production, monkeypatch):
    primary, shadow, mirror = production
    _, key = owner()
    primary.apply(('jobs', 'primary'), {'owner_key': key, 'state': 'leased', 'lease_until': 0})
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'index')
    monkeypatch.setattr(dual_store, '_configured_copy', lambda actual_primary: mirror)
    store = hook.shadow_from_env(primary)
    assert isinstance(store, IndexStore) and store.enabled()
    assert store.due('leased', 1) == ['primary']
    monkeypatch.setattr(store._index, 'due', lambda *args: pytest.fail('unproven production coverage'))
    assert store.due('leased', 1) == ['primary']  # configuration is not complete-query coverage
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR', 'off')
    assert not store.enabled()
    assert store.due('leased', 1) == ['primary']
    assert hook.shadow_from_env(primary) is primary
    assert shadow.pool.connections == 0


@pytest.mark.parametrize(
    'query,args,transaction',
    [('get', ('jobs', 'private-key'), True), ('service_frontier', (0,), True), ('control_candidates', (0, 10), False)],
)
def test_unimplemented_production_query_projection_is_unknown_without_database_reads(
    production, monkeypatch, query, args, transaction
):
    primary, shadow, _ = production
    monkeypatch.setattr(serving_parity, 'query_value', lambda *a, **k: pytest.fail('whole-population observation'))
    metric = serving_parity.SERVING_PARITY_TOTAL.labels(query=query, outcome='unknown')
    before = metric._value.get()
    assert serving_parity.compare_serving_query(primary, shadow, query, *args, transaction=transaction) == 'unknown'
    assert metric._value.get() == before + 1 and shadow.pool.connections == 0


def test_convergence_after_owner_exclusion_records_unknown_instead_of_false_divergence(production, monkeypatch):
    primary, shadow, mirror = production
    _, key = owner()
    primary.rows[('jobs', 'j')] = {'owner_key': key, 'version': 2}
    shadow.rows[('jobs', 'j')] = {'owner_key': key, 'version': 1}
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', '1')
    metric = dual_store.SHADOW_CONVERGENCE_TOTAL.labels(table='jobs', outcome='unknown')
    before = metric._value.get()
    mirror._check_convergence((0, 1, 'jobs', 'j', time.monotonic(), 0))
    assert metric._value.get() == before + 1 and mirror._pending == []


@pytest.mark.parametrize('table', ['jobs', 'control'])
def test_absent_unresolved_rows_cannot_inflate_production_parity(production, monkeypatch, table):
    primary, _, mirror = production
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', '1')
    metric = dual_store.SHADOW_PARITY_TOTAL.labels(table=table, op='read', outcome='match')
    before = metric._value.get()
    assert mirror.run(lambda tx: tx.get(table, 'absent-unknown')) == {}
    assert metric._value.get() == before


def test_cached_production_copy_cannot_escape_kills_through_invalid_staging_context(production, monkeypatch):
    primary, shadow, mirror = production
    uid, key = owner()
    primary.rows[('jobs', 'selected')] = {'owner_id': uid, 'owner_key': key}
    primary.rows[('control', 'shared')] = {'owners': [key]}
    monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    monkeypatch.setenv('JOBSTORE_SHADOW_WRITES', 'off')
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR', 'off')
    assert not jobstore_mirror_factory_admits(NAMESPACE)
    with shadow.pool.connection() as conn:
        with conn.transaction():
            mirror.copy_current(conn, sorted(primary.rows))
    assert shadow.upserts == [] and shadow.rows == {}
