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
from pathlib import Path
from urllib.parse import urlencode

if __package__:
    from .cloud_run_traffic_snapshot import SNAPSHOT_SCHEMA_VERSION, restore_targets
    from .integration_canary_metrics import (
        METRIC_LAG,
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
    from cloud_run_traffic_snapshot import SNAPSHOT_SCHEMA_VERSION, restore_targets
    from integration_canary_metrics import (
        METRIC_LAG,
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
STAGES = (10, 50, 90, 100)
STAGE_SECONDS = 360


def routing(rows, latest=None):
    weights, tags = {}, {}
    require(isinstance(rows, list) and bool(rows), 'traffic_missing')
    for row in rows:
        percent = row.get('percent', 0)
        require(type(percent) is int and 0 <= percent <= 100, 'traffic_weight_invalid')
        kind = row.get('type')
        require(kind in (LATEST, REVISION), 'traffic_target_type_invalid')
        revision = row.get('revision') or (latest if kind == LATEST else None)
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


def verify_service(doc, candidate, expected, tags, uid=None, generation=None):
    require(doc.get('name') == SERVICE and bool(doc.get('uid')), 'service_identity_invalid')
    require(uid is None or doc['uid'] == uid, 'service_replaced')
    actual_generation = doc.get('generation', '')
    require(isinstance(actual_generation, str) and actual_generation.isdigit(), 'generation_missing')
    require(generation is None or actual_generation == generation, 'generation_drift')
    require(actual_generation == doc.get('observedGeneration') and not doc.get('reconciling'), 'generation_unobserved')
    require(doc.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED', 'service_not_ready')
    require(isinstance(doc.get('etag'), str) and bool(doc['etag']), 'etag_missing')
    full_name = f'{SERVICE}/revisions/{candidate}'
    require(
        doc.get('latestCreatedRevision') == doc.get('latestReadyRevision') == full_name,
        'candidate_not_latest_ready',
    )
    require(routing(doc.get('traffic'), candidate) == (expected, tags), 'requested_traffic_drift')
    require(routing(doc.get('trafficStatuses')) == (expected, tags), 'observed_traffic_drift')


def verify_snapshot(path, candidate, inverse):
    snapshot = json.loads(path.read_text())
    require(
        snapshot.get('schema_version') == SNAPSHOT_SCHEMA_VERSION
        and snapshot.get('project') == PROJECT
        and snapshot.get('region') == REGION
        and set(snapshot.get('services', {})) == {'backend'}
        and snapshot.get('missing_services') == [],
        'snapshot_scope_invalid',
    )
    backend = snapshot['services']['backend']
    for field in ('spec', 'status'):
        require(restore_targets(backend, traffic_source=field) == [(inverse, 100)], 'snapshot_inverse_mismatch')
    observed = backend['status']
    require(
        observed.get('latestCreatedRevisionName') == observed.get('latestReadyRevisionName') == candidate,
        'snapshot_candidate_mismatch',
    )


class MissingSample(Refused):
    """A complete sample has not been published yet."""


class Promotion:
    def __init__(self, transport, clock, args):
        self.transport = transport
        self.clock = clock
        self.candidate = args.candidate
        self.inverse = args.inverse
        self.path = args.receipt
        self.start = clock.monotonic()
        self.receipt = {
            'schema': 1,
            'service': 'backend',
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

    def pause(self, seconds, deadline):
        require(self.clock.monotonic() + seconds < deadline, 'stage_deadline')
        self.clock.sleep(seconds)

    def move(self, current, weights, tags, deadline):
        traffic = [{'type': REVISION, 'revision': rev, 'percent': weight} for rev, weight in weights.items()]
        for row in current['traffic']:
            if 'tag' in row:
                traffic.append({key: row[key] for key in ('type', 'revision', 'tag') if key in row})
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
        verify_service(landed, self.candidate, weights, tags, current['uid'], str(int(current['generation']) + 1))
        return landed

    def metric(self, revision, metric, end, deadline):
        params = {
            'filter': (
                f'metric.type="run.googleapis.com/{metric}" AND resource.type="cloud_run_revision"'
                f' AND resource.labels.project_id="{PROJECT}" AND resource.labels.location="{REGION}"'
                f' AND resource.labels.service_name="backend" AND resource.labels.revision_name="{revision}"'
            ),
            'interval.startTime': iso(end - 60),
            'interval.endTime': iso(end),
            'aggregation.alignmentPeriod': '60s',
            'aggregation.perSeriesAligner': 'ALIGN_SUM',
            'aggregation.crossSeriesReducer': 'REDUCE_SUM',
        }
        if metric == 'request_count':
            params['aggregation.groupByFields'] = 'metric.labels.response_code_class'
        if metric == 'request_latencies':
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
            label = series.get('metric', {}).get('labels', {}).get('response_code_class', '')
            require(label not in result, 'duplicate_metric_series')
            points = series['points']
            require(len(points) == 1, 'invalid_metric_bucket')
            point = points[0]
            require(point['interval']['endTime'] == iso(end), 'stale_metric_bucket')
            result[label] = point['value']
        return result

    def health(self, revision, end, deadline, *, capacity=False):
        counts = self.metric(revision, 'request_count', end, deadline)
        latencies = self.metric(revision, 'request_latencies', end, deadline)
        if not counts or not latencies:
            raise MissingSample('missing_request_evidence')
        require(set(counts) <= {'1xx', '2xx', '3xx', '4xx', '5xx'}, 'invalid_response_class')
        requests = {key: int(value['int64Value']) for key, value in counts.items()}
        total = sum(requests.values())
        require(total > 0 and min(requests.values()) >= 0, 'invalid_request_count')
        p95 = latencies['']['doubleValue']
        require(type(p95) in (int, float) and 0 <= p95 and math.isfinite(p95), 'invalid_request_latency')
        sample = {'requests': total, 'errors_5xx': requests.get('5xx', 0), 'p95_ms': p95}
        if capacity:
            instances = self.metric(revision, 'container/instance_count', end, deadline)
            if not instances:
                raise MissingSample('missing_instance_evidence')
            require(int(instances['']['int64Value']) > 0, 'no_active_candidate_instances')
            sample['active_instances'] = int(instances['']['int64Value'])
            startup = self.metric(revision, 'container/startup_latencies', end, deadline)
            if startup:
                distribution = startup['']['distributionValue']
                sample['startup_count'] = int(distribution.get('count', 0))
                sample['startup_mean_ms'] = distribution.get('mean')
            else:
                # No latency point is expected when no instance starts complete in this bucket.
                sample['startup_count'] = None
        return sample

    @staticmethod
    def check_health(sample, reference):
        rate = sample['errors_5xx'] / sample['requests']
        reference_rate = reference['errors_5xx'] / reference['requests']
        require(rate <= max(0.01, 2 * reference_rate + 0.001), 'stage_5xx_regression')
        require(sample['p95_ms'] <= max(1000, 2 * reference['p95_ms']), 'stage_latency_regression')

    def guard(self, row, convergence, baseline, deadline):
        # The entire bucket starts after convergence. Re-read only absent samples
        # within the stage deadline, and never substitute an older bucket.
        first_end = (int(convergence // 60) + 2) * 60
        while True:
            end = max(first_end, int((self.clock.time() - METRIC_LAG) // 60) * 60)
            delay = end + METRIC_LAG - self.clock.time()
            if delay > 0:
                self.pause(delay, deadline)
            try:
                candidate = self.health(self.candidate, end, deadline, capacity=True)
                inverse = self.health(self.inverse, end, deadline)
            except MissingSample:
                self.pause(5, deadline)
                continue
            break
        require(METRIC_LAG <= self.clock.time() - end <= METRIC_LAG + 60, 'stale_health_sample')
        row.update(sample_end=iso(end), candidate_health=candidate, inverse_health=inverse)
        self.record()
        self.check_health(inverse, baseline)
        self.check_health(candidate, baseline)
        self.check_health(candidate, inverse)
        row['health_verified_at'] = iso(self.clock.time())

    def run(self):
        try:
            self.record()
            verify_snapshot(self.snapshot, self.candidate, self.inverse)
            deadline = self.clock.monotonic() + 60
            expected = {self.inverse: 100}
            initial = self.service(deadline)
            _, tags = routing(initial.get('traffic'), self.candidate)
            verify_service(initial, self.candidate, expected, tags)
            baseline_end = int((self.clock.time() - METRIC_LAG) // 60) * 60
            baseline = self.health(self.inverse, baseline_end, deadline)
            require(self.clock.time() - baseline_end <= METRIC_LAG + 60, 'stale_baseline')
            self.receipt['baseline'] = {'sample_end': iso(baseline_end), **baseline}
            current = initial
            for percent in STAGES:
                deadline = self.clock.monotonic() + STAGE_SECONDS
                before = self.service(deadline)
                verify_service(before, self.candidate, expected, tags, initial['uid'], current['generation'])
                expected = {self.candidate: percent}
                if percent < 100:
                    expected[self.inverse] = 100 - percent
                row = {'requested_at': iso(self.clock.time()), 'weights': expected}
                self.receipt['stages'].append(row)
                self.record()
                print(f'Requesting verified candidate traffic shift to {percent} percent', flush=True)
                current = self.move(before, expected, tags, deadline)
                convergence = self.clock.time()
                row.update(verified_at=iso(convergence), generation=current['generation'])
                self.record()
                if percent < 100:
                    self.guard(row, convergence, baseline, deadline)
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
    for field in ('candidate', 'inverse', 'source', 'control'):
        parser.add_argument(f'--{field}', required=True)
    for field in ('snapshot', 'receipt'):
        parser.add_argument(f'--{field}', required=True, type=Path)
    args = parser.parse_args()

    def stop(_signum, _frame):
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, stop)
    try:
        require(args.candidate != args.inverse, 'candidate_equals_inverse')
        for revision in (args.candidate, args.inverse):
            require(bool(re.fullmatch(r'backend-[a-z0-9](?:[a-z0-9-]{0,53}[a-z0-9])?', revision)), 'invalid_revision')
        for sha in (args.source, args.control):
            require(bool(re.fullmatch(r'[0-9a-f]{40}', sha)), 'invalid_release_sha')
        clock = Clock()
        Promotion(Transport(clock), clock, args).run()
    except Refused as exc:
        raise SystemExit(f'Selected backend promotion refused: {exc}') from None
    except (OSError, TypeError, ValueError, KeyError, AttributeError):
        raise SystemExit('Selected backend promotion refused: invalid input or evidence') from None


if __name__ == '__main__':
    main()
