"""Stage selected production backend traffic and emit rollout evidence.

The workflow owns the lock, candidate, snapshot and rollback. This controller
writes only an etag-bound Cloud Run traffic patch and never retries a write.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

if __package__:
    from .cloud_run_traffic_snapshot import DEFAULT_SERVICES, SNAPSHOT_SCHEMA_VERSION, restore_targets
    from .integration_canary_metrics import (
        PROJECT,
        REGION,
        Clock,
        Refused,
        Transport,
        io_budget,
        iso,
        require,
    )
else:
    from cloud_run_traffic_snapshot import DEFAULT_SERVICES, SNAPSHOT_SCHEMA_VERSION, restore_targets
    from integration_canary_metrics import (
        PROJECT,
        REGION,
        Clock,
        Refused,
        Transport,
        io_budget,
        iso,
        require,
    )

RUN_API = 'https://us-central1-run.googleapis.com/v2/'
SERVICE = f'projects/{PROJECT}/locations/{REGION}/services/backend'
MONITORING = f'https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries'
REVISION = 'TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION'
LATEST = 'TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST'
REVISION_NAME = re.compile(r'backend-[a-z0-9](?:[a-z0-9-]{0,53}[a-z0-9])?')
STAGES = (10, 50, 90, 100)
ROUTING_SECONDS = 120
STAGE_SECONDS = 360
BASELINE_SECONDS = 60
# Reserve time for sibling moves, serving verification, smoke and snapshot restore.
WORKFLOW_TAIL_SECONDS = 18 * 60
# Global external load-balancer metrics can take 210 seconds to publish.
METRIC_LAG = 210
METRIC_COLLECTION_SECONDS = 10
MISSING_SAMPLE_RETRY_SECONDS = 5
INGRESS_BACKEND = 'custom-domains-api-omi-me-backend-49a4-be'


def routing(rows, latest=None):
    weights, tags = {}, {}
    require(isinstance(rows, list) and bool(rows), 'traffic_missing')
    for row in rows:
        percent = row.get('percent', 0)
        require(type(percent) is int and 0 <= percent <= 100, 'traffic_weight_invalid')
        kind = row.get('type')
        require(kind in (LATEST, REVISION), 'traffic_target_type_invalid')
        revision = (latest or row.get('revision')) if kind == LATEST else row.get('revision')
        require(
            isinstance(revision, str) and bool(re.fullmatch(r'backend-[a-z0-9-]+', revision)), 'traffic_target_invalid'
        )
        if percent:
            weights[revision] = weights.get(revision, 0) + percent
        if 'tag' in row:
            tag = row['tag']
            require(isinstance(tag, str) and tag and tag not in tags, 'traffic_tag_invalid')
            tags[tag] = revision
    require(sum(weights.values()) == 100, 'traffic_total_invalid')
    return weights, tags


def tag_targets(rows):
    return {
        row['tag']: (row['type'], row['revision'] if row['type'] == REVISION else None) for row in rows if 'tag' in row
    }


def verify_service(doc, candidate, inverse, expected, tags, uid=None, generation=None):
    require(doc.get('name') == SERVICE and bool(doc.get('uid')), 'service_identity_invalid')
    require(uid is None or doc['uid'] == uid, 'service_replaced')
    actual_generation = doc.get('generation', '')
    require(isinstance(actual_generation, str) and actual_generation.isdigit(), 'generation_missing')
    require(generation is None or actual_generation == generation, 'generation_drift')
    require(actual_generation == doc.get('observedGeneration') and not doc.get('reconciling'), 'generation_unobserved')
    require(doc.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED', 'service_not_ready')
    require(isinstance(doc.get('etag'), str) and bool(doc['etag']), 'etag_missing')
    prefix = f'{SERVICE}/revisions/'
    latest_ready = doc.get('latestReadyRevision')
    require(
        doc.get('latestCreatedRevision') == prefix + candidate
        and latest_ready in (prefix + candidate, prefix + inverse),
        'candidate_not_latest_ready',
    )
    latest = latest_ready.removeprefix(prefix)
    desired = doc.get('traffic')
    weights, resolved_tags = routing(desired, latest)
    current_tags = tag_targets(desired)
    require(weights == expected and (tags is None or current_tags == tags), 'requested_traffic_drift')
    require(routing(doc.get('trafficStatuses')) == (expected, resolved_tags), 'observed_traffic_drift')
    return latest, current_tags


def verify_snapshot(path, candidate, inverse, scope):
    try:
        snapshot = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Refused('snapshot_unreadable') from None
    services = snapshot.get('services') if isinstance(snapshot, dict) else None
    expected_services = set(DEFAULT_SERVICES) if scope == 'all' else {'backend'}
    require(
        isinstance(services, dict)
        and snapshot.get('schema_version') == SNAPSHOT_SCHEMA_VERSION
        and snapshot.get('project') == PROJECT
        and snapshot.get('region') == REGION
        and services.keys() == expected_services
        and snapshot.get('missing_services') == [],
        'snapshot_scope_invalid',
    )
    backend = services['backend']
    try:
        requested = restore_targets(backend, traffic_source='spec')
        observed_targets = restore_targets(backend, traffic_source='status')
    except (AttributeError, ValueError):
        raise Refused('snapshot_inverse_mismatch') from None
    if scope == 'all':
        require(inverse is None and len(observed_targets) == 1, 'snapshot_inverse_mismatch')
        inverse = observed_targets[0][0]
    require(isinstance(inverse, str) and bool(REVISION_NAME.fullmatch(inverse)), 'invalid_inverse')
    require(inverse != candidate, 'candidate_equals_inverse')
    require(requested == observed_targets == [(inverse, 100)], 'snapshot_inverse_mismatch')
    observed = backend['status']
    require(
        observed.get('latestCreatedRevisionName') == candidate
        and observed.get('latestReadyRevisionName') in (candidate, inverse),
        'snapshot_candidate_mismatch',
    )
    return inverse


class MissingSample(Refused):
    """A complete sample has not been published yet."""


class Promotion:
    def __init__(self, transport, clock, args):
        self.transport = transport
        self.clock = clock
        self.candidate = args.candidate
        self.inverse = args.inverse
        self.scope = args.scope
        self.path = args.receipt
        self.start = clock.monotonic()
        self.workflow_deadline = args.workflow_started + args.workflow_timeout_minutes * 60
        self.receipt = {
            'schema': 1,
            'service': 'backend',
            'scope': self.scope,
            'source': args.source,
            'control': args.control,
            'run_id': int(os.environ['GITHUB_RUN_ID']),
            'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
            'candidate': self.candidate,
            'inverse': self.inverse,
            'started_at': iso(clock.time()),
            'stages': [],
        }
        self.snapshot = args.snapshot

    def record(self):
        self.receipt['promotion_elapsed_seconds'] = round(self.clock.monotonic() - self.start, 3)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.receipt, sort_keys=True, allow_nan=False) + '\n')
        temporary.replace(self.path)

    def request(self, method, url, deadline, body=None):
        with io_budget(deadline - self.clock.monotonic(), self.clock):
            return self.transport.request(method, url, body=body, deadline=deadline).doc

    def service(self, deadline):
        return self.request('GET', RUN_API + SERVICE, deadline)

    def verify_candidate_revision(self, deadline):
        name = f'{SERVICE}/revisions/{self.candidate}'
        revision = self.request('GET', RUN_API + name, deadline)
        require(revision.get('name') == name, 'candidate_revision_identity_invalid')
        ready = [
            condition.get('state') for condition in revision.get('conditions', []) if condition.get('type') == 'Ready'
        ]
        require(ready == ['CONDITION_SUCCEEDED'], 'candidate_revision_not_ready')

    def pause(self, seconds, deadline):
        require(self.clock.monotonic() + seconds < deadline, 'stage_deadline')
        self.clock.sleep(seconds)

    def move(self, current, weights, tags, deadline):
        traffic = [{'type': REVISION, 'revision': rev, 'percent': weight} for rev, weight in weights.items()]
        for tag, (kind, revision) in tags.items():
            alias = {'type': kind, 'tag': tag}
            if revision is not None:
                alias['revision'] = revision
            traffic.append(alias)
        operation = self.request(
            'PATCH', RUN_API + SERVICE + '?updateMask=traffic', deadline, {'etag': current['etag'], 'traffic': traffic}
        )
        name = operation.get('name', '')
        require(
            isinstance(name, str)
            and bool(
                re.fullmatch(
                    r'projects/(?:based-hardware|[0-9]+)/locations/us-central1/operations/[a-zA-Z0-9_-]+', name
                )
            ),
            'operation_name_invalid',
        )
        while operation.get('done') is not True:
            self.pause(5, deadline)
            operation = self.request('GET', RUN_API + name, deadline)
        require('error' not in operation and isinstance(operation.get('response'), dict), 'traffic_operation_failed')
        landed = self.service(deadline)
        latest, _ = verify_service(
            landed, self.candidate, self.inverse, weights, tags, current['uid'], str(int(current['generation']) + 1)
        )
        # The aggregate can lag even after the exact traffic vector has converged.
        # The workflow's final serving-vector check still requires it to advance.
        if latest == self.inverse:
            self.verify_candidate_revision(deadline)
        return landed

    def metric(self, revision, metric, end, deadline):
        if revision is None:
            metric_filter = (
                f'metric.type="loadbalancing.googleapis.com/https/{metric}" AND resource.type="https_lb_rule"'
                f' AND resource.labels.project_id="{PROJECT}" AND resource.labels.backend_target_name="{INGRESS_BACKEND}"'
            )
        else:
            metric_filter = (
                f'metric.type="run.googleapis.com/{metric}" AND resource.type="cloud_run_revision"'
                f' AND resource.labels.project_id="{PROJECT}" AND resource.labels.location="{REGION}"'
                f' AND resource.labels.service_name="backend" AND resource.labels.revision_name="{revision}"'
            )
        params = {
            'filter': metric_filter,
            'interval.startTime': iso(end - 60),
            'interval.endTime': iso(end),
            'aggregation.alignmentPeriod': '60s',
            'aggregation.perSeriesAligner': 'ALIGN_SUM',
            'aggregation.crossSeriesReducer': 'REDUCE_SUM',
        }
        code_label = 'response_code' if revision is None else 'response_code_class'
        if metric == 'request_count':
            params['aggregation.groupByFields'] = f'metric.labels.{code_label}'
        if metric in ('request_latencies', 'total_latencies'):
            params['secondaryAggregation.alignmentPeriod'] = '60s'
            params['secondaryAggregation.perSeriesAligner'] = 'ALIGN_PERCENTILE_95'
        if metric == 'container/instance_count':
            params['filter'] += ' AND metric.labels.state="active"'
            params['aggregation.perSeriesAligner'] = 'ALIGN_MAX'
        page = self.request('GET', MONITORING + '?' + urlencode(params), deadline)
        require(
            not any(page.get(field) for field in ('error', 'executionErrors', 'unreachable', 'nextPageToken')),
            'metric_response_incomplete',
        )
        result = {}
        for series in page.get('timeSeries', []):
            label = series.get('metric', {}).get('labels', {}).get(code_label, '')
            require(label not in result, 'duplicate_metric_series')
            points = series['points']
            require(len(points) == 1, 'invalid_metric_bucket')
            point = points[0]
            require(point['interval']['endTime'] == iso(end), 'stale_metric_bucket')
            result[label] = point['value']
        return result

    def collect_health(self, revisions, end, deadline, *, include_capacity=False):
        metrics = {
            revision: ('request_count', 'total_latencies' if revision is None else 'request_latencies')
            for revision in revisions
        }
        if include_capacity:
            metrics[self.candidate] += ('container/instance_count', 'container/startup_latencies')

        # Each read has its own connection and shares one absolute collection
        # deadline. The earlier service read has already initialized the token.
        deadline = min(deadline, self.clock.monotonic() + METRIC_COLLECTION_SECONDS)
        require(self.clock.monotonic() < deadline, 'stage_deadline')
        with ThreadPoolExecutor(max_workers=sum(map(len, metrics.values()))) as pool:
            pending = {
                revision: {name: pool.submit(self.metric, revision, name, end, deadline) for name in names}
                for revision, names in metrics.items()
            }
            # Resolve all reads before checking availability so an absent sample
            # cannot hide stale or malformed evidence from a different metric.
            evidence = {
                revision: {name: future.result() for name, future in reads.items()}
                for revision, reads in pending.items()
            }
        require(self.clock.monotonic() <= deadline, 'metric_collection_deadline')
        return [self.health(revision, evidence[revision]) for revision in revisions]

    @staticmethod
    def health(revision, metrics):
        counts = metrics['request_count']
        latencies = metrics['total_latencies' if revision is None else 'request_latencies']
        if not counts or not latencies:
            raise MissingSample('missing_request_evidence')
        if revision is None:
            require(all(re.fullmatch(r'0|[1-5][0-9]{2}', code) for code in counts), 'invalid_ingress_response_code')
            error_codes = [code for code in counts if code in ('0', '429') or code.startswith('5')]
        else:
            require(set(counts) <= {'1xx', '2xx', '3xx', '4xx', '5xx'}, 'invalid_response_class')
            error_codes = ['5xx']
        requests = {key: int(value['int64Value']) for key, value in counts.items()}
        total = sum(requests.values())
        require(total > 0 and min(requests.values()) >= 0, 'invalid_request_count')
        p95 = latencies['']['doubleValue']
        require(type(p95) in (int, float) and 0 <= p95 and math.isfinite(p95), 'invalid_request_latency')
        sample = {'requests': total, 'errors': sum(requests.get(code, 0) for code in error_codes), 'p95_ms': p95}
        if 'container/instance_count' in metrics:
            instances = metrics['container/instance_count']
            if not instances:
                raise MissingSample('missing_instance_evidence')
            require(int(instances['']['int64Value']) > 0, 'no_active_candidate_instances')
            sample['active_instances'] = int(instances['']['int64Value'])
            startup = metrics['container/startup_latencies']
            if startup:
                distribution = startup['']['distributionValue']
                sample['startup_count'] = int(distribution.get('count', 0))
                sample['startup_mean_ms'] = distribution.get('mean')
            else:
                # No latency point is expected when no instance starts complete in this bucket.
                sample['startup_count'] = None
        return sample

    @staticmethod
    def check_health(sample, reference, scope='stage'):
        rate = sample['errors'] / sample['requests']
        reference_rate = reference['errors'] / reference['requests']
        require(rate <= max(0.01, 2 * reference_rate + 0.001), f'{scope}_error_regression')
        require(sample['p95_ms'] <= max(1000, 2 * reference['p95_ms']), f'{scope}_latency_regression')

    def guard(self, row, convergence, baseline, ingress_baseline, deadline):
        # The entire bucket starts after convergence. Re-read only absent samples
        # within the stage deadline, and never substitute an older bucket.
        first_end = (int(convergence // 60) + 2) * 60
        while True:
            end = max(first_end, int((self.clock.time() - METRIC_LAG) // 60) * 60)
            delay = end + METRIC_LAG - self.clock.time()
            if delay > 0:
                self.pause(delay, deadline)
            try:
                candidate, inverse, ingress = self.collect_health(
                    (self.candidate, self.inverse, None), end, deadline, include_capacity=True
                )
            except MissingSample:
                self.pause(MISSING_SAMPLE_RETRY_SECONDS, deadline)
                continue
            break
        require(METRIC_LAG <= self.clock.time() - end <= METRIC_LAG + 60, 'stale_health_sample')
        row.update(sample_end=iso(end), candidate_health=candidate, inverse_health=inverse, ingress_health=ingress)
        self.record()
        self.check_health(inverse, baseline)
        self.check_health(candidate, baseline)
        self.check_health(candidate, inverse)
        self.check_health(ingress, ingress_baseline, 'ingress')
        row['health_verified_at'] = iso(self.clock.time())

    def run(self):
        try:
            self.record()
            required = BASELINE_SECONDS + len(STAGES) * ROUTING_SECONDS + (len(STAGES) - 1) * STAGE_SECONDS
            require(self.workflow_deadline - self.start >= required + WORKFLOW_TAIL_SECONDS, 'workflow_headroom')
            self.inverse = verify_snapshot(self.snapshot, self.candidate, self.inverse, self.scope)
            self.receipt['inverse'] = self.inverse
            deadline = self.clock.monotonic() + BASELINE_SECONDS
            expected = {self.inverse: 100}
            initial = self.service(deadline)
            _, tags = verify_service(initial, self.candidate, self.inverse, expected, None)
            # Select a fresh bucket at the start of the bounded batch. Transport
            # time does not age out a bucket selected near a minute boundary.
            baseline_end = int((self.clock.time() - METRIC_LAG) // 60) * 60
            try:
                baseline, ingress_baseline = self.collect_health((self.inverse, None), baseline_end, deadline)
            except MissingSample:
                self.pause(MISSING_SAMPLE_RETRY_SECONDS, deadline)
                baseline, ingress_baseline = self.collect_health((self.inverse, None), baseline_end, deadline)
            self.receipt['baseline'] = {'sample_end': iso(baseline_end), **baseline}
            self.receipt['ingress_baseline'] = {'sample_end': iso(baseline_end), **ingress_baseline}
            current = initial
            for percent in STAGES:
                deadline = self.clock.monotonic() + ROUTING_SECONDS
                self.verify_candidate_revision(deadline)
                before = self.service(deadline)
                verify_service(
                    before,
                    self.candidate,
                    self.inverse,
                    expected,
                    tags,
                    initial['uid'],
                    current['generation'],
                )
                expected = {self.candidate: percent}
                if percent < 100:
                    expected[self.inverse] = 100 - percent
                row = {'requested_at': iso(self.clock.time()), 'weights': expected}
                self.receipt['stages'].append(row)
                self.record()
                print(f'Requesting verified candidate traffic shift to {percent} percent', flush=True)
                current = self.move(before, expected, tags, deadline)
                require(self.clock.monotonic() <= deadline, 'routing_deadline')
                deadline = self.clock.monotonic() + STAGE_SECONDS
                convergence = self.clock.time()
                row.update(
                    verified_at=iso(convergence),
                    generation=current['generation'],
                    latest_ready_revision=current['latestReadyRevision'].rsplit('/', 1)[-1],
                )
                self.record()
                if percent < 100:
                    self.guard(row, convergence, baseline, ingress_baseline, deadline)
                require(self.clock.monotonic() <= deadline, 'stage_deadline')
            self.receipt['outcome'] = 'promoted'
        except Refused as exc:
            self.receipt.update(outcome='refused', reason=str(exc))
            raise
        except BaseException:
            self.receipt['outcome'] = 'interrupted_or_failed'
            raise
        finally:
            self.receipt['finished_at'] = iso(self.clock.time())
            self.record()
            print(
                f"Selected backend promotion {self.receipt['outcome']} "
                f"in {self.receipt['promotion_elapsed_seconds']:.3f} seconds",
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, choices=(PROJECT,))
    parser.add_argument('--region', required=True, choices=(REGION,))
    parser.add_argument('--scope', choices=('backend', 'all'), default='backend')
    parser.add_argument('--inverse')
    parser.add_argument('--workflow-started', required=True, type=float)
    parser.add_argument('--workflow-timeout-minutes', required=True, type=int, choices=(90, 360))
    for field in ('candidate', 'source', 'control'):
        parser.add_argument(f'--{field}', required=True)
    for field in ('snapshot', 'receipt'):
        parser.add_argument(f'--{field}', required=True, type=Path)
    args = parser.parse_args()

    def stop(_signum, _frame):
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, stop)
    try:
        require(bool(REVISION_NAME.fullmatch(args.candidate)), 'invalid_revision')
        for sha in (args.source, args.control):
            require(bool(re.fullmatch(r'[0-9a-f]{40}', sha)), 'invalid_release_sha')
        clock = Clock()
        require(0 < args.workflow_started <= clock.monotonic(), 'workflow_start_invalid')
        Promotion(Transport(clock), clock, args).run()
    except Refused as exc:
        raise SystemExit(f'Selected backend promotion refused: {exc}') from None
    except (OSError, TypeError, ValueError, KeyError, AttributeError):
        raise SystemExit('Selected backend promotion refused: invalid input or evidence') from None


if __name__ == '__main__':
    main()
