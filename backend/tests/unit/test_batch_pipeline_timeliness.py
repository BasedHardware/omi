"""2-hour batch timeliness alarm (David, 2026-11-02): store sample, gauges and the Grafana rule."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.unit.test_timeliness_metrics_are_scraped import FRESH_NEWEST, NEWEST

from prometheus_client import CollectorRegistry

from config.batch_timeliness import TERMINAL_EMPTY_IS_PROCESSED, timeliness_interval_seconds
from database.batch_pipeline_store import TIMELINESS_HOLD_SCAN_LIMIT, timeliness_sample
from utils.batch_pipeline.leader import TIMELINESS_LEASE_GRACE_SECONDS
from utils.batch_pipeline.metrics import QueueMetrics

BACKEND = Path(__file__).resolve().parents[2]
PENDING = BACKEND / 'charts/monitoring/alerts/batch-timeliness.json'
EPOCH = 100_000.0
NOW = EPOCH + 5 * 3600
SLA = 7200


class _Count:
    def __init__(self, value):
        self.value = value


class _Doc:
    def __init__(self, data):
        self.id = data['id']
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Ref:
    def __init__(self, rows, doc_id):
        self.rows, self.id = rows, doc_id


class _Query:
    """The slice of the Firestore query API the sample uses: where, order_by, limit, stream, count, document."""

    def __init__(self, rows, filters=(), order=None, limit=None, after=None):
        self.rows, self.filters, self.order, self._limit, self.after = rows, filters, order, limit, after

    def where(self, field, op, value):
        return _Query(self.rows, self.filters + ((field, op, value),), self.order, self._limit, self.after)

    def order_by(self, field):
        return _Query(self.rows, self.filters, field, self._limit, self.after)

    def limit(self, n):
        return _Query(self.rows, self.filters, self.order, n, self.after)

    def start_after(self, doc):
        return _Query(self.rows, self.filters, self.order, self._limit, doc.id)

    def document(self, doc_id):
        return _Ref(self.rows, doc_id)

    def _match(self, row):
        ops = {
            '==': lambda a, b: a == b,
            'in': lambda a, b: a in b,
            '>=': lambda a, b: a is not None and a >= b,
            '<': lambda a, b: a is not None and a < b,
        }

        def get(field):
            value = row
            for part in field.split('.'):
                value = value.get(part) if isinstance(value, dict) else None
            return value

        return all(ops[op](get(field), value) for field, op, value in self.filters)

    def _selected(self):
        rows = [r for r in self.rows if self._match(r)]
        if self.order:
            rows.sort(key=lambda r: r[self.order])
        if self.after is not None:
            offset = next(i for i, row in enumerate(rows) if row['id'] == self.after) + 1
            rows = rows[offset:]
        return rows[: self._limit] if self._limit is not None else rows

    def stream(self):
        return [_Doc(r) for r in self._selected()]

    def count(self):
        return Mock(get=lambda: [[_Count(len(self._selected()))]])


class _Client:
    def __init__(self, jobs=(), results=()):
        self.tables = {
            name: [{'id': f'{name}-{i}', **row} for i, row in enumerate(rows)]
            for name, rows in (('ns_jobs', jobs), ('ns_results', results))
        }

    def collection(self, name):
        return _Query(self.tables[name])

    def get_all(self, refs, field_paths=None):
        by_id = {row['id']: row for ref in refs[:1] for row in ref.rows}
        return [_Doc(by_id[ref.id]) for ref in refs if ref.id in by_id]


def _sample(jobs=(), results=(), now=NOW, terminal_empty_processed=False):
    return timeliness_sample(
        _Client(jobs, results), 'ns', EPOCH, now, SLA, terminal_empty_processed=terminal_empty_processed
    )


def test_new_units_alarm_while_backlog_before_the_epoch_is_only_counted():
    sample = _sample(
        jobs=[
            {'state': 'quarantined', 'recovery_state': 'failed_held', 'enqueued_at': EPOCH - 86400},
            {'state': 'quarantined', 'recovery_state': 'failed_held', 'enqueued_at': EPOCH + 600},
            {'state': 'quarantined', 'recovery_state': 'prepared', 'enqueued_at': NOW - 600},
            {'state': 'committed', 'enqueued_at': EPOCH + 60},
            {'state': 'committed', 'recovery_state': 'held', 'enqueued_at': EPOCH + 120},
            {'state': 'committed', 'recovery_state': 'held', 'enqueued_at': EPOCH - 120},
            {'state': 'committed', 'recovery_state': 'recovered', 'enqueued_at': EPOCH + 30},
        ],
        results=[
            {'projection_state': 'quarantine_held', 'committed_at': EPOCH - 3600},
            {'projection_state': 'quarantine_held', 'committed_at': EPOCH + 900},
            {'projection_state': 'completed', 'committed_at': EPOCH + 30},
        ],
    )
    assert sample['new_oldest']['quarantined'] == EPOCH + 600
    assert sample['new_oldest']['assignment_held'] == EPOCH + 120
    assert sample['new_over_sla'] == {
        'quarantined': 1,
        'assignment_held': 1,
        'projection': 0,
        'quarantine_held_rows': 1,
        'held_expired_rows': 0,
        'terminal_empty': 0,
    }
    assert sample['backlog'] == {
        'uncommitted_incl_holds': 0,
        'quarantined': 1,
        'assignment_held': 1,
        'projection': 0,
        'quarantine_held_rows': 1,
        'held_expired_rows': 0,
        'terminal_empty': 0,
    }
    assert sample['new_oldest']['projection'] is None
    assert sample['new_oldest']['uncommitted'] is None


def test_projection_clocks_from_admission_not_commit():
    # 1h59m to commit plus 1h59m unprojected must read as about 4h, not 1h59m.
    jobs = [
        {'id': 'slow', 'state': 'committed', 'enqueued_at': NOW - 4 * 3600},
        {'id': 'old', 'state': 'committed', 'enqueued_at': EPOCH - 60},
    ]
    results = [
        {'id': 'slow', 'projection_state': 'pending', 'committed_at': NOW - 7140},
        {'id': 'old', 'projection_state': 'ready', 'committed_at': EPOCH + 30},
    ]
    sample = _sample(jobs=jobs, results=results)
    assert sample['new_oldest']['projection'] == NOW - 4 * 3600
    assert sample['truncated']['projection'] is False


def test_policy_holds_never_fill_the_bound_and_compute_retries_are_measured():
    # Admission holds park in retry without retry_started_at; a compute failure retry carries it.
    held = {'state': 'retry', 'priority': 0, 'compute_decision': {'outcome': 'held', 'reason': 'fair_use_restricted'}}
    holds = [{**held, 'enqueued_at': EPOCH + i} for i in range(TIMELINESS_HOLD_SCAN_LIMIT * 3)]
    failing = {'state': 'retry', 'priority': 1, 'enqueued_at': EPOCH + 200, 'retry_started_at': EPOCH + 900}
    sample = _sample(jobs=holds + [failing, {'state': 'leased', 'enqueued_at': EPOCH + 300}])
    assert sample['new_oldest']['uncommitted'] == EPOCH + 200
    assert sample['truncated']['uncommitted'] is False
    assert sample['backlog']['uncommitted_incl_holds'] == 0
    # A pre-epoch unit that starts failing after the epoch stays backlog.
    late = {'state': 'retry', 'priority': 2, 'enqueued_at': EPOCH - 60, 'retry_started_at': EPOCH + 60}
    sample = _sample(jobs=[late])
    assert sample['new_oldest']['uncommitted'] is None
    assert sample['backlog']['uncommitted_incl_holds'] == 1


def test_vendor_holds_never_hide_active_work():
    vendor = {'state': 'vendor_held', 'compute_decision': {'outcome': 'held', 'reason': 'vendor'}}
    holds = [{**vendor, 'enqueued_at': EPOCH + i} for i in range(TIMELINESS_HOLD_SCAN_LIMIT * 2)]
    sample = _sample(jobs=holds + [{'state': 'result_ready', 'enqueued_at': EPOCH + 500}])
    assert sample['new_oldest']['uncommitted'] == EPOCH + 500
    # The vendor walk itself is blind past its bound, and says so.
    assert sample['truncated']['uncommitted'] is True


def _ready(at, outcome='unattempted'):
    return {
        'state': 'ready',
        'priority': 2,
        'merge_pending': True,
        'enqueued_at': at,
        'available_at': at,
        'compute_decision': {'outcome': outcome, 'reason': 'allowance_exhausted'},
    }


def test_holds_back_in_ready_never_fill_the_bound():
    holds = [_ready(EPOCH + i, 'held') for i in range(TIMELINESS_HOLD_SCAN_LIMIT * 2)]
    sample = _sample(jobs=holds + [_ready(EPOCH + 999)])
    assert sample['new_oldest']['uncommitted'] == EPOCH + 999
    assert sample['truncated']['uncommitted'] is False
    assert sample['backlog']['uncommitted_incl_holds'] == 0


def test_a_prefix_of_only_pre_epoch_retries_reports_truncation():
    late = {'state': 'retry', 'priority': 0, 'enqueued_at': EPOCH - 60}
    rows = [{**late, 'retry_started_at': EPOCH + i} for i in range(TIMELINESS_HOLD_SCAN_LIMIT)]
    rows.append({**late, 'enqueued_at': EPOCH + 5, 'retry_started_at': EPOCH + 999})
    sample = _sample(jobs=rows)
    assert sample['new_oldest']['uncommitted'] is None
    assert sample['truncated']['uncommitted'] is True


def test_a_full_page_ordered_by_another_clock_is_truncated_even_with_admitted_rows():
    # 20 recent admissions precede a 3-hour-old unit by retry time; the gauge cannot see it, so it says so.
    recent = [
        {'state': 'retry', 'priority': 0, 'enqueued_at': NOW - 600 + i, 'retry_started_at': NOW - 3000 + i}
        for i in range(TIMELINESS_HOLD_SCAN_LIMIT)
    ]
    old = {'state': 'retry', 'priority': 0, 'enqueued_at': NOW - 3 * 3600, 'retry_started_at': NOW - 60}
    sample = _sample(jobs=recent + [old])
    assert sample['new_oldest']['uncommitted'] == NOW - 600
    assert sample['truncated']['uncommitted'] is True


def _empty(at, speech=0):
    """Terminal empty_asr: recovery settled empty and failed held; ``speech`` is the measured held VAD census."""
    return {
        'state': 'quarantined',
        'recovery_state': 'failed_held',
        'recovery': {'failure': {'stage': 'response_validation', 'reason': 'empty_asr'}},
        'measured_held_vad_speech_seconds': speech,
        'enqueued_at': at,
    }


def test_switched_off_terminal_empty_counts_as_unprocessed_and_stays_visible():
    sample = _sample(jobs=[_empty(EPOCH + 60), _empty(EPOCH - 60)], terminal_empty_processed=False)
    assert sample['new_oldest']['quarantined'] == EPOCH + 60
    assert sample['new_over_sla']['quarantined'] == 1
    assert sample['new_over_sla']['terminal_empty'] == 1
    assert sample['backlog']['terminal_empty'] == 1


def test_switched_on_terminal_empty_without_speech_is_processed_but_measured_speech_still_alarms():
    # David, 2026-11-02: "finished recording counts as processed".
    assert TERMINAL_EMPTY_IS_PROCESSED is True
    jobs = [_empty(EPOCH + 60), _empty(EPOCH + 90, speech=1.2), _empty(NOW - 600)]
    sample = _sample(jobs=jobs, terminal_empty_processed=True)
    assert sample['new_oldest']['quarantined'] == EPOCH + 90
    assert sample['new_over_sla']['quarantined'] == 1
    assert sample['new_over_sla']['terminal_empty'] == 1
    only_empty = _sample(jobs=[_empty(EPOCH + 60)], terminal_empty_processed=True)
    assert only_empty['new_oldest']['quarantined'] is None
    assert only_empty['new_over_sla']['quarantined'] == 0


def test_switched_on_a_page_of_terminal_empties_never_hides_a_breach():
    empties = [_empty(EPOCH + i) for i in range(TIMELINESS_HOLD_SCAN_LIMIT * 2)]
    late = {'state': 'quarantined', 'recovery_state': 'prepared', 'enqueued_at': EPOCH + 3600}
    sample = _sample(jobs=empties + [late], terminal_empty_processed=True)
    assert sample['new_over_sla']['quarantined'] == 1
    assert NOW - sample['new_oldest']['quarantined'] > SLA
    # Counts are exact, so a page of exempt rows is not blindness.
    assert sample['truncated']['uncommitted'] is False
    quiet = _sample(jobs=empties + [{**late, 'enqueued_at': NOW - 600}], terminal_empty_processed=True)
    assert quiet['new_over_sla']['quarantined'] == 0
    assert quiet['new_oldest']['quarantined'] is None


def test_no_new_unit_can_breach_before_two_hours_after_the_epoch():
    sample = _sample(jobs=[{'state': 'quarantined', 'enqueued_at': EPOCH + 10}], now=EPOCH + SLA - 1)
    assert set(sample['new_over_sla'].values()) == {0}


def _store(monkeypatch, sample):
    """The sampler the metrics module calls, patched; the store only carries client and namespace."""
    sampler = Mock(return_value=sample)
    monkeypatch.setattr('utils.batch_pipeline.metrics.timeliness_sample', sampler)
    store = Mock(namespace='ns')
    store.timeliness = sampler
    return store


SAMPLE = {
    'drain_oldest': None,
    'held_oldest': {'quarantine_held': NOW - 200_000, 'assignment_held': NOW - 100_000, 'record_pending': None},
    'new_oldest': {
        'uncommitted': None,
        'quarantined': NOW - 9000,
        'projection': NOW - 60,
        'assignment_held': None,
        'quarantine_held_rows': None,
    },
    'new_over_sla': {'quarantined': 1, 'projection': 0, 'assignment_held': 0, 'quarantine_held_rows': 0},
    'backlog': {
        'uncommitted_incl_holds': 370,
        'quarantined': 596,
        'projection': 7,
        'assignment_held': 5434,
        'quarantine_held_rows': 16921,
    },
    'truncated': {'uncommitted': True, 'projection': False},
}


def test_gauges_counter_and_cadence(monkeypatch):
    monkeypatch.delenv('BATCH_TIMELINESS_ALARM_ENABLED', raising=False)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = _store(monkeypatch, SAMPLE)
    metrics.refresh_timeliness(store, NOW)
    value = registry.get_sample_value
    assert value('omi_batch_timeliness_new_oldest_age_seconds', {'leg': 'quarantined'}) == 9000
    assert value('omi_batch_timeliness_new_oldest_age_seconds', {'leg': 'uncommitted'}) == 0
    assert value('omi_batch_timeliness_new_over_sla_units', {'leg': 'quarantined'}) == 1
    assert value('omi_batch_timeliness_backlog_units', {'leg': 'assignment_held'}) == 5434
    assert value('omi_batch_timeliness_scan_truncated', {'leg': 'uncommitted'}) == 1
    assert value('omi_batch_timeliness_scan_truncated', {'leg': 'projection'}) == 0
    assert value('omi_batch_timeliness_observed_at_seconds') == NOW
    assert value('omi_batch_timeliness_samples_total', {'outcome': 'ok'}) == 1
    metrics.refresh_timeliness(store, NOW + 60)
    assert store.timeliness.call_count == 1
    metrics.refresh_timeliness(store, NOW + 301)
    assert store.timeliness.call_count == 2


def test_failed_sample_keeps_values_and_freshness(monkeypatch):
    monkeypatch.delenv('BATCH_TIMELINESS_ALARM_ENABLED', raising=False)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = _store(monkeypatch, SAMPLE)
    metrics.refresh_timeliness(store, NOW)
    store.timeliness.side_effect = RuntimeError('unavailable')
    metrics.refresh_timeliness(store, NOW + 600)
    assert registry.get_sample_value('omi_batch_timeliness_observed_at_seconds') == NOW
    assert registry.get_sample_value('omi_batch_timeliness_new_over_sla_units', {'leg': 'quarantined'}) == 1
    assert registry.get_sample_value('omi_batch_timeliness_samples_total', {'outcome': 'error'}) == 1
    assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': 'quarantine_held'}) == 200_000


def test_kill_switch_skips_firestore_and_counts_disabled(monkeypatch):
    monkeypatch.setenv('BATCH_TIMELINESS_ALARM_ENABLED', 'false')
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = _store(monkeypatch, SAMPLE)
    metrics.refresh_timeliness(store, NOW)
    store.timeliness.assert_not_called()
    assert registry.get_sample_value('omi_batch_timeliness_samples_total', {'outcome': 'disabled'}) == 1
    assert not registry.get_sample_value('omi_batch_timeliness_observed_at_seconds')


def test_rules_page_on_new_delivery_breach_and_keep_diagnostics_agent_tier():
    rules = {rule['uid']: rule for rule in json.loads(PENDING.read_text(encoding='utf-8'))}
    alarm = rules['omi-batch-unit-unpublished-2h']
    exprs = [q['model'].get('expr') or q['model'].get('expression') for q in alarm['data']]
    assert 'leg=~"uncommitted|quarantined|assignment_held|projection"' in exprs[0]
    assert 'quarantine_held_rows' not in exprs[0] and 'backlog' not in ' '.join(exprs)
    assert '($A > 7200 && $B < 1200) || ($C > 7200 && $F < 120)' in exprs
    assert rules['omi-batch-timeliness-sample-stale']['noDataState'] == 'Alerting'
    blind = rules['omi-batch-timeliness-scan-blind']
    assert 'omi_batch_timeliness_scan_truncated' in blind['data'][0]['model']['expr']
    assert blind['for'] == '30m'
    gate = json.loads((BACKEND / 'charts/monitoring/live-alert-gate.json').read_text())
    for uid, rule in rules.items():
        assert uid in gate['uids']
        if uid == 'omi-batch-unit-unpublished-2h':
            assert rule['labels']['tier'] == 'page'
            assert rule['labels']['audience'] == 'human'
            assert not rule['notification_settings']['mute_time_intervals']
        else:
            assert rule['labels']['tier'] == 'agent'
            assert rule['notification_settings']['mute_time_intervals'] == ['omi-tier-silent']


def test_held_stock_age_has_no_epoch_or_24h_cohort_cutoff(monkeypatch):
    # The oldest row is before the timeliness epoch and far older than the lifecycle 24h cohort.
    old = EPOCH - 86400
    sample = _sample(
        jobs=[
            {'state': 'record_pending', 'enqueued_at': old},
            {'state': 'record_pending', 'enqueued_at': NOW - 60},
            {'state': 'committed', 'recovery_state': 'held', 'enqueued_at': old + 10},
            {'state': 'committed', 'recovery_state': 'recovered', 'enqueued_at': old - 10},
        ],
        results=[
            {'projection_state': 'quarantine_held', 'committed_at': old + 20},
            {'projection_state': 'completed', 'committed_at': old - 20},
        ],
    )
    assert sample['held_oldest'] == {
        'record_pending': old,
        'assignment_held': old + 10,
        'quarantine_held': old + 20,
        'held_expired': None,
        'staged_input': None,
    }
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = _store(monkeypatch, sample)
    metrics.refresh_timeliness(store, NOW)
    for leg, started in sample['held_oldest'].items():
        assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': leg}) == (
            NOW - started if started is not None else 0
        )
    # A subsequent empty stock must clear old series, rather than leave a latched age.
    sample['held_oldest'] = dict.fromkeys(sample['held_oldest'])
    metrics.refresh_timeliness(store, NOW + 301)
    for leg in sample['held_oldest']:
        assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': leg}) == 0


def test_held_oldest_does_not_depend_on_stock_size_or_first_input_row():
    old = EPOCH - 86400
    sample = _sample(
        jobs=[
            *({'state': 'record_pending', 'enqueued_at': NOW - i} for i in range(1200)),
            {'state': 'record_pending', 'enqueued_at': old},
        ]
    )
    assert sample['held_oldest']['record_pending'] == old
    assert sample['held_oldest']['assignment_held'] is None
    assert sample['held_oldest']['quarantine_held'] is None


def test_drain_age_excludes_held_only_stock_but_includes_pre_epoch_pending(monkeypatch):
    held = {'projection_state': 'quarantine_held', 'committed_at': EPOCH - 86400}
    assert _sample(results=[held])['drain_oldest'] is None
    sample = _sample(results=[held, {'projection_state': 'pending', 'committed_at': EPOCH - 3600}])
    assert sample['drain_oldest'] == EPOCH - 3600
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = _store(monkeypatch, sample)
    metrics.refresh_timeliness(store, NOW)
    assert registry.get_sample_value('omi_batch_projection_drain_oldest_age_seconds') == NOW - EPOCH + 3600
    sample['drain_oldest'] = None
    metrics.refresh_timeliness(store, NOW + 301)
    assert registry.get_sample_value('omi_batch_projection_drain_oldest_age_seconds') == 0


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize(
    'row,leg',
    [({'state': 'quarantined'}, 'quarantined'), ({'state': 'committed', 'recovery_state': 'held'}, 'assignment_held')],
)
def test_historical_counts_apply_limit_before_aggregation(monkeypatch, enabled, row, leg):
    from database.batch_pipeline_store import TIMELINESS_BACKLOG_COUNT_LIMIT

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'batch_timeliness_leader': 100 if enabled else 0}))
    queries = []
    original = _Query.count

    def counted(query):
        queries.append(query)
        return original(query)

    monkeypatch.setattr(_Query, 'count', counted)
    stock = TIMELINESS_BACKLOG_COUNT_LIMIT + 123
    # Real held stock has a staged input; keep this count-budget fixture out of
    # the separate incomplete/malformed staged-input age scan guard.
    sample = _sample(
        jobs=[
            {**row, 'enqueued_at': EPOCH - 1, 'audio_uri': 'gs://based-hardware-batch-pipeline-staging/synthetic/audio'}
        ]
        * stock
    )
    historical = [q for q in queries if any(op == '<' and value == EPOCH for _, op, value in q.filters)]
    assert len(historical) == 7
    assert all(q._limit == (TIMELINESS_BACKLOG_COUNT_LIMIT if enabled else None) for q in historical)
    assert sample['backlog'][leg] == (TIMELINESS_BACKLOG_COUNT_LIMIT if enabled else stock)
    if leg == 'assignment_held':
        rules = json.loads((BACKEND / 'charts/monitoring/alerts/critical-failures.json').read_text())
        alarm = next(rule for rule in rules if rule['uid'] == 'omi-batch-held-backlog-growing')
        stock_metric = (
            'max(omi_batch_timeliness_backlog_units{leg="assignment_held"} ' f'and ignoring(leg) {FRESH_NEWEST})'
        )
        assert f'({stock_metric} >= {TIMELINESS_BACKLOG_COUNT_LIMIT})' in alarm['data'][0]['model']['expr']
    # Post-epoch counts remain exact and unbounded.
    assert all(q._limit is None for q in queries if q not in historical)


@pytest.mark.parametrize(
    'configured,expected',
    [
        (None, 300),
        ('', 300),
        ('invalid', 300),
        ('nan', 300),
        ('0', 60),
        ('59', 60),
        ('60', 60),
        ('300', 300),
        ('600', 600),
        ('601', 600),
        ('3600', 600),
    ],
)
def test_timeliness_interval_clamps_to_preserve_freshness_through_pending(monkeypatch, configured, expected):
    monkeypatch.delenv('BATCH_TIMELINESS_INTERVAL_SECONDS', raising=False)
    if configured is not None:
        monkeypatch.setenv('BATCH_TIMELINESS_INTERVAL_SECONDS', configured)
    assert timeliness_interval_seconds() == expected


def _fleet(monkeypatch, interval=300):
    from tests.unit.test_batch_pipeline_leader import Clock
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.leader import LeaderLease, TIMELINESS_METRICS

    monkeypatch.delenv('BATCH_PIPELINE_LEADER_LEASE_ENABLED', raising=False)
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    monkeypatch.setenv('BATCH_TIMELINESS_INTERVAL_SECONDS', str(interval))
    clock, lease_store = Clock(NOW), MemoryStore()
    effective_interval = timeliness_interval_seconds()
    metrics = [
        QueueMetrics(
            CollectorRegistry(),
            timeliness_leader=LeaderLease(lease_store, TIMELINESS_METRICS, ttl_seconds=effective_interval, clock=clock),
        )
        for _ in range(2)
    ]
    store = _store(monkeypatch, SAMPLE)
    return metrics, store, clock


@pytest.mark.parametrize('configured,interval', [(60, 60), (300, 300), (600, 600), (3600, 600)])
def test_fleet_sample_follower_zero_queries_and_handover(monkeypatch, configured, interval):
    metrics, store, clock = _fleet(monkeypatch, configured)
    assert timeliness_interval_seconds() == interval
    first, second = metrics
    for m in metrics:
        assert list(m.timeliness_observed_at.collect()) == []
        assert list(m.drain_age.collect()) == []
    first.refresh_timeliness(store, clock.now)
    second.refresh_timeliness(store, clock.now + 1)
    assert store.timeliness.call_count == 1
    assert list(second.timeliness_age.collect()) == []
    assert list(second.timeliness_observed_at.collect()) == []
    # Restarted replicas cannot create an extra sample inside the fleet interval.
    from utils.batch_pipeline.leader import LeaderLease, TIMELINESS_METRICS

    restart = QueueMetrics(
        CollectorRegistry(),
        timeliness_leader=LeaderLease(
            first.timeliness_leader.store, TIMELINESS_METRICS, ttl_seconds=interval, clock=clock
        ),
    )
    clock.now += interval - 1
    restart.refresh_timeliness(store, clock.now)
    assert store.timeliness.call_count == 1
    clock.now += 63  # The bounded refresh grace has also expired.
    second.refresh_timeliness(store, clock.now)
    first.refresh_timeliness(store, clock.now)
    assert store.timeliness.call_count == 2
    assert list(first.timeliness_age.collect()) == []
    assert list(first.timeliness_observed_at.collect()) == []
    assert list(first.held_age.collect()) == []
    assert list(first.drain_age.collect()) == []
    assert list(second.timeliness_observed_at.collect())[0].samples[0].value == clock.now


@pytest.mark.parametrize('configured,interval', [(60, 60), (300, 300), (600, 600), (3600, 600)])
def test_follower_retries_after_refresh_grace_without_another_full_interval(monkeypatch, configured, interval):
    from utils.batch_pipeline import metrics as metrics_module
    from utils.batch_pipeline.leader import TIMELINESS_LEASE_GRACE_SECONDS

    metrics, store, clock = _fleet(monkeypatch, configured)
    assert timeliness_interval_seconds() == interval
    monkeypatch.setattr(metrics_module.time, 'monotonic', clock)
    first, follower = metrics
    follower.timeliness_leader.acquire = Mock(wraps=follower.timeliness_leader.acquire)
    first.refresh_timeliness(store, clock.now)
    clock.now = NOW + 1
    follower.refresh_timeliness(store, clock.now)
    assert list(first.timeliness_observed_at.collect())[0].samples[0].value == NOW
    assert list(follower.timeliness_observed_at.collect()) == []

    # The incumbent stops. This follower loses around the normal sample tick,
    # when the old lease is still live for its fixed refresh grace.
    clock.now = NOW + interval + 1
    follower.refresh_timeliness(store, clock.now)
    assert follower.timeliness_leader.acquire.call_count == 2
    assert store.timeliness.call_count == 1
    assert list(first.timeliness_age.collect())
    assert list(follower.timeliness_age.collect()) == []

    takeover = clock.now + TIMELINESS_LEASE_GRACE_SECONDS
    while clock.now < takeover - 1:
        clock.now += 1
        follower.refresh_timeliness(store, clock.now)
    # Even a fast supervisor cannot poll the lease more than once per minute.
    assert follower.timeliness_leader.acquire.call_count == 2
    assert store.timeliness.call_count == 1
    assert list(first.timeliness_observed_at.collect()) == []
    assert list(follower.timeliness_observed_at.collect()) == []

    clock.now = takeover
    follower.refresh_timeliness(store, clock.now)
    assert follower.timeliness_leader.acquire.call_count == 3
    assert store.timeliness.call_count == 2
    assert list(follower.timeliness_observed_at.collect())[0].samples[0].value == takeover
    assert list(first.timeliness_age.collect()) == []
    # Taking over restores the full successful sampling cadence, not the
    # follower retry cadence. The old leader's values remain absent throughout.
    clock.now = takeover + interval - 1
    follower.refresh_timeliness(store, clock.now)
    assert follower.timeliness_leader.acquire.call_count == 3
    assert store.timeliness.call_count == 2
    assert list(follower.timeliness_age.collect())
    clock.now += 1
    follower.refresh_timeliness(store, clock.now)
    assert store.timeliness.call_count == 3
    assert list(follower.timeliness_observed_at.collect())[0].samples[0].value == clock.now
    assert list(first.timeliness_observed_at.collect()) == []


def test_lever_zero_restores_per_instance_sampling_without_lease_reads(monkeypatch):
    metrics, store, clock = _fleet(monkeypatch)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_timeliness_leader":0}')
    for m in metrics:
        m.timeliness_leader.acquire = Mock(side_effect=AssertionError('must bypass lease'))
        m.refresh_timeliness(store, clock.now)
    assert store.timeliness.call_count == 2


def test_lease_outage_fails_open_and_samples(monkeypatch):
    metrics, store, clock = _fleet(monkeypatch)
    for m in metrics:
        m.timeliness_leader.store = Mock(run=Mock(side_effect=RuntimeError('down')))
        m.refresh_timeliness(store, clock.now)
    assert store.timeliness.call_count == 2


def test_alerts_aggregate_available_leader_and_keep_missing_sample_freshness():
    rules = {rule['uid']: rule for rule in json.loads(PENDING.read_text())}
    stale = rules['omi-batch-timeliness-sample-stale']
    assert stale['noDataState'] == 'Alerting'
    expression = stale['data'][0]['model']['expr']
    assert f'max({NEWEST})' in expression
    assert 'or vector(1e9)' in expression
    assert any(q['model'].get('expression') == '$A >= 1200' for q in stale['data'])
    assert rules['omi-batch-timeliness-scan-blind']['noDataState'] == 'OK'


@pytest.mark.parametrize('configured,interval', [(60, 60), (300, 300), (600, 600), (3600, 600)])
@pytest.mark.parametrize('mode', ['elected', 'lever_zero', 'rollback'])
def test_stalled_replica_expires_at_collection_without_refresh(monkeypatch, configured, interval, mode):
    from utils.batch_pipeline import metrics as metrics_module

    metrics, store, clock = _fleet(monkeypatch, configured)
    assert timeliness_interval_seconds() == interval
    monkeypatch.setattr(metrics_module.time, 'monotonic', clock)
    first, second = metrics
    if mode == 'lever_zero':
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_timeliness_leader":0}')
        for sampler in metrics:
            sampler.timeliness_leader.acquire = Mock(side_effect=AssertionError('must bypass lease'))
    first.refresh_timeliness(store, clock.now)
    assert list(first.timeliness_age.collect())
    if mode == 'rollback':
        # The old replica never refreshes after the lever changes. Collection
        # must still enforce the deadline set by its elected sample.
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_timeliness_leader":0}')
        second.timeliness_leader.acquire = Mock(side_effect=AssertionError('must bypass lease'))
    clock.now += interval + TIMELINESS_LEASE_GRACE_SECONDS - 1
    assert list(first.timeliness_age.collect())
    clock.now += 1  # Expiry is exclusive, even with election off.
    second.refresh_timeliness(store, clock.now)
    # A's supervisor never resumes: scraping alone must withdraw stale debt
    # before max(age from A) can borrow max(timestamp from B)'s freshness.
    for gauge in (
        first.timeliness_age,
        first.timeliness_over_sla,
        first.timeliness_backlog,
        first.timeliness_truncated,
        first.timeliness_observed_at,
        first.drain_age,
        first.held_age,
    ):
        assert list(gauge.collect()) == []
    assert list(second.timeliness_observed_at.collect())[0].samples[0].value == clock.now
    assert store.timeliness.call_count == 2


def test_lazy_election_uses_store_namespace_and_own_role_on_both_planes(monkeypatch):
    from utils.batch_pipeline import metrics as metrics_module
    from utils.batch_pipeline.leader import TIMELINESS_METRICS

    factory = Mock(return_value=Mock(acquire=Mock(return_value=False)))
    monkeypatch.setattr(metrics_module, 'LeaderLease', factory)
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    store = _store(monkeypatch, SAMPLE)
    for scope in ('serving', 'worker'):
        sampler = QueueMetrics(CollectorRegistry(), namespace=scope)
        sampler.refresh_timeliness(store, NOW)
    assert factory.call_count == 2
    for call in factory.call_args_list:
        assert call.args == (store, TIMELINESS_METRICS)
        assert call.kwargs == {'ttl_seconds': 360.0}
    store.timeliness.assert_not_called()


@pytest.mark.parametrize('configured,interval', [(60, 60), (300, 300), (600, 600), (3600, 600)])
@pytest.mark.parametrize('mode', ['elected', 'lever_zero', 'rollback'])
def test_failed_retry_does_not_revive_expired_replica(monkeypatch, configured, interval, mode):
    from utils.batch_pipeline import metrics as metrics_module

    metrics, store, clock = _fleet(monkeypatch, configured)
    assert timeliness_interval_seconds() == interval
    monkeypatch.setattr(metrics_module.time, 'monotonic', clock)
    first, second = metrics
    if mode == 'lever_zero':
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_timeliness_leader":0}')
    first.refresh_timeliness(store, clock.now)
    if mode == 'rollback':
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_timeliness_leader":0}')
    clock.now += interval + TIMELINESS_LEASE_GRACE_SECONDS + 1
    second.refresh_timeliness(store, clock.now)
    assert list(first.timeliness_age.collect()) == []
    first.timeliness_leader.store = Mock(run=Mock(side_effect=RuntimeError('lease store down')))
    store.timeliness.side_effect = RuntimeError('sample failed')
    first.refresh_timeliness(store, clock.now)
    # Preserve the last stored timestamp without extending its visibility.
    assert first.timeliness_observed_at._value.get() == NOW
    assert list(first.timeliness_age.collect()) == []
    assert list(first.timeliness_observed_at.collect()) == []
    assert list(second.timeliness_observed_at.collect())[0].samples[0].value == clock.now
    assert store.timeliness.call_count == 3  # Fail-open still attempts the sample.


@pytest.mark.parametrize('configured', [60, 300, 600, 3600])
def test_refresh_jitter_and_rpc_time_do_not_break_continuous_breach_visibility(monkeypatch, configured):
    from utils.batch_pipeline import metrics as metrics_module

    metrics, store, clock = _fleet(monkeypatch, configured)
    monkeypatch.setattr(metrics_module.time, 'monotonic', clock)
    first = metrics[0]
    first.refresh_timeliness(store, clock.now)

    def slow_sample(*args, **kwargs):
        # The sampler is on a supervised 15s tick and its RPCs also take time.
        assert list(first.timeliness_age.collect())
        clock.now += 10
        assert list(first.timeliness_age.collect())
        return SAMPLE

    store.timeliness.side_effect = slow_sample
    for _ in range(3):
        clock.now = first._timeliness_due + 15
        assert list(first.timeliness_age.collect())
        first.refresh_timeliness(store, clock.now)
        assert list(first.timeliness_age.collect())
    assert store.timeliness.call_count == 4


@pytest.mark.parametrize('bad_clock', [0, -1, float('nan'), float('-inf'), float('inf')])
@pytest.mark.parametrize('leg', ['record_pending', 'assignment_held', 'quarantine_held', 'held_expired'])
def test_held_oldest_skips_invalid_clocks_without_mutating_rows(leg, bad_clock):
    is_result = leg in ('quarantine_held', 'held_expired')
    field = 'committed_at' if is_result else 'enqueued_at'
    row = (
        {'projection_state': 'quarantine_held', 'held_expired_reason': 'held_expired'}
        if is_result
        else (
            {'state': 'record_pending'} if leg == 'record_pending' else {'state': 'committed', 'recovery_state': 'held'}
        )
    )
    old = EPOCH - 86400
    rows = [{**row, field: bad_clock}, {**row, field: old}, {**row, field: NOW - 60}]
    client = _Client(results=rows) if is_result else _Client(jobs=rows)
    before = {name: [dict(row) for row in table] for name, table in client.tables.items()}
    sample = timeliness_sample(client, 'ns', EPOCH, NOW, SLA)
    assert sample['held_oldest'][leg] == old
    assert client.tables == before
    # An all-invalid stock has no usable clock; it must not publish an epoch-scale age.
    invalid = _Client(results=rows[:1]) if is_result else _Client(jobs=rows[:1])
    assert timeliness_sample(invalid, 'ns', EPOCH, NOW, SLA)['held_oldest'][leg] is None


def test_held_oldest_keeps_walking_past_a_page_of_epoch_clocks():
    sample = _sample(
        jobs=[
            *({'state': 'record_pending', 'enqueued_at': 0} for _ in range(TIMELINESS_HOLD_SCAN_LIMIT + 1)),
            {'state': 'record_pending', 'enqueued_at': EPOCH - 86400},
        ]
    )
    assert sample['held_oldest']['record_pending'] == EPOCH - 86400


@pytest.mark.parametrize('bad_clock', [None, 'undated', True, False])
def test_held_oldest_rejects_nonnumeric_or_boolean_record_pending_clocks(bad_clock):
    assert (
        _sample(jobs=[{'state': 'record_pending', 'enqueued_at': bad_clock}])['held_oldest']['record_pending'] is None
    )
