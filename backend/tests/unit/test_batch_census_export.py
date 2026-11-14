"""Census exporter, gauge publishing and rendered alarm contracts (SCA-2119).

The exporter is the only production reader of the registry. These tests pin the
two things that can silently make it lie: the query shape (a wrong filter or a
document read) and the age sentinel (a stock with no ageable clock must never
report a healthy zero).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.batch_census import (
    COLLECTION,
    COLLECTION_GROUP,
    ENTRIES,
    AgeCutoff,
    BY_KEY,
)
from database import batch_census_export
from database.batch_census_export import StockSample, sample_entry
from utils.observability import batch_census as metrics

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / 'backend/charts/monitoring'
GENERATOR = REPO / 'backend/scripts/generate_batch_census_alerts.py'
SCHEDULER = REPO / 'backend/deploy/scheduler/jobs.yaml'


class FakeSnapshot:
    def __init__(self, values):
        self._values = values

    def to_dict(self):
        return dict(self._values)


class FakeQuery:
    """Records the query shape; streams a scripted first row."""

    def __init__(self, store, name, scope, *, filters=(), order=None, projection=None, limit=None):
        self.store = store
        self.name = name
        self.scope = scope
        self.filters = tuple(filters)
        self.order = order
        self.projection = projection
        self.limit_value = limit

    def _clone(self, **changes):
        state = {
            'filters': self.filters,
            'order': self.order,
            'projection': self.projection,
            'limit': self.limit_value,
        }
        state.update(changes)
        return FakeQuery(self.store, self.name, self.scope, **state)

    def where(self, filter=None, **_kwargs):
        return self._clone(filters=self.filters + ((filter.field_path, filter.op_string, filter.value),))

    def select(self, fields):
        return self._clone(projection=tuple(fields))

    def order_by(self, field):
        return self._clone(order=field)

    def limit(self, value):
        return self._clone(limit=value)

    def count(self):
        query = self

        class _Aggregation:
            def get(self, timeout=None):
                query.store.calls.append(('count', query.name, query.scope, query.filters, timeout))
                return [[SimpleNamespace(value=query.store.counts.get(query.name, 0))]]

        return _Aggregation()

    def stream(self, timeout=None):
        self.store.calls.append(('stream', self.name, self.scope, self.filters, self.order, self.projection, timeout))
        row = self.store.oldest.get(self.name)
        return iter([FakeSnapshot({self.order: row})] if row is not None else [])


class FakeClient:
    def __init__(self, counts=None, oldest=None):
        self.counts = counts or {}
        self.oldest = oldest or {}
        self.calls = []

    def collection(self, name):
        return FakeQuery(self, name, COLLECTION)

    def collection_group(self, name):
        return FakeQuery(self, name, COLLECTION_GROUP)


def test_count_and_oldest_use_the_production_collection_without_reading_content():
    client = FakeClient(counts={'batch_pipeline_prod_jobs': 7}, oldest={})
    entry = BY_KEY['batch:ready']

    sample = sample_entry(client, entry, now=1_000.0, timeout=9.0)

    assert sample == StockSample(units=7, oldest_at=None)
    counts = [call for call in client.calls if call[0] == 'count']
    assert [call[1] for call in counts] == ['batch_pipeline_prod_jobs']
    assert counts[0][3] == (('state', '==', 'ready'),)
    streams = [call for call in client.calls if call[0] == 'stream']
    assert [call[1] for call in streams] == ['batch_pipeline_prod_jobs']
    # Exactly the clock field: no document content can reach a log or a label.
    assert {call[5] for call in streams} == {('enqueued_at',)}


def test_entry_without_a_clock_never_issues_an_oldest_read():
    client = FakeClient(counts={'batch_pipeline_prod_results': 3, 'batch_pipeline_dev_results': 0})
    entry = BY_KEY['batch_projection:erased']

    sample = sample_entry(client, entry, now=1_000.0, timeout=1.0)

    assert sample.units == 3
    assert sample.oldest_at is None
    assert not [call for call in client.calls if call[0] == 'stream']


def test_age_cutoff_is_resolved_from_the_sample_moment():
    entry = BY_KEY['batch:deep_backlog']
    cutoff = [value for _field, _op, value in entry.filters if isinstance(value, AgeCutoff)]
    assert len(cutoff) == 1

    client = FakeClient(counts={'batch_pipeline_prod_jobs': 4, 'batch_pipeline_dev_jobs': 0})
    sample_entry(client, entry, now=10_000_000.0, timeout=1.0)

    count = [call for call in client.calls if call[0] == 'count'][0]
    assert ('enqueued_at', '<', 10_000_000.0 - cutoff[0].seconds) in count[3]


def test_collection_group_scope_is_used_for_group_stocks():
    client = FakeClient(counts={'stt_cap_holds': 2})
    entry = BY_KEY['cap_hold:held']

    sample_entry(client, entry, now=1_000.0, timeout=1.0)

    assert [call[2] for call in client.calls] == [COLLECTION_GROUP, COLLECTION_GROUP]


def test_one_failing_stock_does_not_blind_the_others(monkeypatch):
    import asyncio

    from utils.sync import batch_census as sweep

    def flaky(client, entry, *, now, timeout):
        if entry.key == 'batch:ready':
            raise RuntimeError('index missing')
        return StockSample(units=1, oldest_at=None)

    monkeypatch.setattr(batch_census_export, 'sample_entry', flaky)
    result = asyncio.run(sweep.snapshot(firestore_client=FakeClient(), now=1_000.0, concurrency=2))

    assert result['status'] == sweep.OUTCOME_PARTIAL
    assert result['failed'] == 1
    assert result['stocks'] == len(ENTRIES) - 1


def test_disabled_census_reports_disabled_without_sampling(monkeypatch):
    import asyncio

    from utils.sync import batch_census as sweep

    monkeypatch.setenv('BATCH_CENSUS_EXPORT_ENABLED', 'false')
    result = asyncio.run(sweep.snapshot(firestore_client=FakeClient(), now=1_000.0))

    assert result['status'] == sweep.OUTCOME_DISABLED
    assert result['stocks'] == 0


def test_publish_uses_a_sentinel_for_rows_without_an_ageable_clock():
    metrics.publish({'batch:result_ready': StockSample(units=5, oldest_at=None)}, now=1_000.0)

    labels = {'machine': 'batch', 'state': 'result_ready'}
    assert metrics.UNITS.labels(**labels)._value.get() == 5
    assert metrics.OLDEST_AGE.labels(**labels)._value.get() == metrics.UNDATED_OLDEST_AGE_SENTINEL
    assert metrics.OBSERVED_AT.labels(**labels)._value.get() == 1_000.0


def test_publish_zeroes_an_empty_stock_and_reports_real_age():
    metrics.publish(
        {
            'batch:ready': StockSample(units=0, oldest_at=None),
            'batch:retry': StockSample(units=2, oldest_at=400.0),
        },
        now=1_000.0,
    )

    assert metrics.OLDEST_AGE.labels(machine='batch', state='ready')._value.get() == 0.0
    assert metrics.OLDEST_AGE.labels(machine='batch', state='retry')._value.get() == 600.0


def test_publish_keeps_the_previous_observation_for_a_failed_stock():
    labels = {'machine': 'batch', 'state': 'leased'}
    metrics.publish({'batch:leased': StockSample(units=1, oldest_at=900.0)}, now=1_000.0)
    before = metrics.OBSERVED_AT.labels(**labels)._value.get()

    metrics.publish({}, failures=('batch:leased',), now=2_000.0)

    assert metrics.OBSERVED_AT.labels(**labels)._value.get() == before
    assert metrics.UNITS.labels(**labels)._value.get() == 1


def test_publish_ignores_a_key_this_build_no_longer_declares():
    assert metrics.publish({'batch:gone': StockSample(units=4, oldest_at=None)}, now=1.0) == 0


# --- audit coverage ---------------------------------------------------------


AUDIT_STOCKS = (
    'memory_outbox:pending',
    'speaker_outbox:open',
    'enrichment_outbox:pending',
    'cap_hold:held',
    'pipeline_ledger:capturing',
    'batch:committed_hidden',
    'batch:deep_backlog',
    'batch:allowance_held',
)


@pytest.mark.parametrize('key', AUDIT_STOCKS)
def test_every_stock_the_audit_named_is_registered_with_a_clock(key):
    entry = BY_KEY[key]
    if entry.machine in {'memory_outbox', 'speaker_outbox'}:
        # No immutable acceptance clock exists at the writer, and the retry/wake
        # clocks move into the future. The ruling requires the explicit undated
        # sentinel rather than an age that clamps to a healthy 0.
        assert entry.clock is None, key
        assert entry.age_alarm_seconds is None, key
        assert 'sentinel' in entry.note, key
    else:
        assert entry.clock, f'{key} has no ageable clock, so the audit finding is still blind'
        assert not entry.clock.endswith(('_deadline_at', '_until')), key
    assert entry.collection in {
        'jobs',
        'results',
        'memory_outbox',
        'enrichment_outbox',
        'speaker_outbox',
        'cap_holds',
        'pipeline_ledger',
    }


def test_retry_and_wake_clocks_are_never_published_as_an_age():
    """A retry/wake clock can move into the future; aging from it reads healthy."""
    for key, retry_clock in (
        ('memory_outbox:pending', 'available_at'),
        ('memory_outbox:processing', 'available_at'),
        ('memory_outbox:retryable_failure', 'available_at'),
        ('speaker_outbox:open', 'due_at'),
        ('speaker_outbox:terminal_pending', 'due_at'),
    ):
        entry = BY_KEY[key]
        assert entry.clock != retry_clock, key
        assert entry.clock is None, key
        assert entry.age_alarm_seconds is None, key


def test_undated_stocks_publish_a_count_and_no_oldest_read():
    client = FakeClient(counts={'memory_outbox': 4})
    entry = BY_KEY['memory_outbox:pending']

    sample = sample_entry(client, entry, now=1_000.0, timeout=1.0)

    assert sample.units == 4
    assert sample.oldest_at is None
    assert [call[0] for call in client.calls] == ['count']
    metrics.publish({entry.key: sample}, now=1_000.0)
    assert metrics.OLDEST_AGE.labels(machine='memory_outbox', state='pending')._value.get() == (
        metrics.UNDATED_OLDEST_AGE_SENTINEL
    )


def test_every_stock_costs_one_count_and_at_most_one_oldest_read():
    """The per-stock read budget: one collection, one count, <=1 clock-only read."""
    from config.batch_census import COLLECTIONS

    for entry in ENTRIES:
        names = COLLECTIONS[entry.collection]
        assert len(names) == 1, f'{entry.key} reads {names}; production census is one collection per stock'
        assert not names[0].endswith('_dev_jobs') and 'dev' not in names[0], entry.key

        client = FakeClient(counts={names[0]: 2}, oldest={names[0]: 500.0})
        sample_entry(client, entry, now=1_000.0, timeout=1.0)
        counts = [call for call in client.calls if call[0] == 'count']
        streams = [call for call in client.calls if call[0] == 'stream']
        assert len(counts) == 1, entry.key
        assert len(streams) <= 1, entry.key


def test_every_registered_collection_resolves_to_physical_names():
    from config.batch_census import COLLECTIONS

    for entry in ENTRIES:
        assert COLLECTIONS[entry.collection], entry.key
        assert all(name for name in COLLECTIONS[entry.collection])


# --- rendered alarms --------------------------------------------------------


def _rendered_rules():
    import importlib.util

    spec = importlib.util.spec_from_file_location('generate_batch_census_alerts', GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_alert_export_matches_the_registry():
    module = _rendered_rules()
    split = json.loads((MONITORING / 'alerts/batch-census.json').read_text())
    combined = json.loads((MONITORING / 'alert-rules.json').read_text())

    assert {rule['uid']: rule for rule in split} == {rule['uid']: rule for rule in module.rules()}
    by_uid = {rule['uid']: rule for rule in combined}
    for rule in split:
        assert by_uid[rule['uid']] == rule


def test_every_alarmed_stock_has_a_rule_and_no_rule_outlives_its_entry():
    module = _rendered_rules()
    expected = {module.rule_uid(entry) for entry in ENTRIES if entry.age_alarm_seconds}
    rendered = {rule['uid'] for rule in module.rules()} - {module.BLIND_UID, module.SNAPSHOT_BLIND_UID}
    assert rendered == expected


def test_alert_uids_fit_grafana_and_name_their_identity():
    module = _rendered_rules()
    for rule in module.rules():
        assert len(rule['uid']) <= 40, rule['uid']
        assert rule['labels']['alert_identity'] == rule['uid']
        assert rule['labels']['impact'] == 'product'
        assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'


def test_age_alarms_take_age_and_freshness_from_the_same_newest_source():
    """A stale replica's retained age must not borrow a newer replica's observation.

    The expression joins on the full label set (``A and B`` matches labels), then
    keeps only the source whose observation is the fleet maximum, then requires
    that source to be fresh. Bare ``max()`` of each gauge is the failure mode:
    it can pin a page on a dead replica's last reading forever.
    """
    module = _rendered_rules()
    rules = {rule['uid']: rule for rule in module.rules()}
    for entry in ENTRIES:
        if entry.age_alarm_seconds is None:
            continue
        rule = rules[module.rule_uid(entry)]
        expr = rule['data'][0]['model']['expr']
        assert 'omi_batch_pipeline_census_state_oldest_age_seconds' in expr, entry.key
        assert ' and ' in expr, entry.key
        assert '== scalar(max(' in expr, entry.key
        assert f'< {module.FRESH_SECONDS}' in expr, entry.key
        assert rule['data'][1]['model']['expression'] == f'$A > {entry.age_alarm_seconds}', entry.key


def test_alarmed_stocks_are_aged_from_an_acceptance_clock():
    """A deadline clock reads 0 for the whole legitimate wait, so a stock aged
    from one would show healthy while rows sit, and its alarm could only fire
    after the deadline had already dead-lettered them."""
    for entry in ENTRIES:
        if entry.age_alarm_seconds is None:
            continue
        assert entry.clock, entry.key
        assert not entry.clock.endswith(('_deadline_at', '_until')), entry.key


def test_deadline_clocks_stay_in_custody_not_in_the_age_reading():
    for key, deadline in (
        ('batch:record_pending', 'record_dead_letter_deadline_at'),
        ('batch:quarantined', 'held_deadline_at'),
        ('batch_projection:quarantine_held', 'held_deadline_at'),
    ):
        entry = BY_KEY[key]
        assert entry.clock != deadline, key
        assert entry.custody is not None and entry.custody.clock == deadline, key


def test_scheduler_declares_the_census_run_without_creating_it_in_code():
    import yaml

    document = yaml.safe_load(SCHEDULER.read_text())
    jobs = document['environments']['prod']['jobs']
    census = next(job for job in jobs if job['name'] == 'batch-stock-census')
    assert census['target']['uri'].endswith('/v2/batch-census/run')
    assert census['schedule'] == '*/10 * * * *'
    assert census['state'] == 'ENABLED'
    assert census['owner'] == 'backend/docs/runbooks/batch-stuck-census.md'


def test_dashboard_reads_the_census_series_and_is_not_empty():
    dashboard = json.loads((MONITORING / 'dashboards/general/batch-stuck-census.json').read_text())
    expressions = [
        target['expr'] for panel in dashboard['panels'] for target in panel.get('targets', []) if target.get('expr')
    ]
    joined = '\n'.join(expressions)
    assert 'omi_batch_pipeline_census_state_units' in joined
    assert 'omi_batch_pipeline_census_state_oldest_age_seconds' in joined
    assert 'omi_batch_pipeline_census_snapshot_timestamp_seconds' in joined
    assert len(expressions) >= 4


def test_changed_exporter_sources_select_the_export_contract():
    import runpy

    selector = runpy.run_path(str(REPO / 'backend/scripts/select_backend_unit_tests.py'))
    all_tests = selector['discover_all_tests']()
    for path in (
        'backend/database/batch_census_export.py',
        'backend/utils/observability/batch_census.py',
        'backend/utils/sync/batch_census.py',
        'backend/scripts/generate_batch_census_alerts.py',
    ):
        selected, reason = selector['tests_for_changed_paths']([path], all_tests)
        assert 'tests/unit/test_batch_census_export.py' in selected, (path, reason)


def test_census_series_survive_the_sync_scrape_and_ingestion_allowlist():
    """An alarm can only fire on a family the sync scrape keeps and Grafana imports."""
    import re

    import yaml

    from scripts.alert_backtest import metric_names, prometheus

    module = _rendered_rules()
    queried = set().union(
        *(
            metric_names(node['model'].get('expr', ''))
            for rule in module.rules()
            for node in rule['data']
            if prometheus(node)
        )
    )
    assert queried
    assert queried <= set(json.loads((MONITORING / 'metric-inventory.prod.json').read_text())['declared_metrics'])

    gmp = yaml.safe_load((REPO / 'backend/deploy/cloud_run_gmp_sync.yaml').read_text())
    keep = next(item for item in gmp['spec']['endpoints'][0]['metricRelabeling'] if item['action'] == 'keep')['regex']
    for name in queried:
        assert re.fullmatch(keep, name), f'{name} is dropped by the sync GMP keep rule'

    for exporter in ('prod_sync_omi_cloud_run_metrics_exporter.yaml', 'dev_sync_omi_cloud_run_metrics_exporter.yaml'):
        values = yaml.safe_load((MONITORING / 'prometheus-stackdriver-exporter' / exporter).read_text())
        prefixes = values['stackdriver']['metrics']['prefixes']
        assert any(
            name.startswith(prefix.removeprefix('prometheus.googleapis.com/'))
            for name in queried
            for prefix in prefixes
            if prefix.endswith('_')
        )
