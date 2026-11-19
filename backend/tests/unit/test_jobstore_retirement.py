"""Worker target/cohort gating, fairness, missing-schema and total tick budgets."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from database.jobstore import retirement as worker
from database.jobstore.reconcile import PageCounts, PageResult
from database.batch_pipeline_retirement_metrics import RetirementPageReason


@pytest.fixture
def setup(monkeypatch):
    for name in list(__import__('os').environ):
        if name.startswith('JOBSTORE_'):
            monkeypatch.delenv(name)
    for name in ('HOST', 'DATABASE', 'USER'):
        monkeypatch.setenv('JOBSTORE_PG_' + name, 'synthetic')
    monkeypatch.setattr(worker, 'is_staging', lambda: False)
    monkeypatch.setattr(worker, 'jobstore_production_context_matches', lambda: True)
    monkeypatch.setattr(worker, 'jobstore_production_mirror_configured', lambda: False)
    clock = [100.0]
    monkeypatch.setattr(worker.time, 'monotonic', lambda: clock[0])
    errors, pages = [], []
    monkeypatch.setattr(worker, 'page_error', lambda *args: errors.append(args))

    class Conn:
        exists = True
        delay = 0

        def wait(self, generator, interval=None):
            raise AssertionError("no socket in unit fake")

        @contextmanager
        def transaction(self):
            yield

        def execute(self, *_):
            return self

        def fetchone(self):
            clock[0] += self.delay
            return ('jobstore_retirement_cursor' if self.exists else None,)

    conn = Conn()

    class Pool:
        @contextmanager
        def connection(self, **kwargs):
            assert 0 < kwargs['timeout'] <= worker.WARMUP_SECONDS
            yield conn

    pool = Pool()
    monkeypatch.setattr(worker, 'copy_pools', lambda *_: SimpleNamespace(normal=pool, erasure=object()))
    monkeypatch.setattr(
        worker, 'process_page', lambda dual, **kwargs: (pages.append(kwargs), PageResult(PageCounts(), True, None))[1]
    )
    rotation = worker.Retirement()
    rotation._dual = object()
    return SimpleNamespace(
        rotation=rotation,
        clock=clock,
        pages=pages,
        errors=errors,
        conn=conn,
        store=SimpleNamespace(namespace='batch_pipeline_prod'),
    )


def tick(world):
    world.rotation.tick(world.store)
    world.clock[0] += 20


def test_default_on_complete_target_mirror_off_only_retires_and_round_robins(setup):
    for _ in worker.MIRRORED_TABLES:
        tick(setup)
    assert len(setup.pages) == len(worker.MIRRORED_TABLES)
    assert {page['table'] for page in setup.pages} == worker.MIRRORED_TABLES
    assert {page['source'] for page in setup.pages} == {'copy'}
    assert all(page['apply'] and 0 < page['budget_s'] <= 3 for page in setup.pages)


def test_primary_backfill_only_when_production_mirror_configured(setup, monkeypatch):
    from database import batch_pipeline_shadow_hook as hook

    monkeypatch.setattr(worker, 'jobstore_production_mirror_configured', lambda: True)
    monkeypatch.setattr(hook, 'shadow_mode_enabled', lambda: True)
    monkeypatch.setattr(worker, 'shadow_writes_enabled', lambda: True)
    for _ in range(22):
        tick(setup)
    assert len({(page['source'], page['table']) for page in setup.pages}) == 22


@pytest.mark.parametrize('mode,writes', [(False, True), (True, False), (False, False)])
def test_mirror_configuration_alone_never_schedules_primary_pages(setup, monkeypatch, mode, writes):
    # Primary pages read Firestore; with copying off they would only spend reads.
    from database import batch_pipeline_shadow_hook as hook

    monkeypatch.setattr(worker, 'jobstore_production_mirror_configured', lambda: True)
    monkeypatch.setattr(hook, 'shadow_mode_enabled', lambda: mode)
    monkeypatch.setattr(worker, 'shadow_writes_enabled', lambda: writes)
    for _ in range(22):
        tick(setup)
    assert {page['source'] for page in setup.pages} == {'copy'}


@pytest.mark.parametrize('gate', ['kill', 'missing_target', 'partial_target', 'context', 'namespace', 'budget'])
def test_refusal_never_opens_page(setup, monkeypatch, gate):
    if gate == 'kill':
        monkeypatch.setenv('JOBSTORE_RETIREMENT_ENABLED', 'off')
    elif gate == 'missing_target':
        for name in ('HOST', 'DATABASE', 'USER'):
            monkeypatch.delenv('JOBSTORE_PG_' + name)
    elif gate == 'partial_target':
        monkeypatch.delenv('JOBSTORE_PG_HOST')
    elif gate == 'context':
        monkeypatch.setattr(worker, 'jobstore_production_context_matches', lambda: False)
    elif gate == 'namespace':
        setup.store.namespace = 'unknown'
    else:
        monkeypatch.setenv('JOBSTORE_RETIREMENT_PAGE_SECONDS', 'nan')
    tick(setup)
    assert setup.pages == []


def test_missing_schema_noops_and_counts_without_migration(setup):
    setup.conn.exists = False
    tick(setup)
    assert setup.pages == [] and setup.errors[0][-1] == RetirementPageReason.SCHEMA_MISSING


def test_warmup_is_outside_page_budget_but_inside_total_tick_budget(setup):
    setup.conn.delay = worker.TICK_BUDGET_SECONDS + 1
    tick(setup)
    assert setup.pages == [] and setup.errors[0][-1] == RetirementPageReason.TIMEOUT


def test_failed_page_is_isolated_throttled_and_next_table_can_progress(setup, monkeypatch):
    def fail(*_, **kwargs):
        setup.pages.append(kwargs)
        raise RuntimeError('private cursor or provider error text')

    monkeypatch.setattr(worker, 'process_page', fail)
    setup.rotation.tick(setup.store)
    setup.rotation.tick(setup.store)
    assert len(setup.pages) == 1
    tick(setup)
    tick(setup)
    assert len(setup.pages) == 2 and setup.pages[0]['table'] != setup.pages[1]['table']
    assert all(error[-1] == RetirementPageReason.OPERATION_FAILED for error in setup.errors)


def test_collectors_export_in_private_registry_with_mirror_off_and_rotation_lag_uses_db_timestamp(monkeypatch):
    from datetime import datetime, timezone
    from prometheus_client import CollectorRegistry
    from database import batch_pipeline_shadow_hook as hook
    from database import batch_pipeline_retirement_metrics as metrics

    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    registry = CollectorRegistry()
    for collector in hook.shadow_parity_collectors():
        registry.register(collector)
    created = datetime.fromtimestamp(100, timezone.utc)
    monkeypatch.setattr(metrics.time, 'time', lambda: 150)
    metrics.observe('batch_pipeline_dev', 'copy', 'jobs', 0, (created, None, created))
    labels = {'namespace': 'batch_pipeline_dev', 'source': 'copy', 'table': 'jobs'}
    assert registry.get_sample_value('omi_jobstore_retirement_rotation_lag_seconds', labels) == 50
    assert registry.get_sample_value('omi_jobstore_retirement_rotation_completed_timestamp_seconds', labels) == 0
    completed = datetime.fromtimestamp(140, timezone.utc)
    metrics.observe('batch_pipeline_dev', 'copy', 'jobs', 1, (created, completed, completed))
    assert registry.get_sample_value('omi_jobstore_retirement_rotation_lag_seconds', labels) == 10
    monkeypatch.setattr(metrics.time, 'time', lambda: 170)
    assert registry.get_sample_value('omi_jobstore_retirement_rotation_lag_seconds', labels) == 30
    future = datetime.fromtimestamp(500, timezone.utc)
    metrics.observe('batch_pipeline_dev', 'copy', 'jobs', 0, (created, future, future))
    lag = registry.get_sample_value('omi_jobstore_retirement_rotation_lag_seconds', labels)
    assert lag != lag  # NaN: a future database clock is unknown, never fresh
