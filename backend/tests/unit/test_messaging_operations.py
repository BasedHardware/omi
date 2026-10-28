"""Operator tooling is read-only unless explicitly applied; alert/job contracts are executable."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from scripts import messaging_operations as ops
from utils.messaging import maintenance

BACKEND_DIR = Path(__file__).resolve().parents[2]
IMAGE = 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64
CHANNELS = ['projects/based-hardware/notificationChannels/123']


class Session:
    def __init__(self, existing=(), *, job=None):
        self.policies = copy.deepcopy(list(existing))
        self.job = copy.deepcopy(job)
        self.metrics = {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if urlparse(url).hostname == 'logging.googleapis.com':
            name = url.rsplit('/', 1)[-1]
            if method == 'PUT':
                self.metrics[name] = copy.deepcopy(kwargs['json'])
            elif method != 'GET':
                raise AssertionError('Logging metrics use GET or PUT')
            if name not in self.metrics:
                return SimpleNamespace(ok=False, status_code=404)
            value = copy.deepcopy(self.metrics[name])
            if method == 'GET':
                # A valid API response can omit these proto defaults. Exercise
                # normalization in both post-write verification and no-op checks.
                if value.get('disabled') is False:
                    value.pop('disabled')
                for label in value.get('metricDescriptor', {}).get('labels', []):
                    if label.get('valueType') == 'STRING':
                        label.pop('valueType')
            return SimpleNamespace(ok=True, status_code=200, json=lambda: value)
        if method == 'GET':
            if 'locations/' in url:
                if self.job is None:
                    return SimpleNamespace(ok=False, status_code=404)
                value = self.job
            elif url.endswith('alertPolicies'):
                value = {'alertPolicies': self.policies}
            else:
                value = next(p for p in self.policies if url.endswith(p['name']))
        elif 'locations/' in url:
            # Enforce the actual v2 UpdateJobRequest query/body contract.
            if method == 'PATCH':
                assert self.job is not None and url.endswith(self.job['name'])
                assert set(kwargs['params']) == {'validateOnly'}
                assert kwargs['json'] == ops.desired_job(IMAGE)
            else:
                assert method == 'POST' and url.endswith('/jobs')
                assert 'name' not in kwargs['json']
                assert kwargs['params']['jobId'] == 'messaging-maintenance-job'
            if kwargs['params']['validateOnly'] == 'false':
                self.job = copy.deepcopy(kwargs['json'])
                self.job['name'] = ops.desired_job(IMAGE)['name']
            value = {'name': 'projects/based-hardware/locations/us-central1/operations/validation'}
        else:
            value = copy.deepcopy(kwargs['json'])
            value.setdefault('name', 'projects/based-hardware/alertPolicies/' + str(len(self.policies) + 1))
            for index, condition in enumerate(value['conditions']):
                condition.setdefault('name', value['name'] + '/conditions/' + str(index))
            self.policies = [p for p in self.policies if p['name'] != value['name']] + [value]
        return SimpleNamespace(ok=True, status_code=200, json=lambda: copy.deepcopy(value))


def test_read_only_diffs_and_job_validation_never_execute():
    session = Session()
    assert ops.reconcile_job(session, IMAGE, 'check')
    assert all(c[0] == 'GET' for c in session.calls)
    ops.reconcile_job(session, IMAGE, 'validate')
    assert session.calls[-1][2]['params']['validateOnly'] == 'true'
    body = session.calls[-1][2]['json']
    task = body['template']['template']
    assert task['maxRetries'] == 1 and task['timeout'] == '600s'
    assert task['containers'][0]['args'] == ['-m', 'utils.messaging.maintenance']
    assert 'SERVICE_ACCOUNT_JSON' not in json.dumps(body)
    assert ops.reconcile_alerts(session, CHANNELS, 'check')
    assert not any(':run' in c[1] for c in session.calls)


def test_alert_create_is_verified_and_second_run_is_noop():
    session = Session()
    ops.reconcile_log_metrics(session, 'apply')
    ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert len(session.policies) == 10
    session.calls.clear()
    assert not ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)


@pytest.mark.parametrize('mode', ['validate', 'apply'])
def test_new_job_omits_name_only_on_create_and_then_matches(mode):
    session = Session()
    ops.reconcile_job(session, IMAGE, mode)
    method, url, kwargs = session.calls[-1]
    assert method == 'POST' and url.endswith('/locations/us-central1/jobs')
    assert kwargs['params'] == {
        'jobId': 'messaging-maintenance-job',
        'validateOnly': 'true' if mode == 'validate' else 'false',
    }
    assert kwargs['json'] == {k: v for k, v in ops.desired_job(IMAGE).items() if k != 'name'}
    assert (session.job is None) == (mode == 'validate')
    if mode == 'apply':
        assert not ops.reconcile_job(session, IMAGE, 'check')


def test_alert_groups_install_nine_then_rate_without_touching_other_policies(monkeypatch):
    session = Session()
    ops.reconcile_log_metrics(session, 'apply')
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'messaging_operations.py',
            'alerts',
            '--apply',
            '--alert-group',
            'operational',
            '--notification-channels',
            *CHANNELS,
        ],
    )
    monkeypatch.setattr(ops.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='fake-token'))
    monkeypatch.setattr(ops, 'AuthorizedSession', lambda credentials: session)
    assert ops.main() == 0
    assert len(session.policies) == 9
    assert all(p['displayName'] != ops.CONTEXT_RATE_POLICY for p in session.policies)
    installed = copy.deepcopy(session.policies)
    session.calls.clear()
    assert ops.reconcile_alerts(session, CHANNELS, 'apply', 'context-rate')
    assert len(session.policies) == 10 and session.policies[:9] == installed
    assert sum(c[0] == 'POST' for c in session.calls) == 1
    session.calls.clear()
    assert not ops.reconcile_alerts(session, CHANNELS, 'check', 'operational')
    assert not ops.reconcile_alerts(session, CHANNELS, 'check', 'context-rate')
    assert all(c[0] == 'GET' for c in session.calls)


def test_duplicate_policy_fails_before_any_write():
    body = ops.desired_alerts(CHANNELS)[-1]
    session = Session([body, body])
    ops.reconcile_log_metrics(session, 'apply')
    session.calls.clear()
    with pytest.raises(RuntimeError, match='Duplicate'):
        ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)


def test_context_rate_counts_summary_loss_but_not_digest_only_loss():
    policy = next(p for p in ops.desired_alerts(CHANNELS) if p['displayName'] == ops.CONTEXT_RATE_POLICY)
    query = policy['conditions'][0]['conditionPrometheusQueryLanguage']['query']
    assert 'outcome=~"degraded|summary_pending"' in query
    assert 'outcome!="unscoped"' in query
    assert '>= 20' in query and '> 0.05' in query
    assert 'digest_degraded' not in query


@pytest.mark.parametrize('mode', ['validate', 'apply'])
def test_existing_job_update_uses_v2_job_body_without_mask_or_execution(mode):
    old = ops.desired_job(IMAGE.replace('a' * 64, 'b' * 64))
    session = Session(job=old)
    assert not ops.reconcile_job(session, IMAGE, mode)
    method, url, kwargs = session.calls[-1]
    assert method == 'PATCH' and url == 'https://run.googleapis.com/v2/' + old['name']
    assert kwargs['params'] == {'validateOnly': 'true' if mode == 'validate' else 'false'}
    assert session.job == (old if mode == 'validate' else ops.desired_job(IMAGE))
    assert not any(':run' in call[1] for call in session.calls)


def test_cli_validate_existing_job_never_persists(monkeypatch):
    old = ops.desired_job(IMAGE.replace('a' * 64, 'b' * 64))
    session = Session(job=old)
    monkeypatch.setattr(sys, 'argv', ['messaging_operations.py', 'job', '--image', IMAGE, '--validate'])
    monkeypatch.setattr(ops.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='fake-token'))
    monkeypatch.setattr(ops, 'AuthorizedSession', lambda credentials: session)
    assert ops.main() == 0
    assert session.calls[-1][0] == 'PATCH'
    assert session.calls[-1][2]['params'] == {'validateOnly': 'true'}
    assert session.job == old


def test_log_metrics_require_explicit_apply_and_verify_then_become_noop():
    session = Session()
    assert ops.reconcile_log_metrics(session, 'check')
    assert all(c[0] == 'GET' for c in session.calls)
    with pytest.raises(RuntimeError, match='must MATCH'):
        ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)
    assert ops.reconcile_log_metrics(session, 'apply')
    assert len(session.metrics) == 6
    assert sum(c[0] == 'PUT' for c in session.calls) == 6
    session.calls.clear()
    # Proto JSON can omit default false; it must still compare equal.
    for body in session.metrics.values():
        body.pop('disabled')
    assert not ops.reconcile_log_metrics(session, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)


@pytest.mark.parametrize('mismatch', ['value_type', 'reason_type', 'extra_label'])
def test_incompatible_existing_log_metric_fails_before_any_write(mismatch):
    session = Session()
    ops.reconcile_log_metrics(session, 'apply')
    metrics = list(session.metrics.values())
    metrics[0]['description'] = 'Earlier compatible drift must not be written before the schema audit finishes'
    if mismatch == 'value_type':
        metrics[-1]['metricDescriptor']['valueType'] = 'DISTRIBUTION'
    elif mismatch == 'reason_type':
        metric = session.metrics['omi_messaging_maintenance_failures']
        metric['metricDescriptor']['labels'][0]['valueType'] = 'INT64'
    else:
        metrics[-1]['metricDescriptor']['labels'] = [{'key': 'unmanaged', 'valueType': 'STRING'}]
    session.calls.clear()
    with pytest.raises(RuntimeError, match='schema differs'):
        ops.reconcile_log_metrics(session, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)


def test_single_events_below_count_floor_and_documented_sensitive_exceptions():
    policies = ops.desired_alerts(CHANNELS)
    metrics = {m['name']: m for m in json.loads((ops.ROOT / 'log-metrics.json').read_text())}
    for policy in policies:
        condition = policy['conditions'][0]
        if 'conditionMatchedLog' in condition:
            assert policy['displayName'] == 'Messaging: decoder unavailable'
            assert 'at startup; voice notes will be declined' in condition['conditionMatchedLog']['filter']
            assert 'once-per-startup' in policy['documentation']['content']
        threshold = condition.get('conditionThreshold')
        if not threshold:
            continue
        if 'logging.googleapis.com/user/' not in threshold['filter']:
            assert policy['displayName'] == 'Messaging: cleanup execution failed'
            assert threshold['thresholdValue'] == 0 and threshold['comparison'] == 'COMPARISON_GT'
            assert threshold['aggregations'][0]['alignmentPeriod'] == '300s'
            assert 'exhausted' in policy['documentation']['content']
            continue
        metric_name = threshold['filter'].split('logging.googleapis.com/user/')[1].split('"')[0]
        metric = metrics.pop(metric_name)
        assert metric['metricDescriptor']['metricKind'] == 'DELTA'
        assert metric['metricDescriptor']['valueType'] == 'INT64'
        aggregation = threshold['aggregations'][0]
        assert aggregation['perSeriesAligner'] == 'ALIGN_SUM'
        assert aggregation['crossSeriesReducer'] == 'REDUCE_SUM'
        floor = 2 if 'maintenance' in metric_name else 3
        assert aggregation['alignmentPeriod'] == ('3600s' if floor == 2 else '900s')
        assert threshold['comparison'] == 'COMPARISON_GT' and threshold['thresholdValue'] == floor - 1
        assert not (1 > threshold['thresholdValue']) and floor > threshold['thresholdValue']
        assert threshold['duration'] == '0s' and threshold['trigger'] == {'count': 1}
        assert 'notificationRateLimit' not in policy['alertStrategy']
        if metric.get('labelExtractors'):
            assert aggregation['groupByFields'] == ['metric.label.reason']
    assert not metrics


def test_existing_log_alert_is_replaced_by_threshold_preserving_condition_identity():
    session = Session()
    ops.reconcile_log_metrics(session, 'apply')
    ops.reconcile_alerts(session, CHANNELS, 'apply')
    policy = next(p for p in session.policies if p['displayName'] == 'Messaging: webhook 5xx')
    condition_name = policy['conditions'][0]['name']
    policy['conditions'][0].pop('conditionThreshold')
    policy['conditions'][0]['conditionMatchedLog'] = {'filter': 'old filter'}
    policy['alertStrategy']['notificationRateLimit'] = {'period': '3600s'}
    session.calls.clear()
    ops.reconcile_alerts(session, CHANNELS, 'apply')
    patches = [c for c in session.calls if c[0] == 'PATCH']
    assert len(patches) == 1
    body = patches[0][2]['json']
    assert body['conditions'][0]['name'] == condition_name
    assert 'conditionMatchedLog' not in body['conditions'][0]
    assert 'conditionThreshold' in body['conditions'][0]
    assert body['alertStrategy'] == {'autoClose': '3600s'}


@pytest.mark.parametrize(
    'image',
    [
        'latest',
        'gcr.io/based-hardware/backend:main',
        'gcr.io/other/backend@sha256:' + 'a' * 64,
        # Plan B B3: only the fat backend image or its workers role image runs the job.
        'gcr.io/based-hardware-dev/backend-workers@sha256:' + 'a' * 64,
        'gcr.io/based-hardware/backend-api@sha256:' + 'a' * 64,
        'gcr.io/based-hardware/pusher@sha256:' + 'a' * 64,
        'us-docker.pkg.dev/based-hardware/backend-workers@sha256:' + 'a' * 64,
        'gcr.io/based-hardware/backend-workers:aaaaaaa',
    ],
)
def test_job_rejects_unpinned_or_foreign_images(image):
    with pytest.raises(ValueError):
        ops.desired_job(image)


@pytest.mark.parametrize('image', [IMAGE, 'gcr.io/based-hardware/backend-workers@sha256:' + 'a' * 64])
def test_job_admits_the_backend_image_and_its_workers_role_digest(image):
    assert ops.desired_job(image)['template']['template']['containers'][0]['image'] == image


def test_job_images_follow_the_runtime_image_registry():
    registry = json.loads((BACKEND_DIR / 'runtime_images.json').read_text(encoding='utf-8'))
    spec = registry['services']['messaging-maintenance']
    assert ops.MAINTENANCE_JOB_IMAGES == (spec['current_image'], spec['image'])
    assert spec['role'] == 'workers'
    workers = next(image for image in registry['images'] if image['name'] == spec['image'])
    assert 'utils.messaging.maintenance' in workers['entrypoints']


def test_maintenance_failure_is_redacted_and_nonzero(monkeypatch, caplog):
    def fail():
        raise PermissionError('private account and provider data')

    monkeypatch.setattr(maintenance, 'run', fail)
    with pytest.raises(SystemExit) as error:
        maintenance.main()
    assert error.value.code == 1
    assert 'outcome=failed reason=permission error_type=PermissionError' in caplog.text
    assert 'private account' not in caplog.text


def test_zero_threshold_omitted_by_proto_json_still_matches_and_verifies():
    class OmittingSession(Session):
        def request(self, method, url, **kwargs):
            response = super().request(method, url, **kwargs)
            if method != 'GET' or 'alertPolicies' not in url or not response.ok:
                return response
            # Copy before trimming so the stored policy keeps its declared zero.
            body = copy.deepcopy(response.json())
            for policy in body.get('alertPolicies', [body]):
                for condition in policy.get('conditions', []):
                    threshold = condition.get('conditionThreshold', {})
                    if threshold.get('thresholdValue') == 0:
                        del threshold['thresholdValue']
            return SimpleNamespace(ok=True, status_code=200, json=lambda: body)

    session = OmittingSession()
    ops.reconcile_log_metrics(session, 'apply')
    ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert len(session.policies) == 10
    assert not ops.reconcile_alerts(session, CHANNELS, 'check')
