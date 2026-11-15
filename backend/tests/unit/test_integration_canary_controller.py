"""Offline executable-path tests: real controller, registry, metrics, private journal.

The authenticated transport and CAS server are deterministic fakes; no production
reads or snapshot inputs. Fake-clock sleeps execute the full foreground timeline.
"""

from __future__ import annotations

import copy
import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import integration_canary_controller as c
from scripts import integration_canary_metrics as m


class FakeClock:
    def __init__(self):
        self.now = 2_000_000_040.0
        self.elapsed = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        assert 0 < seconds <= 60
        self.sleeps.append(seconds)
        self.now += seconds
        self.elapsed += seconds


def reply(doc):
    raw = c.canonical(doc).encode()
    return m.Reply(copy.deepcopy(doc), raw, {})


def metadata(name, service=None):
    return {
        'name': name,
        'namespace': '123456',
        'uid': 'uid-' + name,
        'resourceVersion': '1',
        'generation': 1,
        'labels': {'serving.knative.dev/service': service, 'custom-label': 'preserved'} if service else {},
        'annotations': {
            'autoscaling.knative.dev/maxScale': '23',
            'autoscaling.knative.dev/minScale': '1',
            'run.googleapis.com/cpu-throttling': 'false',
            'run.googleapis.com/container-dependencies': '{"metrics":["app"]}',
            'run.googleapis.com/secrets': 'alias:projects/123456/secrets/runtime',
        },
    }


def env_values():
    return [
        {'name': 'FRESH_QUEUE', 'value': 'fresh-actual'},
        {'name': 'PFX_READS', 'value': '73'},
        {'name': 'FSR_LEADER_LEASE_TTL_SECONDS', 'value': '121'},
        {'name': 'CREDENTIAL', 'valueFrom': {'secretKeyRef': {'name': 'runtime', 'key': '7'}}},
        {'name': c.PROVIDER, 'value': 'false'},
        {'name': c.STAMP, 'value': 'previous-source'},
    ]


def revision(name, service):
    return {
        'apiVersion': 'serving.knative.dev/v1',
        'kind': 'Revision',
        'metadata': metadata(name, service),
        'spec': {
            'serviceAccountName': 'runtime@based-hardware.iam.gserviceaccount.com',
            'containerConcurrency': 37,
            'timeoutSeconds': 999,
            'volumes': [{'name': 'config', 'secret': {'secretName': 'runtime'}}],
            'containers': [
                {
                    'name': 'app',
                    'image': 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64,
                    'ports': [{'containerPort': 8080}],
                    'env': env_values(),
                    'resources': {'limits': {'cpu': '2', 'memory': '4Gi'}},
                    'startupProbe': {'httpGet': {'path': '/health', 'port': 8080}},
                },
                {
                    'name': 'metrics',
                    'image': 'gcr.io/based-hardware/metrics@sha256:' + 'b' * 64,
                    'resources': {'limits': {'cpu': '0.25', 'memory': '512Mi'}},
                    'volumeMounts': [{'name': 'config', 'mountPath': '/etc/metrics'}],
                },
            ],
        },
        'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]},
    }


class FakeTransport:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.cloud = None
        self.row = lambda _at: (1000, 0, 0.50)
        self.whole_cpu = 0.50
        self.page_hook = lambda _params, doc: doc
        self.missing = None
        self.config = reply(
            {'config': {'Labels': {'org.opencontainers.image.revision': c.SOURCE}, 'Env': ['OMI_ROLE=workers']}}
        )
        self.config_digest = c.digest_bytes(self.config.raw)
        self.manifest = reply({'schemaVersion': 2, 'config': {'digest': self.config_digest}})
        self.image = 'gcr.io/based-hardware/backend@' + c.digest_bytes(self.manifest.raw)

    def request(self, method, url, body=None, deadline=None, registry_blob=False):
        self.calls.append((method, url, copy.deepcopy(body)))
        parts = urlsplit(url)
        assert parts.scheme == 'https'
        if method == 'PUT':
            assert url == c.RUN_URL and self.cloud is not None
            return reply(self.cloud.cas(body))
        if parts.netloc == 'gcr.io':
            if '/manifests/' in parts.path:
                return self.manifest
            if '/blobs/' in parts.path:
                return self.config
            assert parts.path.endswith('/tags/list')
            return reply({'manifest': {self.image.split('@')[1]: {'tag': [c.SOURCE[:7]]}}})
        assert parts.netloc == 'monitoring.googleapis.com'
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        start = int(m.timestamp(params['interval.startTime']))
        end = int(m.timestamp(params['interval.endTime']))
        period = int(params['aggregation.alignmentPeriod'][:-1])
        cpu = 'container/cpu/utilizations' in params['filter']
        assert params['aggregation.perSeriesAligner'] == 'ALIGN_SUM'
        assert params['aggregation.crossSeriesReducer'] == 'REDUCE_SUM'
        if cpu:
            assert params['secondaryAggregation.perSeriesAligner'] == 'ALIGN_PERCENTILE_95'
            assert params['secondaryAggregation.alignmentPeriod'] == f'{period}s'
        codes = ['cpu'] if cpu else ['2xx', '5xx']
        series = []
        for code in codes:
            points = []
            for at in range(start + period, end + 1, period):
                if self.missing == ('cpu' if cpu else 'requests', at):
                    continue
                total, errors, utilization = self.row(at)
                value = (
                    {'doubleValue': self.whole_cpu if period == 1800 else utilization}
                    if cpu
                    else {'int64Value': str(errors if code == '5xx' else total - errors)}
                )
                points.append({'interval': {'startTime': m.iso(at - period), 'endTime': m.iso(at)}, 'value': value})
            series.append(
                {
                    'valueType': 'DOUBLE' if cpu else 'INT64',
                    'metricKind': 'GAUGE' if cpu else 'DELTA',
                    'metric': {'labels': {} if cpu else {'response_code_class': code}},
                    'points': points,
                }
            )
        return reply(self.page_hook(params, {'timeSeries': series}))


class FakeCloud(c.Cloud):
    def __init__(self, transport):
        super().__init__(transport)
        transport.cloud = self
        self.services, self.revisions = {}, {}
        self.writes = []
        self.mode = None
        self.read_delay = 0
        self.pending = None
        for service in c.SERVICES:
            name = c.ROLLBACK if service == c.SERVICE else service + '-serving'
            rev = revision(name, service)
            self.revisions[name] = rev
            # Failed/latest template differs in resources, sidecars and queue routing.
            failed = c.template(rev, service + '-failed')
            failed['spec']['containers'] = [copy.deepcopy(failed['spec']['containers'][0])]
            failed['spec']['containers'][0]['resources']['limits']['cpu'] = '8'
            failed['spec']['containers'][0]['env'][0]['value'] = 'wrong-failed-queue'
            self.services[service] = {
                'apiVersion': 'serving.knative.dev/v1',
                'kind': 'Service',
                'metadata': metadata(service),
                'spec': {
                    'template': failed,
                    'traffic': [
                        {'revisionName': name, 'percent': 100},
                        {'revisionName': name, 'percent': 0, 'tag': 'retained'},
                    ],
                },
                'status': {
                    'conditions': [{'type': 'Ready', 'status': 'True'}],
                    'observedGeneration': 1,
                    'latestCreatedRevisionName': service + '-failed',
                    'latestReadyRevisionName': name,
                    'traffic': [
                        {'revisionName': name, 'percent': 100},
                        {'revisionName': name, 'percent': 0, 'tag': 'retained'},
                    ],
                },
            }

    def head(self):
        return c.SOURCE

    def read(self, kind, name):
        if kind == 'services' and name == c.SERVICE and self.pending:
            if self.read_delay:
                self.read_delay -= 1
            else:
                self.services[name]['status']['traffic'] = self.pending
                self.pending = None
        return copy.deepcopy((self.services if kind == 'services' else self.revisions)[name])

    def cas(self, body):
        live = self.services[c.SERVICE]
        self.writes.append(copy.deepcopy(body))
        # Verify the intent is durable at the transport boundary in every test.
        if hasattr(self, 'journal'):
            assert self.journal.read()['intent']['status'] == 'uncertain'
        if self.mode == 'conflict':
            raise m.Refused('cas_conflict')
        assert body['metadata']['resourceVersion'] == live['metadata']['resourceVersion']
        if self.mode == 'lost_before':
            raise TimeoutError('private provider body must never escape')
        next_doc = copy.deepcopy(body)
        next_doc['metadata']['generation'] = live['metadata']['generation'] + 1
        next_doc['metadata']['resourceVersion'] = str(int(live['metadata']['resourceVersion']) + 1)
        next_doc['status'] = copy.deepcopy(live['status'])
        next_doc['status']['observedGeneration'] = next_doc['metadata']['generation']
        candidate = body['spec']['template']['metadata']['name']
        if candidate not in self.revisions:
            rev = copy.deepcopy(body['spec']['template'])
            rev['apiVersion'], rev['kind'] = 'serving.knative.dev/v1', 'Revision'
            rev['metadata'].update(uid='uid-' + candidate, resourceVersion='1', namespace='123456', generation=1)
            rev['metadata']['labels']['serving.knative.dev/service'] = c.SERVICE
            rev['status'] = {'conditions': [{'type': 'Ready', 'status': 'True'}]}
            self.revisions[candidate] = rev
        next_doc['status']['latestCreatedRevisionName'] = candidate
        next_doc['status']['latestReadyRevisionName'] = candidate
        requested = copy.deepcopy(body['spec']['traffic'])
        if self.read_delay:
            self.pending = requested
        else:
            next_doc['status']['traffic'] = requested
        self.services[c.SERVICE] = next_doc
        if self.mode == 'lost_after':
            raise TimeoutError('private provider body must never escape')
        return next_doc


@pytest.fixture
def harness(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock)
    cloud = FakeCloud(transport)
    journal = c.Journal(tmp_path / 'private.json')
    cloud.journal = journal
    controller = c.Controller(
        journal,
        cloud,
        c.Registry(transport),
        m.Metrics(transport, clock),
        clock,
        {'GITHUB_ACTIONS': 'true', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'},
    )
    runtime = {'services': {}}
    for service in c.SERVICES:
        entries = [{'name': k, 'value': v} for k, v in c.QUALITY.items()]
        if service in ('backend-sync', c.SERVICE):
            entries.append({'name': c.BACKOFF, 'value': 'false'})
        runtime['services'][service] = {'env': entries}
    controller.prepare(c.SOURCE, transport.image, c.SERVICE + '-' + c.SOURCE[:7] + '-123-1')
    return controller, cloud, transport, clock, runtime


def make_candidate(harness):
    controller, *_rest, runtime = harness
    controller.candidate(runtime)
    return harness


def test_full_foreground_happy_path_and_immutable_baseline(harness, capsys):
    controller, cloud, transport, clock, runtime = make_candidate(harness)
    baseline = copy.deepcopy(controller.state['baseline'])
    controller.promote()
    assert controller.state['phase'] == 'complete'
    assert controller.state['baseline'] == baseline
    assert [c.traffic(b['spec']['traffic']) for b in cloud.writes] == [
        {c.ROLLBACK: 100},
        {c.ROLLBACK: 75, controller.state['candidate']: 25},
        {controller.state['candidate']: 100},
    ]
    moves = controller.state['moves']
    assert moves[1]['verified_at'] - moves[0]['verified_at'] >= 300
    assert clock.time() - moves[1]['verified_at'] >= 1200
    assert controller.state['health']['state'] == 'below_threshold'
    assert 'integration_canary: immature' in capsys.readouterr().out
    assert max(clock.sleeps) <= 60 and clock.elapsed < 2700
    assert all(b['metadata']['resourceVersion'] == str(i + 1) for i, b in enumerate(cloud.writes))
    assert all(b['spec']['traffic'][-1]['tag'] == 'retained' for b in cloud.writes)


def test_failed_latest_template_does_not_disqualify_the_exact_ready_serving_clone(harness):
    controller, cloud, transport, _clock, runtime = harness
    controller.journal.path.unlink()
    cloud.services[c.SERVICE]['status']['conditions'] = [{'type': 'Ready', 'status': 'False'}]
    controller.prepare(c.SOURCE, transport.image, controller.state['candidate'])
    controller.candidate(runtime)
    assert c.app(cloud.revisions[controller.state['candidate']]['spec'])['resources']['limits']['cpu'] == '2'
    assert len(cloud.writes) == 1


def test_failed_actual_serving_revision_still_refuses_preparation(harness):
    controller, cloud, transport, _clock, _runtime = harness
    controller.journal.path.unlink()
    cloud.revisions[c.ROLLBACK]['status']['conditions'] = [{'type': 'Ready', 'status': 'False'}]
    with pytest.raises(m.Refused, match='not_ready'):
        controller.prepare(c.SOURCE, transport.image, controller.state['candidate'])
    assert cloud.writes == []


def test_monotonic_hold_cannot_be_shortened_by_wall_clock_jump(harness, monkeypatch):
    controller, _cloud, _transport, clock, _runtime = make_candidate(harness)
    controller.move(25)
    clock.now += 3600
    started = clock.monotonic()
    monkeypatch.setattr(controller, 'sample', lambda percent: {'state': 'immature'})
    controller.observe(25, 300)
    assert clock.monotonic() - started >= 300


def test_candidate_honors_source_forbidden_entries_before_first_traffic(harness):
    controller, cloud, _transport, _clock, runtime = harness
    runtime['services'][c.SERVICE]['forbidden_env'] = ['CREDENTIAL']
    controller.candidate(runtime)
    assert 'CREDENTIAL' not in c.env_map(c.app(cloud.revisions[controller.state['candidate']]['spec'])['env'])
    assert c.traffic(cloud.services[c.SERVICE]['status']['traffic']) == {c.ROLLBACK: 100}


def test_serving_clone_preserves_every_non_application_field(harness):
    controller, cloud, _transport, _clock, runtime = make_candidate(harness)
    old = controller.state['services'][c.SERVICE]['revision']
    candidate = cloud.revisions[controller.state['candidate']]
    expected = copy.deepcopy(old['spec'])
    expected['containers'][0] = copy.deepcopy(candidate['spec']['containers'][0])
    assert candidate['spec'] == expected
    assert candidate['spec']['containers'][0]['resources'] == old['spec']['containers'][0]['resources']
    assert candidate['spec']['containers'][1] == old['spec']['containers'][1]
    assert c.annotations(candidate['metadata']) == c.annotations(old['metadata'])
    env = c.env_map(c.app(candidate['spec'])['env'])
    assert env['FRESH_QUEUE']['value'] == 'fresh-actual'
    assert env['CREDENTIAL'] == c.env_map(c.app(old['spec'])['env'])['CREDENTIAL']
    assert env[c.STAMP]['value'] == c.SOURCE
    assert c.app(candidate['spec'])['image'] == controller.state['image']
    assert c.app(candidate['spec'])['resources']['limits']['cpu'] == '2'
    assert controller.journal.path.stat().st_mode & 0o777 == 0o600


def rows(end, errors=0, cpu=0.5):
    return [m.Minute(t, 1000, errors, cpu) for t in range(end - 540, end + 1, 60)]


@pytest.mark.parametrize(
    ('errors', 'cpu', 'baseline', 'expected'),
    [
        (15, 0.94999, 0.001, 'below_threshold'),
        (16, 0.5, 0.001, 'rollback'),
        (18, 0.5, 0.009, 'below_threshold'),
        (19, 0.5, 0.009, 'rollback'),
        (0, 0.95, 0.001, 'rollback'),
        (0, 0.94999, 0.001, 'below_threshold'),
    ],
)
def test_exact_threshold_boundaries(errors, cpu, baseline, expected):
    result = m.decision(rows(1800, errors, cpu), moved_at=0, now=1920, baseline_share=baseline, end=1800)
    assert result['state'] == expected


def test_one_bad_minute_cannot_trigger_sustained_cpu_or_fraction():
    samples = rows(1800)
    samples[-1] = m.Minute(1800, 1, 1, 0.99)
    assert m.decision(samples, moved_at=0, now=1920, baseline_share=0.005, end=1800)['state'] == 'below_threshold'
    # Fractions are weighted by REQUEST COUNT, not a mean of ten fractions.
    assert sum(r.errors for r in samples) / sum(r.requests for r in samples) < 0.015


def test_warmup_each_move_and_full_window_boundaries():
    assert m.decision([], moved_at=0, now=300, baseline_share=0.001, end=180)['state'] == 'immature'
    assert m.decision([], moved_at=60, now=900, baseline_share=0.001, end=780)['state'] == 'immature'
    assert m.decision(rows(780), moved_at=0, now=900, baseline_share=0.001, end=780)['state'] == 'below_threshold'
    assert m.decision([], moved_at=0.1, now=900, baseline_share=0.001, end=780)['state'] == 'immature'
    assert m.decision([], moved_at=300, now=1020, baseline_share=0.001, end=900)['state'] == 'immature'


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, '0.1'])
def test_bad_numeric_evidence(value):
    with pytest.raises(m.Refused):
        m.decision(rows(1800), moved_at=0, now=1920, baseline_share=value, end=1800)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'idle', 'stale', 'future'])
def test_unknown_metric_windows_refuse(mutation):
    samples = rows(1800)
    now = 1920
    if mutation == 'missing':
        samples.pop()
    elif mutation == 'duplicate':
        samples[-1] = samples[0]
    elif mutation == 'idle':
        samples[-1] = m.Minute(1800, 0, 0, 0.2)
    elif mutation == 'stale':
        now = 1981
    else:
        now = 1799
    with pytest.raises(m.Refused):
        m.decision(samples, moved_at=0, now=now, baseline_share=0.001, end=1800)


@pytest.mark.parametrize(
    'error',
    [
        {'executionErrors': [{}]},
        {'unreachable': ['zone']},
        {'error': {'code': 403}},
        {'timeSeries': 'bad'},
        {'nextPageToken': 2},
    ],
)
def test_error_on_second_page_never_returns_partial_evidence(harness, error):
    controller, _cloud, transport, _clock, _runtime = harness

    def hook(params, doc):
        if 'pageToken' not in params:
            return doc | {'nextPageToken': 'second'}
        return error

    transport.page_hook = hook
    with pytest.raises(m.Refused):
        controller.metrics.collect()


def test_metrics_page_budget_and_no_retry(harness):
    controller, _cloud, transport, _clock, _runtime = harness
    before = len(transport.calls)
    transport.page_hook = lambda params, doc: doc | {'nextPageToken': params.get('pageToken', '') + 'x'}
    with pytest.raises(m.Refused, match='metric_page_budget'):
        controller.metrics.collect()
    assert len(transport.calls) - before == 8


def test_actual_whole_30m_percentile_not_max_or_mean_of_minute_percentiles(harness):
    controller, _cloud, transport, clock, _runtime = harness
    end = int((clock.time() - m.METRIC_LAG) // 60) * 60
    transport.row = lambda at: (1000, 9, 0.99 if at == end else 0.1)
    transport.whole_cpu = 0.90
    assert controller.metrics.collect(30, preflight=True)['cpu_p95'] == 0.90
    transport.whole_cpu = 0.900001
    with pytest.raises(m.Refused, match='preflight_threshold'):
        controller.metrics.collect(30, preflight=True)
    transport.whole_cpu = 0.5
    transport.row = lambda _at: (1000, 10, 0.2)
    with pytest.raises(m.Refused, match='preflight_threshold'):
        controller.metrics.collect(30, preflight=True)


@pytest.mark.parametrize('metric', ['requests', 'cpu'])
def test_missing_latest_minute_refuses(harness, metric):
    controller, _cloud, transport, clock, _runtime = harness
    transport.missing = (metric, int((clock.time() - m.METRIC_LAG) // 60) * 60)
    with pytest.raises(m.Refused):
        controller.metrics.collect()


@pytest.mark.parametrize('change', ['rv', 'cpu', 'queue', 'sidecar', 'uid'])
def test_candidate_refuses_prepare_drift(harness, change):
    controller, cloud, _transport, _clock, runtime = harness
    doc = cloud.services[c.SERVICE]
    if change == 'rv':
        doc['metadata']['resourceVersion'] = '2'
    elif change == 'uid':
        doc['metadata']['uid'] = 'replaced'
    elif change == 'cpu':
        doc['spec']['template']['spec']['containers'][0]['resources']['limits']['cpu'] = '10'
    elif change == 'queue':
        doc['spec']['template']['spec']['containers'][0]['env'][0]['value'] = 'drift'
    else:
        doc['spec']['template']['spec']['containers'].append({'name': 'foreign', 'image': 'foreign'})
    with pytest.raises(m.Refused):
        controller.candidate(runtime)
    assert cloud.writes == []


@pytest.mark.parametrize('name', ['FRESH_QUEUE', 'PFX_READS', 'CREDENTIAL'])
def test_overlay_must_preserve_serving_ops_and_secret_references(harness, name):
    controller, cloud, _transport, _clock, runtime = harness
    runtime['services'][c.SERVICE]['env'].append({'name': name, 'value': 'foreign'})
    with pytest.raises(m.Refused, match='serving_ops_env_changed'):
        controller.candidate(runtime)
    assert not cloud.writes


@pytest.mark.parametrize('change', ['quality', 'backoff', 'provider', 'other_quality', 'account'])
def test_source_configuration_contract(harness, change):
    controller, cloud, _transport, _clock, runtime = harness
    env = runtime['services'][c.SERVICE]['env']
    if change == 'quality':
        env[0]['value'] = 'false'
    elif change == 'other_quality':
        runtime['services']['backend']['env'][0]['value'] = 'false'
    elif change == 'backoff':
        env[-1]['value'] = 'true'
    elif change == 'provider':
        env.append({'name': c.PROVIDER, 'value': 'true'})
    else:
        runtime['services'][c.SERVICE]['service_account'] = 'foreign@example.test'
    with pytest.raises(m.Refused):
        controller.candidate(runtime)
    assert not cloud.writes


@pytest.mark.parametrize('change', ['revision', 'digest', 'stamp', 'scale', 'sidecar', 'not_ready', 'unobserved'])
def test_promote_refuses_changed_identity_or_config(harness, change):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    doc = cloud.services[c.SERVICE]
    rev = cloud.revisions[controller.state['candidate']]
    if change == 'revision':
        doc['status']['latestReadyRevisionName'] = 'foreign'
    elif change == 'digest':
        c.app(rev['spec'])['image'] = 'gcr.io/based-hardware/backend@sha256:' + 'f' * 64
    elif change == 'stamp':
        next(e for e in c.app(rev['spec'])['env'] if e['name'] == c.STAMP)['value'] = 'foreign'
    elif change == 'scale':
        doc['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/maxScale'] = '24'
    elif change == 'sidecar':
        rev['spec']['containers'][1]['resources']['limits']['cpu'] = '1'
    elif change == 'not_ready':
        rev['status']['conditions'][0]['status'] = 'False'
    else:
        doc['status']['observedGeneration'] = 0
    with pytest.raises(m.Refused):
        controller.promote()
    assert len(cloud.writes) == 1


@pytest.mark.parametrize('mode', ['conflict', 'lost_before', 'lost_after'])
def test_uncertain_candidate_write_is_never_replayed(harness, mode):
    controller, cloud, _transport, _clock, runtime = harness
    cloud.mode = mode
    with pytest.raises((m.Refused, TimeoutError)):
        controller.candidate(runtime)
    assert controller.journal.read()['intent']['status'] == 'uncertain'
    cloud.mode = None
    with pytest.raises((m.Refused, KeyError)):
        controller.candidate(runtime)
    assert len(cloud.writes) == 1
    controller.failure_receipt()
    assert controller.journal.read()['operator_receipt']['write'] == 'uncertain'


def test_timer_starts_only_after_actual_readback(harness):
    controller, cloud, _transport, clock, _runtime = make_candidate(harness)
    before = clock.time()
    cloud.read_delay = 3
    controller.move(25)
    assert controller.state['moved_at'] > before
    assert controller.state['moved_at'] == clock.time()
    assert clock.elapsed == 15


def test_rollback_idempotent_after_25_and_no_second_flip(harness):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    controller.move(25)
    controller.rollback()
    assert c.traffic(cloud.services[c.SERVICE]['status']['traffic']) == {c.ROLLBACK: 100}
    count = len(cloud.writes)
    controller.rollback()
    assert len(cloud.writes) == count
    assert controller.state['phase'] == 'rolled_back'


def test_rollback_before_candidate_is_read_only(harness):
    controller, cloud, *_ = harness
    controller.rollback()
    controller.rollback()
    assert not cloud.writes


def test_rollback_refuses_foreign_writer(harness):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    controller.move(25)
    cloud.services[c.SERVICE]['spec']['template']['spec']['containerConcurrency'] = 99
    with pytest.raises(m.Refused, match='rollback_foreign_writer'):
        controller.rollback()
    assert len(cloud.writes) == 2


def test_full_postwarmup_cpu_failure_rolls_back_exact_revision(harness):
    controller, cloud, transport, clock, _runtime = make_candidate(harness)
    controller.move(25)
    controller.observe(25, 300)
    controller.move(100)
    anchor = controller.state['moved_at']
    # Warmup is bad too; it does not get included in the ten-minute decision.
    transport.row = lambda _at: (1000, 0, 0.95)
    with pytest.raises(m.Refused, match='qualified_health_rollback'):
        controller.observe(100, 1200)
    assert clock.time() - anchor >= 780
    assert controller.state['phase'] == 'rolled_back'
    assert c.traffic(cloud.services[c.SERVICE]['status']['traffic']) == {c.ROLLBACK: 100}


def test_warmup_only_cpu_spike_never_rolls_back(harness):
    controller, cloud, transport, _clock, _runtime = make_candidate(harness)
    controller.move(25)
    controller.observe(25, 300)
    controller.move(100)
    anchor = controller.state['moved_at']
    transport.row = lambda at: (1000, 0, 0.99 if at <= anchor + 180 else 0.5)
    controller.observe(100, 1200)
    assert controller.state['health']['state'] == 'below_threshold'
    assert len(cloud.writes) == 3


def test_image_must_be_registry_bound_not_caller_asserted(harness):
    controller, _cloud, transport, _clock, _runtime = harness
    image = transport.image
    assert controller.registry.verify(image, c.SOURCE) == image
    with pytest.raises(m.Refused):
        controller.registry.verify(image.replace('backend@', 'backend:latest@'), c.SOURCE)
    with pytest.raises(m.Refused):
        controller.registry.verify('gcr.io/based-hardware/backend:badcafe', c.SOURCE)
    assert controller.registry.verify('gcr.io/based-hardware/backend:' + c.SOURCE[:7], c.SOURCE) == image
    transport.config.doc['config']['Labels']['org.opencontainers.image.revision'] = 'foreign'
    with pytest.raises(m.Refused, match='registry_source_mismatch'):
        controller.registry.verify(image, c.SOURCE)


def test_bindings_and_journal_reuse_refuse(harness):
    controller, cloud, transport, _clock, _runtime = harness
    with pytest.raises(m.Refused, match='journal_already_exists'):
        controller.prepare(c.SOURCE, transport.image, controller.state['candidate'])
    controller.environ['GITHUB_RUN_ID'] = '456'
    with pytest.raises(m.Refused, match='journal_binding'):
        controller.load()
    controller.environ['GITHUB_ACTIONS'] = 'false'
    with pytest.raises(m.Refused, match='workflow_only'):
        controller.load()


def test_run_attempt_cannot_reuse_previous_journal(harness):
    controller, *_ = harness
    controller.environ['GITHUB_RUN_ATTEMPT'] = '2'
    with pytest.raises(m.Refused, match='journal_binding'):
        controller.load()


def test_registry_failed_attempts_and_git_calls_consume_finite_budgets(harness, monkeypatch):
    controller, _cloud, transport, _clock, _runtime = harness
    registry = c.Registry(transport)

    def fail(*args, **kwargs):
        raise m.Refused('unavailable')

    monkeypatch.setattr(transport, 'request', fail)
    for _ in range(4):
        with pytest.raises(m.Refused, match='unavailable'):
            registry.get('backend', 'manifests', 'missing')
    with pytest.raises(m.Refused, match='registry_request_budget'):
        registry.get('backend', 'manifests', 'missing')
    monkeypatch.setattr(c, 'command', lambda argv: '')
    for _ in range(16):
        registry.git(['git', 'rev-parse', 'HEAD'])
    with pytest.raises(m.Refused, match='registry_git_budget'):
        registry.git(['git', 'rev-parse', 'HEAD'])


def test_io_deadline_clips_subprocess_timeout_and_expires(monkeypatch):
    clock = FakeClock()
    timeouts = []
    real_popen = m.subprocess.Popen

    def popen(argv, **kwargs):
        timeouts.append(m.io_remaining(30))
        return real_popen([sys.executable, '-c', 'print("ok")'], **kwargs)

    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    with pytest.raises(m.Refused, match='io_deadline'):
        with m.io_budget(5, clock):
            assert m.command(['gcloud']) == 'ok'
            clock.sleep(6)
            with pytest.raises(m.Refused, match='io_deadline'):
                m.command(['gcloud'])
    assert timeouts == [5]


def test_real_subprocess_output_cap_and_stall_are_reaped(monkeypatch):
    monkeypatch.setattr(m, 'MAX_BYTES', 256)
    with pytest.raises(m.Refused, match='command_output_budget'):
        m.command([sys.executable, '-c', 'import os; chunk=b"x"*65536\nwhile True: os.write(1,chunk)'])
    children = []
    real_popen = m.subprocess.Popen

    def popen(argv, **kwargs):
        child = real_popen(argv, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    with pytest.raises(m.Refused, match='command_deadline'):
        with m.io_budget(0.1, m.Clock()):
            m.command([sys.executable, '-c', 'import time; time.sleep(10)'])
    assert children[0].poll() is not None


def test_journal_baseline_tamper_and_permissions_refuse(harness):
    controller, *_ = harness
    state = controller.journal.read()
    state['baseline']['share'] = 0.5
    controller.journal.save(state)
    with pytest.raises(m.Refused, match='baseline_changed'):
        controller.load()
    os.chmod(controller.journal.path, 0o644)
    with pytest.raises(m.Refused, match='unsafe_journal'):
        controller.journal.read()


def test_cli_never_echoes_bad_arguments_or_provider_text(capsys, monkeypatch):
    assert c.main(['prepare', '--token=private-credential']) == 1
    assert 'private-credential' not in capsys.readouterr().err

    def failing(*_args, **_kwargs):
        raise RuntimeError('token=private-credential')

    monkeypatch.setattr(c.Journal, '__enter__', failing)
    assert c.main(['rollback', '--state', '/fake/path']) == 1
    assert 'private-credential' not in capsys.readouterr().err


def test_transport_rejects_untrusted_origin_without_reading_token():
    transport = m.Transport()
    with pytest.raises(m.Refused):
        transport.request('GET', 'https://evil.test/')
    assert transport._token is None


def test_json_nonfinite_and_duplicate_keys_refuse():
    for raw in (b'{"x": NaN}', b'{"x": 1, "x": 2}', b'[]'):
        with pytest.raises(m.Refused):
            m.decode(raw)


def test_failed_candidate_still_allows_retained_ready_revision_rollback(harness):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    controller.move(25)
    cloud.services[c.SERVICE]['status']['conditions'][0]['status'] = 'False'
    cloud.revisions[controller.state['candidate']]['status']['conditions'][0]['status'] = 'False'
    controller.rollback()
    assert controller.state['phase'] == 'rolled_back'
    assert c.traffic(cloud.services[c.SERVICE]['status']['traffic']) == {c.ROLLBACK: 100}
    count = len(cloud.writes)
    controller.rollback()
    assert len(cloud.writes) == count


@pytest.mark.parametrize('mode', ['lost_before', 'lost_after'])
def test_uncertain_promotion_can_be_compensated_without_replay(harness, mode):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    cloud.mode = mode
    with pytest.raises(TimeoutError):
        controller.move(25)
    cloud.mode = None
    if mode == 'lost_after':
        controller.rollback()
        assert c.traffic(cloud.services[c.SERVICE]['status']['traffic']) == {c.ROLLBACK: 100}
        assert len(cloud.writes) == 3
    else:
        with pytest.raises(m.Refused, match='unsettled_promotion_refused'):
            controller.rollback()
        assert controller.journal.read()['intent']['kind'] == 'traffic_25'
        assert len(cloud.writes) == 2


@pytest.mark.parametrize('mode', ['lost_before', 'lost_after'])
def test_uncertain_rollback_never_blindly_retries(harness, mode):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    controller.move(25)
    cloud.mode = mode
    with pytest.raises(TimeoutError):
        controller.rollback()
    assert len(cloud.writes) == 3
    cloud.mode = None
    if mode == 'lost_after':
        controller.rollback()  # Read-only verification of an already landed rollback.
        assert controller.state['phase'] == 'rolled_back'
    else:
        with pytest.raises(m.Refused, match='uncertain_rollback_refused'):
            controller.rollback()
    assert len(cloud.writes) == 3


def test_foreign_generation_refuses_even_if_spec_was_reverted(harness):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    controller.move(25)
    doc = cloud.services[c.SERVICE]
    doc['metadata']['generation'] += 2
    doc['status']['observedGeneration'] += 2
    with pytest.raises(m.Refused, match='rollback_foreign_generation'):
        controller.rollback()
    with pytest.raises(m.Refused, match='foreign_generation'):
        controller.move(100)


def test_actual_zero_percent_tag_binding_must_match_requested(harness):
    controller, cloud, _transport, _clock, _runtime = make_candidate(harness)
    cloud.services[c.SERVICE]['status']['traffic'][-1]['revisionName'] = 'foreign-revision'
    with pytest.raises(m.Refused, match='actual_tag_drift'):
        controller.promote()
    assert len(cloud.writes) == 1


@pytest.mark.parametrize('bad', [None, '', {}, False])
def test_malformed_execution_errors_refuse_on_any_page(harness, bad):
    controller, _cloud, transport, _clock, _runtime = harness
    transport.page_hook = lambda _params, doc: doc | {'executionErrors': bad}
    with pytest.raises(m.Refused, match='metric_page_error'):
        controller.metrics.collect()


def test_monitoring_collection_has_total_deadline(harness):
    controller, _cloud, transport, clock, _runtime = harness

    def slow(_params, doc):
        clock.sleep(31)
        return doc

    transport.page_hook = slow
    with pytest.raises(m.Refused, match='metric_collection_deadline'):
        controller.metrics.collect()


def test_registry_commit_tag_fallback_native_same_tree_policy(harness, monkeypatch):
    controller, _cloud, transport, _clock, _runtime = harness
    previous = 'a' * 40
    config = reply({'config': {}})
    config_digest = c.digest_bytes(config.raw)
    manifest = reply({'schemaVersion': 2, 'config': {'digest': config_digest}})
    image = 'gcr.io/based-hardware/backend@' + c.digest_bytes(manifest.raw)
    transport.config, transport.manifest, transport.image = config, manifest, image
    original_request = transport.request

    def registry_request(method, url, **kwargs):
        if url.endswith('/tags/list'):
            return reply({'manifest': {image.split('@')[1]: {'tag': [c.SOURCE[:7], previous[:7]]}}})
        return original_request(method, url, **kwargs)

    monkeypatch.setattr(transport, 'request', registry_request)

    def git(argv):
        assert argv[0] == 'git'
        if argv[1] == 'merge-base':
            assert argv[-2:] == [previous, c.SOURCE]
            return ''
        ref = argv[-1]
        if ref.endswith('^{tree}'):
            return 'same-tree'
        return c.SOURCE if ref.startswith(c.SOURCE[:7]) else previous

    monkeypatch.setattr(c, 'command', git)
    assert controller.registry.verify(image, c.SOURCE) == image

    def different_tree(argv):
        if argv[-1] == previous + '^{tree}':
            return 'different-tree'
        return git(argv)

    monkeypatch.setattr(c, 'command', different_tree)
    with pytest.raises(m.Refused, match='registry_commit_tags_ambiguous'):
        controller.registry.verify(image, c.SOURCE)


@pytest.mark.parametrize('kind', ['source', 'role', 'digest', 'host'])
def test_role_image_source_and_config_are_proved(harness, kind):
    controller, _cloud, transport, _clock, _runtime = harness
    config = {'Labels': {'org.opencontainers.image.revision': c.SOURCE}, 'Env': ['OMI_ROLE=workers']}
    if kind == 'source':
        config['Labels']['org.opencontainers.image.revision'] = 'f' * 40
    elif kind == 'role':
        config['Env'] = ['OMI_ROLE=api']
    transport.config = reply({'config': config})
    transport.manifest = reply({'schemaVersion': 2, 'config': {'digest': c.digest_bytes(transport.config.raw)}})
    image = 'gcr.io/based-hardware/backend-workers@' + c.digest_bytes(transport.manifest.raw)
    if kind == 'digest':
        image = image.split('@')[0] + '@sha256:' + 'a' * 64
    if kind == 'host':
        image = image.replace('gcr.io', 'evil.test')
    with pytest.raises(m.Refused):
        controller.registry.verify(image, c.SOURCE)


class HttpSocket:
    def settimeout(self, _timeout):
        pass


def test_real_transport_authentication_redirect_and_byte_bounds(monkeypatch):
    calls = []
    statuses = [302]
    location = 'https://evil.test/private'
    body = b'{"secret-provider-body":"private-token"}'

    class Response:
        def __init__(self):
            self.status = statuses.pop(0)
            self.payload = body

        def getheader(self, name, default=None):
            return location if name == 'Location' else default

        def getheaders(self):
            return []

        def read1(self, size):
            chunk, self.payload = self.payload[:size], self.payload[size:]
            return chunk

    class Connection:
        def __init__(self, host, timeout):
            assert 0 < timeout <= 10
            self.host, self.sock = host, HttpSocket()

        def request(self, method, path, body, headers):
            assert headers['Authorization'] == 'Bearer private-token'
            calls.append((method, self.host, path))

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(m.http.client, 'HTTPSConnection', Connection)
    transport = m.Transport()
    transport._token = 'private-token'
    with pytest.raises(m.Refused):
        transport.request('GET', 'https://monitoring.googleapis.com/v3/projects/based-hardware/timeSeries')
    assert len(calls) == 1  # Monitoring does not follow redirects, including Google URLs.
    statuses[:] = [302]
    with pytest.raises(m.Refused):
        transport.request('GET', 'https://gcr.io/v2/based-hardware/backend/blobs/sha256:x', registry_blob=True)
    assert len(calls) == 2  # Registry redirect may never leak bearer auth to a foreign host.
    statuses[:] = [302]
    location = 'https://storage.googleapis.com/registry/config'
    body = b'{"config":{}}'
    with pytest.raises(m.Refused):
        transport.request('GET', 'https://gcr.io/v2/based-hardware/backend/blobs/sha256:x', registry_blob=True)
    assert len(calls) == 3  # Even a Google storage target never receives bearer credentials.
    statuses[:] = [200]
    monkeypatch.setattr(m, 'MAX_BYTES', 8)
    with pytest.raises(m.Refused):
        transport.request('GET', 'https://monitoring.googleapis.com/v3/projects/based-hardware/timeSeries')


def test_journal_lock_and_symlink_are_rejected(tmp_path):
    path = tmp_path / 'state'
    with c.Journal(path):
        with pytest.raises(m.Refused, match='journal_busy'):
            with c.Journal(path):
                pytest.fail('concurrent lock admitted')
    real = tmp_path / 'real'
    real.write_text('{}')
    real.chmod(0o600)
    path.symlink_to(real)
    with pytest.raises(OSError):
        c.Journal(path).read()
