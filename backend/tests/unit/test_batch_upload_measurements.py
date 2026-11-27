"""First creation and original-clock observations, independent of metric scraping."""

from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import re
import subprocess
import sys

import pytest
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
import yaml

from database import batch_pipeline_upload_metrics as upload_metrics
from config.request_clock import HOLD_STATES
from diarizer import batch_pipeline_runtime as runtime
from diarizer.batch_pipeline_runtime import merge_metrics
from utils.batch_pipeline import upload_entitlement
from utils.metrics import metrics_response
from utils.observability import sync_upload
from utils.sync import legacy_dark
from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder
from tests.unit.test_batch_pipeline_intake import proposal, submit, cohort  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_capture_time_skew import _default_skew, _filename, client  # noqa: F401

MISMATCH_METRIC = 'omi_batch_pipeline_upload_recovery_label_mismatch_total'
COMPARISONS_METRIC = 'omi_batch_pipeline_upload_recovery_label_comparisons_total'
DIRECTIONS = ('fresh_labelled_recovered', 'recovered_labelled_fresh', 'missing')
JOURNAL_STATES = ('fresh', 'recovered', 'mixed')


@pytest.mark.parametrize(
    'plan,status,expected',
    [
        ('basic', 'active', 'free'),
        ('plus', 'active', 'paid'),
        ('plus', 'trialing', 'trial'),
        ('alien', 'active', 'unknown'),
    ],
)
def test_effective_allowance_plan_without_usage_reads(monkeypatch, plan, status, expected):
    sub = SimpleNamespace(plan=plan, status=status)
    users = SimpleNamespace(get_user_valid_subscription=Mock(return_value=sub))
    policy = SimpleNamespace(
        is_marketplace_reviewer=lambda _: False,
        RELEASE_PROBE_UID='probe',
        is_paid_plan=lambda p: p == 'plus',
        transcription_allowance_seconds=lambda _: 1200,
    )
    monkeypatch.setattr(upload_entitlement, 'subscription_policy', lambda: (users, policy))
    assert upload_entitlement.classify('synthetic') == expected
    users.get_user_valid_subscription.assert_called_once_with('synthetic', provision=False)


def test_entitlement_failure_stays_unknown(monkeypatch):
    monkeypatch.setattr(upload_entitlement, 'subscription_policy', Mock(side_effect=RuntimeError('unavailable')))
    assert upload_entitlement.classify('synthetic') == 'unknown'


def test_created_unit_count_is_not_a_reack_or_transaction_attempt(cohort, monkeypatch):
    created = Mock()
    monkeypatch.setattr(upload_metrics, 'CREATED', created)
    s = MemoryStore()
    submit(s, *proposal())
    submit(s, *proposal('bp_replay', 'replay'))
    created.labels.assert_called_once_with('unknown')
    created.labels.return_value.inc.assert_called_once_with(1)


@pytest.mark.parametrize('clock', [None, float('nan'), float('inf'), True, -1])
def test_invalid_clocks_never_create_latency_observations(monkeypatch, clock):
    delivered = Mock()
    monkeypatch.setattr(upload_metrics, 'DELIVERED', delivered)
    upload_metrics.observe_delivery({'upload_arrived_at': clock}, 100)
    delivered.labels.assert_not_called()


@pytest.mark.parametrize(
    'state,expected',
    [
        ('none', 'none'),
        ('bg300', 'bg300'),
        ('fg_preview300', 'fg_preview300'),
        ('fg60', 'fg60'),
        ('unknown', 'unknown'),
        (None, 'unknown'),
        ('synthetic-private-user', 'unknown'),
    ],
)
def test_upload_latency_labels_are_closed(monkeypatch, state, expected):
    assert HOLD_STATES == {'none', 'bg300', 'fg_preview300', 'fg60', 'unknown'}
    delivered = Mock()
    monkeypatch.setattr(upload_metrics, 'DELIVERED', delivered)
    upload_metrics.observe_delivery(
        {'upload_arrived_at': 10, 'upload_entitlement': 'free', 'upload_hold_state': state}, 370
    )
    delivered.labels.assert_called_once_with('free', expected, 'false')
    delivered.labels.return_value.observe.assert_called_once_with(360)
    assert upload_metrics.bounded_class('synthetic-private-user') == 'unknown'


@pytest.mark.parametrize(
    'age_ms,state,expected_label,seconds',
    [('0', 'fg60', 'fg60', 0), ('360123', 'bg300', 'bg300', 360.123), ('86400000', 'invalid', 'unknown', 86400)],
)
@pytest.mark.parametrize('recovered,label', [(True, 'true'), (False, 'false'), ('private', 'false')])
def test_hold_age_observes_bounded_milliseconds(monkeypatch, age_ms, state, expected_label, seconds, recovered, label):
    histogram = Mock()
    monkeypatch.setattr(sync_upload, 'HOLD_AGE', histogram)
    sync_upload.observe_hold_age(age_ms, state, recovered)
    histogram.labels.assert_called_once_with(expected_label, label)
    histogram.labels.return_value.observe.assert_called_once_with(seconds)


@pytest.mark.parametrize('age_ms', [None, '', '1.5', ' 10', '-1', '+1', '١', '86400001', '1' * 100, 1000])
def test_malformed_hold_age_is_not_observed(monkeypatch, age_ms):
    histogram = Mock()
    monkeypatch.setattr(sync_upload, 'HOLD_AGE', histogram)
    sync_upload.observe_hold_age(age_ms, 'bg300')
    histogram.labels.assert_not_called()


def test_hold_age_is_exported_from_sync_with_guard_buckets():
    sync_upload.observe_hold_age('60000', 'fg60', True)
    samples = metrics_response().body
    for boundary in ('60.0', '300.0', '360.0', '600.0', '900.0', '1800.0'):
        assert (
            f'omi_batch_pipeline_upload_hold_age_seconds_bucket{{hold_state="fg60",le="{boundary}",recovered="true"}}'.encode()
            in samples
        )


def test_recovery_comparison_is_exported_while_idle():
    page = subprocess.check_output(
        [
            sys.executable,
            '-c',
            'from routers import sync; from utils.metrics import metrics_response; print(metrics_response().body.decode())',
        ],
        text=True,
    )
    for direction in DIRECTIONS:
        assert f'{MISMATCH_METRIC}{{direction="{direction}"}} 0.0\n' in page
    for state in JOURNAL_STATES:
        assert f'{COMPARISONS_METRIC}{{journal_state="{state}"}} 0.0\n' in page


@pytest.mark.parametrize(
    'journal,label,hold,comparison,mismatch',
    [
        ('fresh', '1', 'bg300', 1, 'fresh_labelled_recovered'),
        ('recovered', '0', 'fg60', 1, 'recovered_labelled_fresh'),
        ('fresh', '0', 'fg_preview300', 1, None),
        ('recovered', '1', 'bg300', 1, None),
        ('recovered', None, 'bg300', 1, 'missing'),
        ('fresh', None, 'none', 1, 'missing'),
        ('recovered', 'private', 'fg60', 1, 'missing'),
        (None, '1', 'bg300', 0, 'missing'),
        ('private', '1', 'bg300', 0, 'missing'),
        ('mixed', '0', 'bg300', 1, 'recovered_labelled_fresh'),
        ('mixed', '1', 'bg300', 1, 'fresh_labelled_recovered'),
        (None, None, None, 0, None),
        (None, None, 'none', 0, None),
        (None, '1', 'none', 0, None),
    ],
)
def test_v2_upload_compares_recovery_labels_without_firestore(
    client, monkeypatch, journal, label, hold, comparison, mismatch
):
    headers = {
        name: value
        for name, value in (
            ('X-Omi-Upload-Journal-Recovery', journal),
            ('X-Omi-Upload-Recovered', label),
            ('X-Omi-Upload-Hold', hold),
        )
        if value is not None
    }
    # Isolate the comparator from the route's existing legacy-mode lookup,
    # which may read rollout_cohorts when its process cache is cold.
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda _uid: legacy_dark.LegacySyncMode.ON)
    firestore = RecordingFirestore()
    # The shape recorder captures query terminals. Spy on reference builders
    # as well to cover direct document reads and writes in this path.
    firestore_calls = Mock()
    for method in ('document', 'collection', 'collection_group', 'get_all', 'batch', 'transaction'):
        spy = Mock(wraps=getattr(firestore, method))
        firestore_calls.attach_mock(spy, method)
        monkeypatch.setattr(firestore, method, spy)

    def mismatches():
        return {
            direction: REGISTRY.get_sample_value(MISMATCH_METRIC, {'direction': direction}) for direction in DIRECTIONS
        }

    def comparisons():
        return {
            state: REGISTRY.get_sample_value(COMPARISONS_METRIC, {'journal_state': state}) for state in JOURNAL_STATES
        }

    before = mismatches()
    evaluated = comparisons()
    filename = _filename(-60).replace('audio_omi_', 'audio_omimobilebatch001_', 1)
    with install_recorder(firestore):
        response = client.post(
            '/v2/sync-local-files',
            headers=headers,
            files=[('files', (filename, b'\x00' * 32, 'application/octet-stream'))],
        )
    assert response.status_code == 202, response.text
    assert firestore_calls.mock_calls == []
    assert firestore.shapes == []
    assert comparisons() == {
        state: count + (comparison if state == journal else 0) for state, count in evaluated.items()
    }
    assert mismatches() == {direction: count + (direction == mismatch) for direction, count in before.items()}


def test_completion_latency_counts_originals_not_merged_units_or_replays(monkeypatch):
    delivered = Mock()
    monkeypatch.setattr(upload_metrics, 'DELIVERED', delivered)
    ordinary = {'upload_arrived_at': 10, 'upload_entitlement': 'paid'}
    members = [{'upload_arrived_at': stamp, 'upload_entitlement': 'free'} for stamp in (20, 50, 100)]
    upload_metrics.observe_completion(ordinary, members, merged=True, changed=True, result={}, now=400)
    assert [call.args for call in delivered.labels.return_value.observe.call_args_list] == [(380,), (350,), (300,)]
    delivered.labels.assert_called_with('free', 'unknown', 'false')
    delivered.reset_mock()
    upload_metrics.observe_completion(ordinary, [], merged=True, changed=False, result={}, now=500)
    upload_metrics.observe_completion(ordinary, [], merged=False, changed=False, result={}, now=500)
    upload_metrics.observe_completion(
        ordinary, members, merged=True, changed=True, result={'reason_code': 'source_deleted'}, now=500
    )
    upload_metrics.observe_completion(ordinary, members, merged=True, changed=False, result=None, now=500)
    delivered.labels.assert_not_called()
    upload_metrics.observe_completion(ordinary, [], merged=False, changed=True, result={}, now=400)
    delivered.labels.assert_called_once_with('paid', 'unknown', 'false')
    delivered.labels.return_value.observe.assert_called_once_with(390)


def test_upload_metrics_forward_through_worker_multiprocess_exposition():
    registry = CollectorRegistry()
    for collector in upload_metrics.COLLECTORS:
        registry.register(collector)
    upload_metrics.CREATED.labels('free').inc()
    upload_metrics.DELIVERED.labels('free', 'fg60', 'true').observe(360)
    upload_metrics.INTER_UPLOAD_GAP.labels('paid', 'fresh', 'within_group').observe(65)
    page = generate_latest(registry)
    merged = merge_metrics([(0, page), (1, page)])
    assert b'omi_batch_pipeline_created_units_total{entitlement="free",worker_process="0"}' in merged
    assert any(
        line.startswith(b'omi_batch_pipeline_upload_to_transcript_seconds_bucket{entitlement="free",hold_state="fg60"')
        and b'recovered="true"' in line
        for line in merged.splitlines()
    )
    assert b'omi_batch_pipeline_inter_upload_gap_seconds_bucket' in merged
    assert b'worker_process="1"' in merged


@pytest.mark.parametrize(
    'profile', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml', 'cloud_run_gmp_projection_pump.yaml']
)
@pytest.mark.parametrize(
    'metric',
    [
        'omi_batch_pipeline_created_units_total',
        'omi_batch_pipeline_upload_to_transcript_seconds_bucket',
        'omi_batch_pipeline_upload_to_transcript_seconds_sum',
        'omi_batch_pipeline_upload_to_transcript_seconds_count',
        'omi_batch_pipeline_upload_hold_age_seconds_bucket',
        'omi_batch_pipeline_upload_hold_age_seconds_sum',
        'omi_batch_pipeline_upload_hold_age_seconds_count',
        MISMATCH_METRIC,
        COMPARISONS_METRIC,
        'omi_batch_pipeline_inter_upload_gap_seconds_bucket',
        'omi_batch_pipeline_inter_upload_gap_seconds_sum',
        'omi_batch_pipeline_inter_upload_gap_seconds_count',
    ],
)
def test_class_metrics_survive_every_cloud_run_relabel_rule(profile, metric):
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / 'deploy' / profile).read_text())
    for rule in config['spec']['endpoints'][0]['metricRelabeling']:
        labels = {'__name__': metric}
        value = ';'.join(labels.get(name, '') for name in rule['sourceLabels'])
        matched = bool(re.fullmatch(rule['regex'], value))
        assert rule['action'] != 'keep' or matched
        assert rule['action'] != 'drop' or not matched


def test_worker_actual_health_registry_exposes_both_collectors():
    registry = CollectorRegistry()
    server = runtime.health_server(runtime.RuntimeState(), registry, 0, '127.0.0.1')
    try:
        samples = generate_latest(registry)
        assert b'omi_batch_pipeline_created_units_total' in samples
        assert b'omi_batch_pipeline_upload_to_transcript_seconds_bucket' in samples
        assert b'omi_batch_pipeline_inter_upload_gap_seconds_bucket' in samples
    finally:
        server.shutdown()
        server.server_close()


def test_sync_default_registry_serves_the_created_and_latency_families():
    response = metrics_response()
    assert b'omi_batch_pipeline_created_units_total' in response.body
    assert b'omi_batch_pipeline_upload_to_transcript_seconds_bucket' in response.body
    assert b'omi_batch_pipeline_inter_upload_gap_seconds_bucket' in response.body
