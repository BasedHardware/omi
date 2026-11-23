"""Exercise the selected promotion state machine without Cloud Run writes."""

import copy
import json
import re
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import promote_selected_backend as promotion

OLD = 'backend-prior'
NEW = 'backend-candidate'
OPERATION = f'projects/{promotion.PROJECT}/locations/{promotion.REGION}/operations/operation-1'


class Clock:
    elapsed = 0.0

    def time(self):
        return 1_800_000_000 + self.elapsed

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


class FakeCloud:
    def __init__(self, scenario, clock):
        self.scenario = scenario
        self.clock = clock
        self.metric_batch = None
        self.batches = 0
        if scenario in ('delayed', 'late', 'retry'):
            self.metric_batch = Barrier(8, action=self.finish_batch)
        if scenario == 'baseline_boundary':
            clock.sleep(29)
            self.metric_batch = Barrier(4, action=self.finish_batch)
        self.generation = 1
        self.writes = []
        self.polls = 0
        self.reads = 0
        self.traffic = [
            {'type': promotion.REVISION, 'revision': OLD, 'tag': 'stable', 'percent': 100},
            {'type': promotion.LATEST, 'tag': 'latest-probe'},
        ]

    def finish_batch(self):
        self.batches += 1
        self.clock.sleep(11 if self.scenario == 'late' else 9)

    def service(self):
        observed = copy.deepcopy(self.traffic)
        for row in observed:
            if row['type'] == promotion.LATEST:
                row['revision'] = NEW
        if self.writes and self.scenario == 'wrong_weight':
            observed[0]['percent'] = 11
            observed[1]['percent'] = 89
        return {
            'name': promotion.SERVICE,
            'uid': 'service-uid',
            'generation': str(self.generation),
            'observedGeneration': str(self.generation),
            'etag': f'etag-{self.generation}',
            'latestCreatedRevision': f'{promotion.SERVICE}/revisions/{NEW}',
            'latestReadyRevision': f'{promotion.SERVICE}/revisions/{NEW}',
            'terminalCondition': {'state': 'CONDITION_SUCCEEDED'},
            'traffic': copy.deepcopy(self.traffic),
            'trafficStatuses': observed,
        }

    def request(self, method, url, body=None, deadline=None):
        assert deadline is not None
        if url == promotion.RUN_API + promotion.SERVICE:
            assert method == 'GET'
            self.reads += 1
            if self.scenario == 'foreign_generation' and self.reads == 4:
                self.generation += 1
            doc = self.service()
        elif url == promotion.RUN_API + promotion.SERVICE + '?updateMask=traffic':
            assert method == 'PATCH'
            assert set(body) == {'etag', 'traffic'}
            assert body['etag'] == f'etag-{self.generation}'
            routing_delay = {'retry': 55, 'delayed': 15, 'late': 15, 'routing_timeout': 121}
            self.clock.sleep(routing_delay.get(self.scenario, 0))
            self.writes.append(copy.deepcopy(body))
            self.traffic = body['traffic']
            self.generation += 1
            if self.scenario == 'cancel':
                raise SystemExit(143)
            doc = {'name': OPERATION}
        elif url == promotion.RUN_API + OPERATION:
            assert method == 'GET'
            self.polls += 1
            doc = {'done': True, 'response': {}}
            if self.scenario == 'operation_failure':
                doc = {'done': True, 'error': {'code': 9}}
        else:
            assert method == 'GET'
            if self.metric_batch and bool(self.writes) != (self.scenario == 'baseline_boundary'):
                self.metric_batch.wait(timeout=2)
            query = parse_qs(urlsplit(url).query)
            metric = re.search(
                r'metric\.type="(?:run\.googleapis\.com/|loadbalancing\.googleapis\.com/https/)([^"]+)"',
                query['filter'][0],
            )[1]
            candidate = f'revision_name="{NEW}"' in query['filter'][0]
            ingress = 'resource.type="https_lb_rule"' in query['filter'][0]
            if ingress:
                assert f'backend_target_name="{promotion.INGRESS_BACKEND}"' in query['filter'][0]
            doc = self.metrics(query, metric, candidate, ingress)
        return SimpleNamespace(doc=doc)

    def metrics(self, query, metric, candidate, ingress):
        end = query['interval.endTime'][0]
        if candidate and self.scenario == 'missing':
            return {}
        if candidate and self.scenario == 'retry' and self.batches == 1 and metric == 'request_count':
            return {}
        if candidate and self.scenario == 'stale':
            end = '2026-11-22T16:00:00Z'
        if ingress and self.writes and self.scenario == 'missing_ingress':
            return {}
        labels = {}
        if metric == 'container/startup_latencies':
            if not candidate or self.scenario != 'pass':
                return {}
            value = {'distributionValue': {'count': '3', 'mean': 240}}
        elif metric == 'request_count':
            if ingress:
                error_codes = {'ingress_error': '503', 'ingress_throttled': '429', 'ingress_no_response': '0'}
                labels['response_code'] = error_codes.get(self.scenario, '200') if self.writes else '200'
            else:
                labels['response_code_class'] = '5xx' if candidate and self.scenario == 'unhealthy' else '2xx'
            value = {'int64Value': '500'}
        elif metric in ('request_latencies', 'total_latencies'):
            value = {'doubleValue': 5000 if ingress and self.writes and self.scenario == 'ingress_slow' else 100}
        else:
            assert metric == 'container/instance_count'
            value = {'int64Value': '8'}
        return {
            'timeSeries': [{'metric': {'labels': labels}, 'points': [{'interval': {'endTime': end}, 'value': value}]}]
        }


def controller(tmp_path, monkeypatch, scenario, *, scope='backend'):
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    snapshot = tmp_path / 'snapshot.json'
    traffic = [{'revisionName': OLD, 'percent': 100}]
    snapshot.write_text(
        json.dumps(
            {
                'schema_version': promotion.SNAPSHOT_SCHEMA_VERSION,
                'project': promotion.PROJECT,
                'region': promotion.REGION,
                'services': {
                    'backend': {
                        'spec': {'traffic': traffic},
                        'status': {
                            'traffic': traffic,
                            'latestReadyRevisionName': NEW,
                            'latestCreatedRevisionName': NEW,
                        },
                    }
                },
                'missing_services': [],
            }
        )
    )
    if scope == 'all':
        doc = json.loads(snapshot.read_text())
        for service in promotion.DEFAULT_SERVICES[1:]:
            doc['services'][service] = {'service': service}
        snapshot.write_text(json.dumps(doc))
    args = SimpleNamespace(
        candidate=NEW,
        inverse=OLD if scope == 'backend' else None,
        scope=scope,
        source='a' * 40,
        control='b' * 40,
        snapshot=snapshot,
        receipt=tmp_path / 'receipt.json',
    )
    clock = Clock()
    return promotion.Promotion(FakeCloud(scenario, clock), clock, args)


def test_promote_records_verified_stages_and_total_duration(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'pass')
    rollout.run()

    receipt = json.loads(rollout.path.read_text())
    assert receipt['outcome'] == 'promoted'
    assert receipt['promotion_elapsed_seconds'] == rollout.clock.elapsed
    assert receipt['promotion_elapsed_seconds'] > 3 * promotion.METRIC_LAG
    assert [row['weights'][NEW] for row in receipt['stages']] == [10, 50, 90, 100]
    assert [row['generation'] for row in receipt['stages']] == ['2', '3', '4', '5']
    assert [row['candidate_health']['active_instances'] for row in receipt['stages'][:-1]] == [8, 8, 8]
    assert [row['candidate_health']['startup_count'] for row in receipt['stages'][:-1]] == [3, 3, 3]
    assert [row['candidate_health']['startup_mean_ms'] for row in receipt['stages'][:-1]] == [240, 240, 240]
    assert all('ingress_health' in row for row in receipt['stages'][:-1])
    assert receipt['stages'][-1]['weights'] == {NEW: 100}
    assert rollout.transport.polls == 4
    for patch in rollout.transport.writes:
        assert {'type': promotion.REVISION, 'revision': OLD, 'tag': 'stable'} in patch['traffic']
        assert {'type': promotion.LATEST, 'tag': 'latest-probe'} in patch['traffic']


@pytest.mark.parametrize(
    ('scenario', 'error'),
    [
        ('missing', 'stage_deadline'),
        ('stale', 'stale_metric_bucket'),
        ('unhealthy', 'stage_error_regression'),
        ('missing_ingress', 'stage_deadline'),
        ('ingress_error', 'ingress_error_regression'),
        ('ingress_throttled', 'ingress_error_regression'),
        ('ingress_no_response', 'ingress_error_regression'),
        ('ingress_slow', 'ingress_latency_regression'),
        ('foreign_generation', 'generation_drift'),
        ('wrong_weight', 'observed_traffic_drift'),
        ('operation_failure', 'traffic_operation_failed'),
    ],
)
def test_stage_refusals_do_not_advance_or_retry_a_write(tmp_path, monkeypatch, scenario, error):
    rollout = controller(tmp_path, monkeypatch, scenario)
    with pytest.raises(promotion.Refused, match=error):
        rollout.run()

    assert len(rollout.transport.writes) == 1
    receipt = json.loads(rollout.path.read_text())
    assert receipt['outcome'] == 'refused'
    assert receipt['reason'] == error
    assert [row['weights'][NEW] for row in receipt['stages']] == [10]
    assert receipt['promotion_elapsed_seconds'] <= promotion.STAGE_SECONDS


def test_slow_healthy_metrics_fit_under_stage_deadline(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'delayed')
    rollout.run()

    receipt = json.loads(rollout.path.read_text())
    assert receipt['outcome'] == 'promoted'
    # First bucket is ready at 330s. Eight serial 9s calls would miss 360s.
    assert receipt['stages'][0]['health_verified_at'] == promotion.iso(1_800_000_339)
    assert [row['weights'][NEW] for row in receipt['stages']] == [10, 50, 90, 100]


def test_metric_collection_timeout_cannot_advance_stage(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'late')
    with pytest.raises(promotion.Refused, match='io_deadline'):
        rollout.run()

    assert len(rollout.transport.writes) == 1
    receipt = json.loads(rollout.path.read_text())
    assert receipt['outcome'] == 'refused'
    assert 'health_verified_at' not in receipt['stages'][0]


def test_aligned_convergence_and_one_missing_sample_fit_with_slow_reads(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'retry')
    rollout.run()

    receipt = json.loads(rollout.path.read_text())
    first = receipt['stages'][0]
    assert first['verified_at'] == promotion.iso(1_800_000_060)
    assert first['health_verified_at'] == promotion.iso(1_800_000_413)
    assert rollout.transport.batches == 4
    assert receipt['outcome'] == 'promoted'


def test_routing_has_its_own_deadline(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'routing_timeout')
    with pytest.raises(promotion.Refused, match='io_deadline'):
        rollout.run()
    assert len(rollout.transport.writes) == 1
    assert rollout.transport.polls == 0


def test_baseline_selected_before_minute_boundary_survives_collection(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'baseline_boundary')
    rollout.run()

    receipt = json.loads(rollout.path.read_text())
    assert receipt['baseline']['sample_end'] == promotion.iso(1_799_999_760)
    assert receipt['outcome'] == 'promoted'


def test_all_service_scope_uses_exact_backend_inverse_from_snapshot(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'pass', scope='all')
    rollout.run()

    receipt = json.loads(rollout.path.read_text())
    assert receipt['scope'] == 'all'
    assert receipt['inverse'] == OLD
    assert [row['weights'][NEW] for row in receipt['stages']] == [10, 50, 90, 100]


def test_all_service_scope_refuses_disagreeing_backend_snapshot_before_write(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'pass', scope='all')
    doc = json.loads(rollout.snapshot.read_text())
    doc['services']['backend']['spec']['traffic'][0]['revisionName'] = 'backend-other'
    rollout.snapshot.write_text(json.dumps(doc))

    with pytest.raises(promotion.Refused, match='snapshot_inverse_mismatch'):
        rollout.run()
    assert not rollout.transport.writes


def test_unreadable_snapshot_is_a_refusal(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'pass')
    rollout.snapshot.unlink()
    with pytest.raises(promotion.Refused, match='snapshot_unreadable'):
        rollout.run()
    receipt = json.loads(rollout.path.read_text())
    assert (receipt['outcome'], receipt['reason']) == ('refused', 'snapshot_unreadable')
    assert not rollout.transport.writes


def test_live_v2_requested_and_observed_traffic_row_shape():
    row = {
        'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION',
        'revision': 'backend-0fb4972-45146075887-1',
        'percent': 100,
    }
    for field in ('traffic', 'trafficStatuses'):
        service = {field: [row]}
        assert promotion.routing(service[field]) == ({'backend-0fb4972-45146075887-1': 100}, {})


def test_cancellation_records_unverified_intent_without_advancing(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'cancel')
    with pytest.raises(SystemExit) as exc:
        rollout.run()

    assert exc.value.code == 143
    assert len(rollout.transport.writes) == 1
    receipt = json.loads(rollout.path.read_text())
    assert receipt['outcome'] == 'interrupted_or_failed'
    assert 'verified_at' not in receipt['stages'][0]


def test_live_traffic_must_match_the_captured_inverse_before_any_write(tmp_path, monkeypatch):
    rollout = controller(tmp_path, monkeypatch, 'pass')
    rollout.transport.traffic[0]['revision'] = 'backend-other'
    with pytest.raises(promotion.Refused, match='requested_traffic_drift'):
        rollout.run()
    assert rollout.transport.writes == []


def test_workflow_keeps_staged_failures_and_cancellation_on_the_snapshot_restore_path():
    path = Path(__file__).resolve().parents[3] / '.github/actions/deploy-backend-stack/action.yml'
    workflow = path.read_text()
    shift = workflow.split('id: shift-cloud-run-traffic\n', 1)[1].split('    - name:', 1)[0]
    assert '--snapshot artifacts/backend-cloud-run-pre-promotion-traffic-snapshot.json' in shift
    assert 'python3 "$DEPLOY_CONTROL_SCRIPTS/promote_selected_backend.py"' in shift
    assert '== manual &&' in shift and '== prod ]]' in shift and '== backend ]]' in shift
    restore = workflow.split('    - name: Restore Cloud Run traffic snapshot after failed promotion')[-1]
    assert "steps.shift-cloud-run-traffic.outcome == 'failure'" in restore
    assert "steps.shift-cloud-run-traffic.outcome == 'cancelled'" in restore
    assert 'artifacts/backend-promotion-stages.json' in workflow
