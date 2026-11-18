"""Recording-outcome SLI: production count shapes, collector, pages, tiles and export path.

Failure-Class: FC-alert-never-provably-fired

2026-11-16 18:50Z: summaries for finished recordings fell from about 60% to about
10% for 21 hours with nothing paged. These contracts keep the outcome page on an
independent denominator, on a datasource that carries the family, and on the
first screen.
"""

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from prometheus_client import CollectorRegistry

from database.batch_pipeline_recording_outcome import (
    COHORT_NEWEST_SECONDS,
    COHORT_OLDEST_SECONDS,
    recording_outcome_counts,
)
from utils.batch_pipeline import recording_outcome as module
from utils.batch_pipeline.metrics import PROJECTION_DRAIN_WALK_STOPS, record_walk_stop
from utils.batch_pipeline.projection_walk_stop import STOP_CLASSES, WALK_STOPS, walk_stop_class

BACKEND = Path(__file__).resolve().parents[2]
MONITORING = BACKEND / 'charts/monitoring'
spec = importlib.util.spec_from_file_location('recording_outcome_alert_backtest', BACKEND / 'scripts/alert_backtest.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
RULES = {r['uid']: r for r in json.loads((MONITORING / 'alerts/recording-outcome.json').read_text())}
FAMILY = 'omi_batch_pipeline_recording_outcome_'
SEL = (
    'project_id="based-hardware",cluster="__run__",job="omi-cloud-run-application-metrics",'
    'namespace="backend-integration"'
)


class CountClient:
    def __init__(self, rows=(), fail_at=None):
        self.rows, self.fail_at, self.calls = rows, fail_at, []

    def collection_group(self, name):
        assert name == 'conversations'
        return CountQuery(self, ())


class CountQuery:
    def __init__(self, client, filters):
        self.client, self.filters = client, filters

    def where(self, *, filter):
        return CountQuery(self.client, self.filters + ((filter.field_path, filter.op_string, filter.value),))

    def count(self):
        return self

    def get(self, *, timeout, retry):
        assert timeout == 10 and retry is None
        self.client.calls.append(self.filters)
        if len(self.client.calls) == self.client.fail_at:
            raise RuntimeError('synthetic count failure')
        ops = {
            '==': lambda a, v: a == v,
            '>=': lambda a, v: a >= v,
            '<': lambda a, v: a < v,
            '>': lambda a, v: a > v,
        }
        matches = sum(
            all(key in row and ops[op](row[key], value) for key, op, value in self.filters) for row in self.client.rows
        )
        return [[SimpleNamespace(value=matches)]]


def _at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


NOW = 2_000_000_000.0


def _row(finished_ago, *, revision=None, summary=None, lane='batch_live_v1', status='completed'):
    row = {'record_lane_owner': lane, 'status': status, 'finished_at': _at(NOW - finished_ago)}
    if revision is not None:
        row['record_projection_revision'] = revision
    if summary is not None:
        row['summary_output_present'] = summary
    return row


def test_counts_use_one_finished_cohort_with_an_independent_denominator():
    rows = [
        _row(1000, revision=1, summary=True),
        _row(1500, revision=2, summary=False),
        # Never projected: still a finished recording, so it stays in the denominator.
        _row(2000),
        _row(COHORT_OLDEST_SECONDS, revision=1, summary=True),  # closed lower bound: included
        _row(COHORT_NEWEST_SECONDS, revision=1, summary=True),  # open upper bound: excluded
        _row(3000, revision=1, summary=True),  # finished too long ago
        _row(1200, revision=1, summary=True, lane='batch_sync_v1'),
        _row(1200, revision=1, summary=True, status='in_progress'),
    ]
    client = CountClient(rows)
    assert recording_outcome_counts(client, NOW) == (4, 3, 2)
    cohort = client.calls[0]
    assert cohort == (
        ('record_lane_owner', '==', 'batch_live_v1'),
        ('status', '==', 'completed'),
        ('finished_at', '>=', _at(NOW - 2700)),
        ('finished_at', '<', _at(NOW - 900)),
    )
    assert client.calls[1] == cohort + (('record_projection_revision', '>', 0),)
    assert client.calls[2] == cohort + (('summary_output_present', '==', True),)


def test_both_numerator_shapes_have_a_declared_composite_index():
    manifest = json.loads((BACKEND.parent / 'firestore.indexes.json').read_text())
    fields = {
        tuple(field['fieldPath'] for field in index['fields'])
        for index in manifest['indexes']
        if index['collectionGroup'] == 'conversations' and index['queryScope'] == 'COLLECTION_GROUP'
    }
    assert ('record_lane_owner', 'status', 'finished_at', '__name__') in fields
    assert ('record_lane_owner', 'status', 'summary_output_present', 'finished_at', '__name__') in fields
    assert ('record_lane_owner', 'status', 'finished_at', 'record_projection_revision', '__name__') in fields


@pytest.fixture
def sampler(monkeypatch):
    clock = [5000.0]
    monkeypatch.delenv('BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED', raising=False)
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'time', lambda: NOW)
    registry = CollectorRegistry()
    return module.RecordingOutcome(registry), registry, clock


def _samples(registry):
    return {s.name: s.value for m in registry.collect() for s in m.samples if s.name.startswith(FAMILY)}


def test_collector_publishes_the_triple_then_withdraws_it_when_stale_or_failed(sampler):
    outcome, registry, clock = sampler
    assert _samples(registry) == {}
    store = SimpleNamespace(client=CountClient([_row(1000, revision=1, summary=True), _row(1100)]))
    outcome.refresh(store)
    assert _samples(registry) == {
        FAMILY + 'finished_window_total': 2,
        FAMILY + 'transcribed_window_total': 1,
        FAMILY + 'summarized_window_total': 1,
        FAMILY + 'sample_age_seconds': 0.0,
        FAMILY + 'sample_timestamp_seconds': NOW,
    }
    clock[0] += 30
    outcome.refresh(store)  # not due: no new RPCs
    assert len(store.client.calls) == 3
    clock[0] += 30
    failing = SimpleNamespace(client=CountClient(fail_at=2))
    outcome.refresh(failing)
    # A failure never leaves an old share on the board; only the age remains.
    assert _samples(registry) == {FAMILY + 'sample_age_seconds': 60.0}
    clock[0] += 60
    outcome.refresh(store)
    assert _samples(registry)[FAMILY + 'finished_window_total'] == 2
    clock[0] += module.EXPIRY_SECONDS
    assert set(_samples(registry)) == {FAMILY + 'sample_age_seconds'}


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no'])
def test_kill_switch_stops_queries_and_hides_every_gauge(sampler, monkeypatch, value):
    outcome, registry, _ = sampler
    store = SimpleNamespace(client=CountClient([_row(1000, revision=1)]))
    outcome.refresh(store)
    assert _samples(registry)
    monkeypatch.setenv('BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED', value)
    assert _samples(registry) == {}
    outcome.refresh(store)
    assert len(store.client.calls) == 3


def test_deactivated_sampler_publishes_nothing(sampler):
    outcome, registry, _ = sampler
    outcome.refresh(SimpleNamespace(client=CountClient([_row(1000)])))
    outcome.deactivate()
    assert _samples(registry) == {}


def test_walk_stop_classes_are_closed_and_fold_the_open_blocked_family():
    assert set(STOP_CLASSES) == WALK_STOPS | {'yield', 'blocked', 'blocked_privacy', 'other'}
    assert walk_stop_class('blocked_immutable_result_binding_mismatch') == 'blocked'
    assert walk_stop_class('blocked_privacy_disposition_requires_a_source_deletion_tombstone') == 'blocked_privacy'
    assert walk_stop_class('privacy_blocked') == 'privacy_blocked'
    assert walk_stop_class('end') == 'end'
    assert walk_stop_class('yield') == 'yield'
    assert walk_stop_class('something_new') == 'other'
    assert walk_stop_class(None) == 'other'
    child = PROJECTION_DRAIN_WALK_STOPS.labels(stop='blocked', progress='advanced')
    before = child._value.get()
    record_walk_stop('blocked_some_future_refusal', 3)
    assert child._value.get() == before + 1


def test_alerted_walk_stop_children_exist_before_the_first_event():
    labels = {
        (s.labels['stop'], s.labels['progress'])
        for m in PROJECTION_DRAIN_WALK_STOPS.collect()
        for s in m.samples
        if s.name.endswith('_total')
    }
    assert {('blocked', 'none'), ('blocked_privacy', 'none')} <= labels


def test_new_families_leave_cloud_run_through_the_gmp_keep_list():
    text = (BACKEND / 'deploy/cloud_run_gmp_sync.yaml').read_text()
    keep = re.search(r"regex: '(omi_\(record_wal_handoff_.*?)'", text).group(1)
    pattern = re.compile(keep)
    for name in (
        'omi_batch_pipeline_recording_outcome_finished_window_total',
        'omi_batch_pipeline_recording_outcome_transcribed_window_total',
        'omi_batch_pipeline_recording_outcome_summarized_window_total',
        'omi_batch_pipeline_recording_outcome_sample_timestamp_seconds',
        'omi_batch_pipeline_fresh_unprojected_ratio',
        'omi_batch_projection_walk_stops_total',
        'omi_fallback_total',
    ):
        assert pattern.fullmatch(name), name


def test_split_and_combined_exports_match_and_lint_clean():
    combined = {r['uid']: r for r in json.loads((MONITORING / 'alert-rules.json').read_text())}
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    for uid, rule in RULES.items():
        assert combined[uid] == rule
        assert not b.lint_rule(rule, inventory), uid
        assert len(uid) <= 40


@pytest.mark.parametrize('uid', sorted(RULES))
def test_every_rule_pages_a_human_with_runbook_and_measured_threshold(uid):
    rule = RULES[uid]
    assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
    assert rule['labels']['alert_identity'] == uid
    assert 'mute_time_intervals' not in rule['notification_settings']
    assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'
    assert not rule['isPaused']
    assert (BACKEND.parent / rule['annotations']['runbook']).is_file()
    for key in ('summary', 'user_impact', 'scope', 'verification', 'safe_next_action', 'threshold'):
        assert rule['annotations'][key], key
    assert 'Backtest' in rule['annotations']['verification']
    for node in rule['data']:
        if node['datasourceUid'] != '__expr__':
            # The in-cluster bridge does not import these Cloud Run families.
            assert node['datasourceUid'] == 'gmp-cloud-run'
            assert 'project_id="based-hardware"' in node['model']['expr']


def test_fast_outcome_page_has_independent_denominator_volume_floor_and_alerting_nodata():
    rule = RULES['omi-recording-outcome-fast']
    expr = rule['data'][0]['model']['expr']
    assert rule['labels']['severity'] == 'critical'
    assert rule['noDataState'] == 'Alerting', 'a blind sampler must page, not read healthy'
    assert rule['for'] == '10m' and rule['keep_firing_for'] == '30m'
    finished = f'{FAMILY}finished_window_total{{{SEL}}}'
    assert f'max({FAMILY}transcribed_window_total{{{SEL}}} / ({finished} >= 50)) < bool 0.6' in expr
    assert f'max({FAMILY}summarized_window_total{{{SEL}}} / ({finished} >= 50)) < bool 0.1' in expr
    # Under the volume floor the sampler is alive and the rule must read 0, not NoData.
    assert expr.endswith(f' or on() (0 * max({finished}))')
    assert '"outcome", "transcript"' in expr and '"outcome", "summary"' in expr
    assert 'histogram_quantile' not in expr and '_seconds_bucket' not in expr


def test_slow_outcome_page_pools_six_hours_across_instances():
    rule = RULES['omi-recording-outcome-slow']
    expr = rule['data'][0]['model']['expr']
    assert rule['noDataState'] == 'OK' and rule['for'] == '30m'
    assert f'sum(sum_over_time({FAMILY}transcribed_window_total{{{SEL}}}[6h]))' in expr
    assert f'sum(count_over_time({FAMILY}finished_window_total{{{SEL}}}[6h])) >= 50)' in expr
    assert '< bool 0.7' in expr and '< bool 0.25' in expr


def test_cause_level_rules_read_fresh_scoped_and_closed_signals():
    fresh = RULES['omi-batch-fresh-unprojected-share']['data'][0]['model']['expr']
    assert 'omi_batch_pipeline_fresh_unprojected_ratio' in fresh and '> bool 0.1' in fresh
    assert 'omi_batch_pipeline_fresh_committed_window_total' in fresh and '>= bool 500' in fresh
    assert 'obligation_oldest_age' not in fresh, 'the unscoped age is pinned by the 30-day held stock'
    blocked = RULES['omi-batch-projection-heads-blocked']
    expr = blocked['data'][0]['model']['expr']
    assert 'stop="blocked",progress="none"' in expr and '[10m]' in expr
    assert blocked['data'][1]['model']['expression'] == '$A >= 50'
    skew = RULES['omi-batch-result-marker-skew']['data'][0]['model']['expr']
    assert 'component="sync_dispatch",from_mode="row_source_marker",to_mode="job_source_marker"' in skew


@pytest.mark.parametrize('uid', sorted(RULES))
def test_pending_period_and_empty_frames(uid):
    rule = RULES[uid]
    pending = int(b.seconds(rule["for"]))
    brief = [(t, {(): float(t < pending)}) for t in range(0, pending + 121, 60)]
    assert b.episodes(rule, brief, 0, pending + 120, 60)['episodes'] == 0
    # The blocked-heads count thresholds in the math node; the others compare inside PromQL.
    fires, quiet = (50.0, 49.0) if uid == 'omi-batch-projection-heads-blocked' else (1.0, 0.0)
    assert b.evaluate(rule, {'A': {(): [fires]}}) == {(): 1.0}
    assert b.evaluate(rule, {'A': {(): [quiet]}}) == {(): 0.0}


def _dashboard_panels():
    dashboard = json.loads((MONITORING / 'dashboards/general/omi-core-features.json').read_text())
    return dashboard['panels']


def test_outcome_tiles_sit_on_the_first_screen_with_trends_on_gmp():
    top = _dashboard_panels()
    order = [p['id'] for p in top]
    stuck = order.index(27)
    by_id = {p['id']: p for p in top}
    for stat_id, spark_id, numerator, steps in (
        (99, 101, 'transcribed', [None, 0, 60, 70]),
        (100, 102, 'summarized', [None, 0, 10, 25]),
    ):
        stat, spark = by_id[stat_id], by_id[spark_id]
        assert order.index(stat_id) < stuck and order.index(spark_id) < stuck
        assert 'collapsed' not in stat
        assert stat['datasource']['uid'] == spark['datasource']['uid'] == 'gmp-cloud-run'
        assert [s['value'] for s in stat['fieldConfig']['defaults']['thresholds']['steps']] == steps
        assert spark['fieldConfig']['defaults']['thresholds'] == stat['fieldConfig']['defaults']['thresholds']
        assert spark['gridPos']['x'] == stat['gridPos']['x']
        assert spark['gridPos']['y'] == stat['gridPos']['y'] + stat['gridPos']['h']
        assert f'{FAMILY}{numerator}_window_total{{{SEL}}}' in stat['targets'][0]['expr']
        assert f'{FAMILY}finished_window_total{{{SEL}}} > 0' in stat['targets'][0]['expr']
        trend = spark['targets'][0]['expr']
        assert '[$__interval]' in trend and trend.endswith(' >= 0')
        assert spark['interval'] == '5m' and spark['maxDataPoints'] == 24
        assert 'noValue' not in spark['fieldConfig']['defaults']


def test_stuck_row_shows_blocked_heads_and_fresh_unprojected_share():
    top = _dashboard_panels()
    order = [p['id'] for p in top]
    by_id = {p['id']: p for p in top}
    assert order.index(27) < order.index(103) < order.index(104) < order.index(89)
    assert 'stop="blocked",progress="none"' in by_id[103]['targets'][0]['expr']
    assert 'omi_batch_pipeline_fresh_unprojected_ratio' in by_id[104]['targets'][0]['expr']
    assert by_id[103]['datasource']['uid'] == by_id[104]['datasource']['uid'] == 'gmp-cloud-run'


def test_kill_switch_is_registered_default_on():
    with (BACKEND.parent / 'config/feature-flags.yaml').open(encoding='utf-8') as registry:
        flags = {entry['key']: entry for entry in yaml.load(registry, Loader=yaml.CSafeLoader)['flags']}
    flag = flags['BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED']
    assert flag['lifecycle'] == 'ops_kill' and flag['fail'] == 'open'
    from config.policy.kill_switches import KILL_SWITCHES

    assert KILL_SWITCHES['BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED'] is True
