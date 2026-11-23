"""Production cohort policy over synthetic loopback Firestore and real Postgres.

Only the policy's namespace/configuration inputs are adapted. The admission hash,
owner resolver, exact primary rereads, SQL, locks and page transactions are real.
No production namespace, cloud credentials or customer data are accessed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import threading
from types import SimpleNamespace

import pytest

from database.batch_pipeline_privacy import privacy_owner_key
from database.jobstore import cohort, cohort_due_parity, dual_store
from database.jobstore.connection import Pool
from database.jobstore.dual_store import DualStore, mirrored, read_current
from database.jobstore.postgres_store import PostgresStore
from database.jobstore.reconcile import process_page
from testing.store_fixtures import BackendUnavailable, build_backend, postgres_connect, required_backends
from utils.staging_fence import jobstore_shadow_admits

pytestmark = pytest.mark.integration


@pytest.fixture
def production_copy(monkeypatch):
    # This suite must never inherit the harness's optional remote/IAM route.
    assert not os.getenv('OMI_TEST_POSTGRES_IAM'), 'this proof requires local Postgres'
    psycopg = pytest.importorskip('psycopg')
    dsn = os.getenv('OMI_TEST_POSTGRES_DSN', '')
    if dsn:
        host = psycopg.conninfo.conninfo_to_dict(dsn).get('host', '')
        assert host and all(
            part.startswith('/') or part in {'localhost', '127.0.0.1', '::1'} for part in host.split(',')
        ), 'this proof requires an explicit loopback or Unix-socket Postgres host'
    harness = build_backend('emulator')  # rejects non-loopback Firestore before constructing a client
    try:
        connect = postgres_connect()
    except BackendUnavailable as exc:
        harness.close()
        if 'postgres' in required_backends():
            pytest.fail(f'required postgres backend unavailable: {exc}')
        pytest.skip(str(exc))
    pool = Pool('', size=3, connect=connect)
    shadow = PostgresStore(harness.namespace, pool=pool, customer_client=None)
    try:
        with pool.connection():
            pass  # reconciliation/parity may only borrow an already warm connection
        policy = {
            'OMI_DEPLOYMENT': 'prod',
            'OMI_ENV_STAGE': 'prod',
            'GOOGLE_CLOUD_PROJECT': 'based-hardware',
            'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware',
            'OMI_FIRESTORE_DATA_PLANE_PROJECT': 'based-hardware',
            'FIRESTORE_DATABASE_ID': '(default)',
            'JOBSTORE_SHADOW_NAMESPACES': 'batch_pipeline_prod',
            'JOBSTORE_PG_HOST': 'synthetic-policy-only',
            'JOBSTORE_PG_DATABASE': 'synthetic-policy-only',
            'JOBSTORE_PG_USER': 'synthetic-policy-only',
            'JOBSTORE_PRODUCTION_MIRROR': 'on',
            'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '5000',
        }

        def admits(namespace, *, owner_key=None):
            assert namespace == harness.namespace
            return jobstore_shadow_admits('batch_pipeline_prod', policy, owner_key=owner_key)

        # Never set a production client identity in os.environ: the real primary
        # remains the anonymous loopback client in its generated test namespace.
        monkeypatch.setattr(cohort, 'PROD_JOBSTORE_NAMESPACE', harness.namespace)
        monkeypatch.setattr(cohort, 'jobstore_shadow_admits', admits)
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setenv('OMI_DEPLOYMENT', 'local')  # production_policy_applies only excludes staging
        monkeypatch.delenv('JOBSTORE_SHADOW_WRITES', raising=False)
        monkeypatch.delenv('JOBSTORE_SHADOW_QUERY_PARITY', raising=False)
        monkeypatch.setattr(
            cohort_due_parity, 'jobstore_mirror_factory_admits', lambda namespace: namespace == harness.namespace
        )
        owners = {}
        for number in range(1000):
            uid = harness.uid(f'production-policy-{number}')
            key = privacy_owner_key(uid)
            selected = admits(harness.namespace, owner_key=key)
            if selected and jobstore_shadow_admits(
                'batch_pipeline_prod', {**policy, 'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '1'}, owner_key=key
            ):
                continue  # selected must leave the cohort after a valid 5000 -> 1 shrink
            owners.setdefault(selected, uid)
            if len(owners) == 2:
                break
        assert len(owners) == 2
        dual = DualStore(harness.store, shadow, inline=True, budget_s=5)
        yield SimpleNamespace(
            primary=harness.store,
            shadow=shadow,
            pool=pool,
            dual=dual,
            policy=policy,
            selected=owners[True],
            excluded=owners[False],
            psycopg=psycopg,
        )
    finally:
        try:
            shadow.purge_namespace()
        finally:
            pool.close()
            harness.close()


def _primary(stores, rows):
    for table, key, doc in rows:
        stores.primary.client.collection(f'{stores.primary.namespace}_{table}').document(key).set(doc)


def _copies(stores, rows):
    with stores.pool.connection() as conn:
        with conn.transaction():
            for table, key, doc in rows:
                stores.shadow.write_doc(conn, table, key, doc)


def _copy(stores, table, key):
    with stores.pool.connection() as conn:
        return stores.shadow.read_doc(conn, table, key)


def _job(uid, key, *, state='retry', at=1, **extra):
    return {
        'segment_id': key,
        'owner_id': uid,
        'owner_key': privacy_owner_key(uid),
        'state': state,
        'priority': 1,
        'merge_pending': False,
        'capture_at': at,
        'lease_until': at,
        'available_at': at,
        'enqueued_at': at,
        **extra,
    }


def _owner_rows(uid, suffix):
    owner = privacy_owner_key(uid)
    return [
        ('jobs', f'job-{suffix}', _job(uid, f'job-{suffix}', repair_lineage=['omitted'])),
        ('results', f'job-{suffix}', {'owner_key': owner, 'projection_state': 'completed'}),
        ('intakes', f'intake-{suffix}', {'owner_id': uid, 'segment_ids': [f'job-{suffix}']}),
        ('artifacts', f'artifact-{suffix}', {'owner_key': owner, 'cleaned': True}),
        ('owners', owner, {'revision': 1}),
        ('queues', f'1_{owner}', {'head': f'job-{suffix}', 'priority': 1}),
        ('merge_holds', owner, {'held': True}),
        ('allowance_holds', owner, {'active': True, 'check_at': 1}),
    ]


@pytest.mark.parametrize('route', ['mirror', 'refresh', 'direct'])
def test_all_copy_entry_points_apply_current_owner_policy(production_copy, route):
    stores = production_copy
    selected = _owner_rows(stores.selected, 'selected')
    excluded = _owner_rows(stores.excluded, 'excluded')
    malformed = [
        ('jobs', 'no-owner', {'state': 'retry'}),
        ('results', 'conflict', {'owner_id': stores.selected, 'owner_key': privacy_owner_key(stores.excluded)}),
        ('intakes', 'null-owner', {'owner_key': None}),
        ('artifacts', 'malformed-owner', {'owner_key': 'invalid'}),
        ('queues', 'bad-key', {'owner_key': privacy_owner_key(stores.selected)}),
    ]
    shared = [
        (table, 'shared', {'owner_key': privacy_owner_key(stores.selected), 'token': 'shared', 'expires_at': 1})
        for table in ('control', 'gpus', 'pull_claims')
    ]
    _primary(stores, selected + excluded + malformed + shared)
    # Model retained copies from an earlier cohort/implementation. Exclusion
    # must delete these rows, rather than merely refusing a new upsert.
    _copies(stores, excluded + malformed + shared + [('jobs', 'gone', _job(stores.selected, 'gone'))])
    keys = [(table, key) for table, key, _ in selected + excluded + malformed + shared] + [('jobs', 'gone')]
    if route == 'mirror':
        stores.dual.mirror({}, keys)
    elif route == 'refresh':
        stores.dual.refresh(keys)
    else:
        with stores.pool.connection() as conn:
            with conn.transaction():
                stores.dual.copy_current(conn, keys)
    for table, key, doc in selected:
        assert _copy(stores, table, key) == mirrored(doc, table)
    for table, key, _ in excluded + malformed + shared:
        assert _copy(stores, table, key) == {}
    assert _copy(stores, 'jobs', 'gone') == {}


@pytest.mark.parametrize('change', ['shrink', 'off', 'writes_off', 'mode_off'])
@pytest.mark.parametrize('kind', ['refresh', 'txn'])
def test_queued_work_rereads_primary_and_live_cohort(production_copy, monkeypatch, change, kind):
    stores = production_copy
    row = _job(stores.selected, 'queued', revision=1)
    _primary(stores, [('jobs', 'queued', row)])
    _copies(stores, [('jobs', 'queued', row)])
    stores.dual.inline = False
    monkeypatch.setattr(stores.dual, '_ensure_worker', lambda: None)
    if kind == 'refresh':
        stores.dual.refresh([('jobs', 'queued')])
    else:
        # Use a real Firestore transaction through DualStore; no ownership or
        # customer-policy fakes are needed for owner state.
        owner = privacy_owner_key(stores.selected)
        stores.dual.run(lambda tx: tx.put('owners', owner, {'revision': 1}))
        _copies(stores, [('owners', owner, {'revision': 1})])
    _primary(stores, [('jobs', 'queued', {**row, 'revision': 2})])
    if change == 'shrink':
        stores.policy['JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS'] = '1'
    elif change == 'off':
        stores.policy['JOBSTORE_PRODUCTION_MIRROR'] = 'off'
    elif change == 'mode_off':
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    else:
        monkeypatch.setenv('JOBSTORE_SHADOW_WRITES', 'off')
    item = stores.dual._queue.get_nowait()
    try:
        if item[0] == 'refresh':
            stores.dual.refresh_now(item[1])
        else:
            stores.dual.mirror(item[1], item[2])
    finally:
        stores.dual._queue.task_done()
    address = ('jobs', 'queued') if kind == 'refresh' else ('owners', privacy_owner_key(stores.selected))
    assert _copy(stores, *address) == {}
    assert stores.dual._queue.empty()


def test_copy_uses_current_document_after_queued_refresh(production_copy, monkeypatch):
    stores = production_copy
    row = _job(stores.selected, 'current', revision=1)
    _primary(stores, [('jobs', 'current', row)])
    stores.dual.inline = False
    monkeypatch.setattr(stores.dual, '_ensure_worker', lambda: None)
    stores.dual.refresh([('jobs', 'current')])
    _primary(stores, [('jobs', 'current', {**row, 'revision': 2})])
    _, keys, _ = stores.dual._queue.get_nowait()
    try:
        stores.dual.refresh_now(keys)
    finally:
        stores.dual._queue.task_done()
    assert _copy(stores, 'jobs', 'current')['revision'] == 2


@pytest.mark.parametrize('table', ['jobs', 'results', 'intakes', 'artifacts'])
def test_copy_census_retires_primary_ttl_after_dropped_final_refresh(production_copy, table):
    stores = production_copy
    doc = {'owner_key': privacy_owner_key(stores.selected), 'state': 'committed'}
    _primary(stores, [(table, 'expired', doc)])
    stores.dual.refresh_now([(table, 'expired')])
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    _primary(stores, [(table, 'expired', {**doc, 'expires_at': expired})])
    assert 'expires_at' not in _copy(stores, table, 'expired')
    stores.primary.client.collection(f'{stores.primary.namespace}_{table}').document('expired').delete()
    page = process_page(stores.dual, source='copy', table=table, apply=True)
    assert page.end_of_pass and page.cursor is None
    assert page.counts.scanned == page.counts.deleted == page.counts.stale == 1
    assert _copy(stores, table, 'expired') == {}


def test_present_primary_expiry_changes_and_hold_are_preserved(production_copy):
    stores = production_copy
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    future = expired + timedelta(days=10)
    variants = [
        ('extended', {'expires_at': future}),
        ('removed', {}),
        ('hold', {'expires_at': expired, 'legal_hold': True}),
        ('malformed', {'expires_at': 'unresolved-legacy-clock'}),
        ('missing', {'legacy': True}),
    ]
    rows = [('jobs', key, _job(stores.selected, key, **fields)) for key, fields in variants]
    _primary(stores, rows)
    _copies(stores, [('jobs', key, _job(stores.selected, key, expires_at=expired)) for key, _ in variants])
    page = process_page(stores.dual, source='copy', table='jobs', apply=True)
    assert page.counts.selected == page.counts.copied == 5
    assert page.counts.deleted == 0
    for table, key, doc in rows:
        assert _copy(stores, table, key) == doc
        assert read_current(stores.primary, [(table, key)])[(table, key)] == doc


def test_bounded_pages_resume_and_dry_run_does_not_publish_copies(production_copy):
    stores = production_copy
    rows = [('jobs', key, _job(stores.selected, key)) for key in ('a', 'b', 'e')]
    unknown = ('jobs', 'c', {'state': 'retry'})
    excluded = ('jobs', 'd', _job(stores.excluded, 'd'))
    _primary(stores, rows + [unknown, excluded])
    _copies(stores, [unknown, excluded])
    dry = process_page(stores.dual, source='primary', table='jobs', max_rows=2, max_primary_reads=4)
    assert dry.counts.scanned == dry.counts.selected == 2
    assert dry.counts.copied == 0 and dry.cursor and not dry.end_of_pass
    assert _copy(stores, 'jobs', 'a') == {}
    cursor = None
    pages = []
    while True:
        page = process_page(
            stores.dual, source='primary', table='jobs', cursor=cursor, max_rows=2, max_primary_reads=4, apply=True
        )
        pages.append(page)
        assert page.counts.scanned <= 2 and page.counts.primary_reads <= 4
        assert 'cursor' not in page.public_report()
        if page.end_of_pass:
            break
        assert page.cursor != cursor
        cursor = page.cursor
        assert len(pages) < 4
    assert [page.counts.scanned for page in pages] == [2, 2, 1]
    assert sum(page.counts.copied for page in pages) == 3
    assert sum(page.counts.unknown_owner for page in pages) == 1
    assert sum(page.counts.excluded for page in pages) == 1
    assert sum(page.counts.deleted for page in pages) == 2
    assert all(_copy(stores, table, key) == doc for table, key, doc in rows)
    assert _copy(stores, 'jobs', 'c') == _copy(stores, 'jobs', 'd') == {}
    stores.policy['JOBSTORE_PRODUCTION_MIRROR'] = 'off'
    page = process_page(stores.dual, source='copy', table='jobs', apply=True)
    assert page.counts.deleted == 3 and page.counts.excluded == 3
    assert all(_copy(stores, table, key) == {} for table, key, _ in rows)


def test_failed_apply_page_rolls_back_and_can_resume_same_checkpoint(production_copy, monkeypatch):
    stores = production_copy
    rows = [('jobs', key, _job(stores.selected, key)) for key in ('a', 'b', 'c')]
    _primary(stores, rows)
    first = process_page(stores.dual, source='primary', table='jobs', max_rows=1, apply=True)
    assert first.cursor and _copy(stores, 'jobs', 'a')
    real_write = stores.shadow.write_doc
    written = []

    def fail_second(conn, table, key, doc):
        real_write(conn, table, key, doc)
        written.append(key)
        if len(written) == 2:
            conn.execute('SELECT 1 / 0')  # real PG abort, after both writes within this page

    with monkeypatch.context() as patch:
        patch.setattr(stores.shadow, 'write_doc', fail_second)
        with pytest.raises(stores.psycopg.errors.DivisionByZero):
            process_page(stores.dual, source='primary', table='jobs', cursor=first.cursor, max_rows=2, apply=True)
    assert written == ['b', 'c']
    assert _copy(stores, 'jobs', 'a')
    assert _copy(stores, 'jobs', 'b') == _copy(stores, 'jobs', 'c') == {}
    page = process_page(stores.dual, source='primary', table='jobs', cursor=first.cursor, max_rows=2, apply=True)
    assert page.counts.copied == 2
    assert all(_copy(stores, table, key) == doc for table, key, doc in rows)


def test_statement_budget_failure_rolls_back_earlier_page_writes(production_copy):
    stores = production_copy
    rows = [('jobs', key, _job(stores.selected, key)) for key in ('a', 'b')]
    _primary(stores, rows)
    with pytest.raises(RuntimeError, match='statement budget exhausted'):
        process_page(stores.dual, source='primary', table='jobs', max_rows=2, max_statements=12, apply=True)
    assert all(_copy(stores, table, key) == {} for table, key, _ in rows)


def test_purge_barrier_covers_real_primary_read_before_deletion(production_copy, monkeypatch):
    stores = production_copy
    row = _job(stores.selected, 'race')
    _primary(stores, [('jobs', 'race', row)])
    read, release, entering_purge, purged = (threading.Event() for _ in range(4))
    errors = []
    monkeypatch.setattr(dual_store, 'PURGE_SETTLE_S', 0)
    original_reconcile = stores.dual._reconcile_owner

    def reconcile(uid):
        entering_purge.set()
        return original_reconcile(uid)

    monkeypatch.setattr(stores.dual, '_reconcile_owner', reconcile)

    def slow_reader(primary, keys):
        docs = read_current(primary, keys)
        read.set()
        assert release.wait(10)
        return docs

    def copy():
        try:
            with stores.pool.connection() as conn:
                with conn.transaction():
                    stores.dual.copy_current(conn, [('jobs', 'race')], reader=slow_reader)
        except BaseException as exc:
            errors.append(exc)

    def purge():
        try:
            stores.dual.purge_owner_now(stores.selected)
            purged.set()
        except BaseException as exc:
            errors.append(exc)

    copier = threading.Thread(target=copy)
    purger = threading.Thread(target=purge)
    copier.start()
    try:
        assert read.wait(10)
        stores.primary.client.collection(f'{stores.primary.namespace}_jobs').document('race').delete()
        purger.start()
        assert entering_purge.wait(10)
        assert not purged.wait(0.1), 'purge must wait for the pre-deletion copy to commit'
    finally:
        release.set()
        copier.join(15)
        if purger.ident is not None:
            purger.join(15)
    assert not copier.is_alive() and not purger.is_alive()
    assert errors == [] and purged.is_set()
    assert _copy(stores, 'jobs', 'race') == {}


@pytest.mark.parametrize('state', ['leased', 'retry', 'result_ready'])
def test_sampled_due_keeps_selected_prefix_and_allows_valid_later_hints(production_copy, state):
    stores = production_copy
    rows = [
        ('jobs', 'a-excluded', _job(stores.excluded, 'a-excluded', state=state, at=1)),
        ('jobs', 'b-selected', _job(stores.selected, 'b-selected', state=state, at=2)),
        ('jobs', 'c-later', _job(stores.selected, 'c-later', state=state, at=3)),
    ]
    _primary(stores, rows)
    stores.dual.refresh_now([(table, key) for table, key, _ in rows])
    assert stores.primary.due(state, 4, 2) == ['a-excluded', 'b-selected']
    assert cohort_due_parity.compare_sampled_due(stores.primary, stores.shadow, (state, 4, 2), {}, 5) == 'match'


@pytest.mark.parametrize('problem', ['missing', 'excluded', 'stale'])
def test_sampled_due_rejects_missing_selected_prefix_and_invalid_hints(production_copy, problem):
    stores = production_copy
    selected = ('jobs', 'selected', _job(stores.selected, 'selected'))
    excluded = ('jobs', 'excluded', _job(stores.excluded, 'excluded'))
    _primary(stores, [selected, excluded])
    if problem != 'missing':
        _copies(stores, [selected])
    if problem == 'excluded':
        _copies(stores, [excluded])
    elif problem == 'stale':
        _copies(stores, [('jobs', 'selected', {**selected[2], 'revision': 'old'})])
    assert cohort_due_parity.compare_sampled_due(stores.primary, stores.shadow, ('retry', 4, 10), {}, 5) == 'mismatch'


def test_sampled_due_returns_unknown_when_source_changes_between_observations(production_copy, monkeypatch):
    stores = production_copy
    row = _job(stores.selected, 'moving')
    _primary(stores, [('jobs', 'moving', row)])
    stores.dual.refresh_now([('jobs', 'moving')])
    original = cohort_due_parity.read_current
    observations = []

    def moving(primary, keys):
        docs = original(primary, keys)
        observations.append(True)
        if len(observations) == 1:
            _primary(stores, [('jobs', 'moving', {**row, 'revision': 2})])
        return docs

    monkeypatch.setattr(cohort_due_parity, 'read_current', moving)
    assert cohort_due_parity.compare_sampled_due(stores.primary, stores.shadow, ('retry', 4, 10), {}, 5) == 'unknown'
    assert len(observations) == 2


def test_sampled_due_without_selected_observations_is_unknown(production_copy):
    stores = production_copy
    _primary(stores, [('jobs', 'excluded', _job(stores.excluded, 'excluded'))])
    assert cohort_due_parity.compare_sampled_due(stores.primary, stores.shadow, ('retry', 4, 10), {}, 5) == 'unknown'
