"""2-hour batch timeliness alarm (David, 2026-11-02): store sample, gauges and the Grafana rule."""

import json
from pathlib import Path
from unittest.mock import Mock

from prometheus_client import CollectorRegistry

from config.batch_timeliness import TERMINAL_EMPTY_IS_PROCESSED
from database.batch_pipeline_store import TIMELINESS_HOLD_SCAN_LIMIT, timeliness_sample
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

    def __init__(self, rows, filters=(), order=None, limit=None):
        self.rows, self.filters, self.order, self._limit = rows, filters, order, limit

    def where(self, field, op, value):
        return _Query(self.rows, self.filters + ((field, op, value),), self.order, self._limit)

    def order_by(self, field):
        return _Query(self.rows, self.filters, field, self._limit)

    def limit(self, n):
        return _Query(self.rows, self.filters, self.order, n)

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
        'terminal_empty': 0,
    }
    assert sample['backlog'] == {
        'uncommitted_incl_holds': 0,
        'quarantined': 1,
        'assignment_held': 1,
        'projection': 0,
        'quarantine_held_rows': 1,
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
    assert '($A > 7200 && $B < 900) || ($C > 7200 && $F < 120)' in exprs
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
    old = EPOCH - 3 * 86400
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
    }
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = _store(monkeypatch, sample)
    metrics.refresh_timeliness(store, NOW)
    for leg, started in sample['held_oldest'].items():
        assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': leg}) == NOW - started
    # A subsequent empty stock must clear old series, rather than leave a latched age.
    sample['held_oldest'] = dict.fromkeys(sample['held_oldest'])
    metrics.refresh_timeliness(store, NOW + 301)
    for leg in sample['held_oldest']:
        assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': leg}) == 0


def test_held_oldest_does_not_depend_on_stock_size_or_first_input_row():
    old = EPOCH - 2 * 86400
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
