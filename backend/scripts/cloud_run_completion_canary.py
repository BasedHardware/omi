#!/usr/bin/env python3
"""Production route90-v1 gate and CAS traffic owner (no activation authority).

All four baselines must pass before any write. Each service gets at most 60
Cloud Run metadata GETs, three route aggregate GETs (pages/failures included),
one request-count idle discriminator, two descriptor GETs, two normal PUTs and
one rollback PUT. Calls have a 30s deadline and bounded response size; no retry.
The 15-minute window starts on the next minute boundary after observed 90/10,
then waits another 120s for metric ingestion. Reconciliation allows at most 16
polls, 30s apart (450s sleep), per transition. Even late success of both normal
transitions leaves 18 reads for guarded rollback: worst case 59 of the 60 reads.
Call latency and these waits are additional to deployment/headroom admission.
Only a proven regression permits local rollback; all unknowns fail to the
workflow's guarded rollback command. An existing evidence journal is terminal
for this invocation: operators must inspect it, never blindly resend a PUT.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
from contextlib import contextmanager
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT = 'based-hardware'
REGION = 'us-central1'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
PROTOCOL = 'route90-v1'
WINDOW = 900
SETTLE = 120
ALIGN = 60
MAX_ROUTES = 256
MAX_BODY = 4 * 1024 * 1024
MAX_TRANSITION_POLLS = 16
ROUTE = re.compile(r'(?:/v[0-9]+)?(?:/[a-z][a-z_-]*){1,3}')
REVISION = re.compile(r'[a-z][a-z0-9-]{0,62}')
EXTRACTORS = {
    'method': 'REGEXP_EXTRACT(httpRequest.requestMethod, "^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$")',
    'route': 'REGEXP_EXTRACT(httpRequest.requestUrl, "^https?://[^/?#]+((?:/v[0-9]+)?(?:/[a-z][a-z_-]*){1,3})(?:/|[?#]|$)")',
}
OUTPUT_ANNOTATIONS = {
    'run.googleapis.com/operation-id',
    'run.googleapis.com/ingress-status',
    'run.googleapis.com/urls',
    'serving.knative.dev/creator',
    'serving.knative.dev/lastModifier',
}


class Refusal(Exception):
    """Fixed, redacted diagnostic; unknown evidence never authorizes promotion."""


class Regression(Refusal):
    """Explicit, readable count regression; permits guarded rollback."""


class UnknownWrite(Refusal):
    """A PUT may have applied. Do not retry or guess its outcome."""


class Clock:
    def now(self):
        return time.time()

    def monotonic(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def epoch(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        raise Refusal('invalid_metric_timestamp') from None


class Journal:
    """Private, bounded, fsynced redacted evidence, including pre-request intent."""

    def __init__(self, path, clock, *, resume=False):
        self.path = Path(path)
        self.clock = clock
        if resume:
            if self.path.is_symlink() or self.path.stat().st_size > MAX_BODY:
                raise Refusal('rollback_journal_unavailable')
            self.data = json.loads(self.path.read_text())
            if self.data.get('protocol') != PROTOCOL or not isinstance(self.data.get('events'), list):
                raise Refusal('rollback_journal_unavailable')
            return
        self.data = {'protocol': PROTOCOL, 'started': timestamp(clock.now()), 'events': []}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise Refusal('existing_journal_inspect_before_restart') from None
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(self.data))
            stream.flush()
            os.fsync(stream.fileno())

    def record(self, reason, **fields):
        if len(self.data['events']) >= 128:
            raise Refusal('evidence_budget_exhausted')
        self.data['events'].append({'at': timestamp(self.clock.now()), 'reason': reason, **fields})
        self.persist()

    def persist(self):
        # Atomic replacement keeps the last durable intent if interrupted.
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.data, stream, allow_nan=False, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@contextmanager
def read_deadline():
    """Hard wall deadline, including slow/trickling response bodies (CLI main thread)."""

    def expired(_signum, _frame):
        raise TimeoutError('request_deadline')

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class GoogleProvider:
    """Only instantiated by CLI; tests inject providers, never credentials or IO."""

    def __init__(self, journal=None):
        self.journal = journal
        self.budgets = defaultdict(int)
        if journal is not None:
            for key, value in journal.data.get('budgets', {}).items():
                if type(value) is not int or value < 0 or key.count('/') != 1:
                    raise Refusal('invalid_budget_journal')
                self.budgets[tuple(key.split('/'))] = value
        self.opener = urllib.request.build_opener(NoRedirect())

    def charge(self, service, category, limit):
        self.budgets[service, category] += 1
        if self.journal is not None:
            self.journal.data['budgets'] = {'/'.join(key): value for key, value in self.budgets.items()}
            self.journal.persist()  # Failures/pages and restarts cannot reset allowance.
        if self.budgets[service, category] > limit:
            raise Refusal(category + '_budget_exhausted')

    def request(self, service, category, limit, url, *, body=None):
        self.charge(service, category, limit)
        try:
            # Refresh per call so the full observation cannot expire a cached token.
            proc = subprocess.run(
                ['gcloud', 'auth', 'print-access-token', '--project=' + PROJECT],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            token = proc.stdout.strip()
            if not token or '\n' in token:
                raise ValueError('invalid token')
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode() if body is not None else None,
                method='PUT' if body is not None else 'GET',
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            )
            with read_deadline():
                with self.opener.open(request, timeout=30) as response:
                    raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError('response too large')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('invalid response')
            return result
        except (OSError, ValueError, subprocess.SubprocessError):
            if body is not None:
                raise UnknownWrite('unknown_write_outcome') from None
            raise Refusal('unreadable_' + category) from None

    def run_url(self, collection, name):
        return (
            f'https://{REGION}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{PROJECT}/{collection}/{name}'
        )

    def service(self, service):
        return self.request(service, 'metadata', 60, self.run_url('services', service))

    def revision(self, service, revision):
        return self.request(service, 'metadata', 60, self.run_url('revisions', revision))

    def replace(self, service, body, *, rollback=False):
        return self.request(
            service,
            'rollback' if rollback else 'normal_write',
            1 if rollback else 2,
            self.run_url('services', service),
            body=body,
        )

    def descriptors(self, service):
        name = service + '_route_2xx'
        metric = self.request(
            service, 'descriptor', 2, f'https://logging.googleapis.com/v2/projects/{PROJECT}/metrics/{name}'
        )
        descriptor = self.request(
            service,
            'descriptor',
            2,
            f'https://monitoring.googleapis.com/v3/projects/{PROJECT}/metricDescriptors?'
            + urllib.parse.urlencode({'filter': f'metric.type = "logging.googleapis.com/user/{name}"'}),
        )
        descriptors = descriptor.get('metricDescriptors', [])
        if len(descriptors) != 1:
            raise Refusal('metric_descriptor_missing_or_ambiguous')
        return metric, descriptors[0]

    def aggregate(self, service, start, end, *, idle=False):
        metric_type = 'run.googleapis.com/request_count' if idle else f'logging.googleapis.com/user/{service}_route_2xx'
        params = {
            'filter': f'metric.type="{metric_type}" AND resource.type="cloud_run_revision" '
            f'AND resource.labels.project_id="{PROJECT}" AND resource.labels.location="{REGION}" '
            f'AND resource.labels.service_name="{service}"',
            'interval.startTime': timestamp(start),
            'interval.endTime': timestamp(end),
            'aggregation.alignmentPeriod': '60s',
            'aggregation.perSeriesAligner': 'ALIGN_SUM',
            'aggregation.crossSeriesReducer': 'REDUCE_SUM',
            'view': 'FULL',
            # FULL pageSize counts points, not route series. Use the API's
            # documented maximum; byte/series limits still bound each reply.
            'pageSize': 100000,
        }
        if not idle:
            params['aggregation.groupByFields'] = ['metric.labels.route', 'resource.labels.revision_name']
        rows = []
        while True:
            url = f'https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries?' + urllib.parse.urlencode(
                params, doseq=True
            )
            page = self.request(service, 'idle' if idle else 'route_query', 1 if idle else 3, url)
            values = page.get('timeSeries', [])
            if not isinstance(values, list) or len(rows) + len(values) > 1024:
                raise Refusal('aggregate_size_or_schema')
            rows.extend(values)
            token = page.get('nextPageToken')
            if not token:
                return rows
            if not isinstance(token, str) or len(token) > 4096:
                raise Refusal('invalid_page_token')
            params['pageToken'] = token


def validate_descriptors(service, metric, descriptor):
    expected_filter = (
        f'resource.type="cloud_run_revision" AND resource.labels.project_id="{PROJECT}" '
        f'AND resource.labels.service_name="{service}" '
        f'AND logName="projects/{PROJECT}/logs/run.googleapis.com%2Frequests" '
        'AND httpRequest.status >= 200 AND httpRequest.status < 300'
    )
    if (
        metric.get('name') != service + '_route_2xx'
        or metric.get('disabled', False)
        or metric.get('filter') != expected_filter
        or metric.get('labelExtractors') != EXTRACTORS
    ):
        raise Refusal('log_metric_schema_mismatch')
    for index, definition in enumerate((metric.get('metricDescriptor', {}), descriptor)):
        labels = definition.get('labels', [])
        expected_labels = {'route': 'STRING', 'method': 'STRING'}
        # Monitoring adds its own default log label to the user definition.
        if index == 1 and any(label.get('key') == 'log' for label in labels):
            expected_labels['log'] = 'STRING'
        if (
            definition.get('metricKind') != 'DELTA'
            or definition.get('valueType') != 'INT64'
            or definition.get('unit') != '1'
            or not isinstance(labels, list)
            or len(labels) != len(expected_labels)
            or {label.get('key'): label.get('valueType', 'STRING') for label in labels} != expected_labels
        ):
            raise Refusal('metric_descriptor_schema_mismatch')
    if descriptor.get(
        'type'
    ) != f'logging.googleapis.com/user/{service}_route_2xx' or 'cloud_run_revision' not in descriptor.get(
        'monitoredResourceTypes', []
    ):
        raise Refusal('metric_resource_schema_mismatch')


def ready(document, revision, service):
    metadata = document.get('metadata', {})
    conditions = document.get('status', {}).get('conditions', [])
    if (
        metadata.get('name') != revision
        or metadata.get('labels', {}).get('serving.knative.dev/service') != service
        or [entry.get('status') for entry in conditions if entry.get('type') == 'Ready'] != ['True']
    ):
        raise Refusal('revision_not_ready_or_wrong_pin')


def traffic(entries, service):
    if not isinstance(entries, list) or not entries:
        raise Refusal('traffic_unreadable')
    result = {}
    for entry in entries:
        revision, percent = entry.get('revisionName'), entry.get('percent')
        if (
            not isinstance(revision, str)
            or not REVISION.fullmatch(revision)
            or not revision.startswith(service + '-')
            or type(percent) is not int
            or percent <= 0
            or percent > 100
            or entry.get('latestRevision') not in (None, False)
            or 'tag' in entry
            or revision in result
        ):
            raise Refusal('ambiguous_traffic')
        result[revision] = percent
    if sum(result.values()) != 100:
        raise Refusal('traffic_not_100')
    return result


def intent(document):
    """Only writable, unchanged service intent; never copy status/server metadata."""
    metadata = document['metadata']
    result = {
        'apiVersion': document['apiVersion'],
        'kind': document['kind'],
        'metadata': {
            key: copy.deepcopy(metadata[key])
            for key in ('name', 'namespace', 'labels', 'annotations')
            if key in metadata
        },
        'spec': {key: copy.deepcopy(value) for key, value in document['spec'].items() if key != 'traffic'},
    }
    if 'annotations' in result['metadata']:
        result['metadata']['annotations'] = {
            key: value for key, value in result['metadata']['annotations'].items() if key not in OUTPUT_ANNOTATIONS
        }
    return result


def intent_hash(document):
    return hashlib.sha256(json.dumps(intent(document), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inspect(document, service, candidate, original=None):
    metadata, status = document.get('metadata', {}), document.get('status', {})
    if (
        document.get('apiVersion') != 'serving.knative.dev/v1'
        or document.get('kind') != 'Service'
        or metadata.get('name') != service
        or not isinstance(metadata.get('resourceVersion'), str)
        or not metadata['resourceVersion']
        or len(metadata['resourceVersion']) > 256
        or not re.fullmatch(r'[1-9][0-9]*', str(metadata.get('generation')))
        or status.get('latestCreatedRevisionName') != candidate
        or document.get('spec', {}).get('template', {}).get('metadata', {}).get('name') != candidate
    ):
        raise Refusal('service_identity_or_candidate_drift')
    if original is not None and intent(document) != original:
        raise Refusal('foreign_service_intent_drift')
    return traffic(document['spec'].get('traffic'), service), traffic(status.get('traffic'), service)


def reconciled(document):
    return str(document['metadata']['generation']) == str(document['status'].get('observedGeneration'))


def count_points(row, start, end):
    points = row.get('points')
    if not isinstance(points, list) or not points or len(points) > 32:
        raise Refusal('missing_or_oversized_points')
    count, seen = 0, set()
    for point in points:
        interval = point.get('interval', {})
        left, right = epoch(interval.get('startTime')), epoch(interval.get('endTime'))
        if (
            left < start
            or right > end
            or right - left != ALIGN
            or left % ALIGN
            or right % ALIGN
            or (left, right) in seen
        ):
            raise Refusal('unaligned_or_duplicate_points')
        seen.add((left, right))
        value = point.get('value', {}).get('int64Value')
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,19}', value):
            raise Refusal('invalid_or_nonfinite_count')
        count += int(value)
    return count


def route_counts(rows, service, start, end):
    counts = {}
    for row in rows:
        if row.get('metricKind') != 'DELTA' or row.get('valueType') != 'INT64':
            raise Refusal('aggregate_value_schema')
        metric = row.get('metric', {})
        labels = metric.get('labels', {})
        route = labels.get('route', '')  # Google LogMetric's omitted/default label is its own bucket.
        if not isinstance(route, str) or len(route) > 128 or (route and not ROUTE.fullmatch(route)):
            raise Refusal('invalid_route_bucket')
        resource = row.get('resource', {})
        revision = resource.get('labels', {}).get('revision_name')
        if (
            metric.get('type') != f'logging.googleapis.com/user/{service}_route_2xx'
            or resource.get('type') != 'cloud_run_revision'
            or not isinstance(revision, str)
            or not REVISION.fullmatch(revision)
            or not revision.startswith(service + '-')
        ):
            raise Refusal('aggregate_revision_schema')
        for key, expected in (('project_id', PROJECT), ('location', REGION), ('service_name', service)):
            if key in resource.get('labels', {}) and resource['labels'][key] != expected:
                raise Refusal('aggregate_resource_drift')
        counts[route, revision] = counts.get((route, revision), 0) + count_points(row, start, end)
    if len({route for route, _ in counts}) > MAX_ROUTES:
        raise Refusal('route_budget_exhausted')
    return counts


class Canary:
    def __init__(self, provider, clock, journal, candidates):
        if set(candidates) != set(SERVICES) or any(
            not isinstance(revision, str) or not REVISION.fullmatch(revision) or not revision.startswith(service + '-')
            for service, revision in candidates.items()
        ):
            raise Refusal('four_exact_candidates_required')
        self.provider, self.clock, self.journal, self.candidates = provider, clock, journal, candidates
        self.states = {}

    def pause_until(self, deadline, monotonic_deadline):
        while True:
            wall_remaining = deadline - self.clock.now()
            monotonic_remaining = monotonic_deadline - self.clock.monotonic()
            if abs(wall_remaining - monotonic_remaining) > 5:
                raise Refusal('clock_drift')
            remaining = max(wall_remaining, monotonic_remaining)
            if remaining <= 0:
                return
            self.clock.sleep(min(30, remaining))

    def current(self, service, expected):
        state = self.states[service]
        document = self.provider.service(service)
        spec, actual = inspect(document, service, self.candidates[service], state['intent'])
        if spec != expected or actual != expected or not reconciled(document):
            raise Refusal('foreign_or_unreconciled_traffic')
        return document

    def put(self, service, document, shares, *, rollback=False):
        body = intent(document)
        body['metadata']['resourceVersion'] = document['metadata']['resourceVersion']
        body['spec']['traffic'] = [{'revisionName': name, 'percent': percent} for name, percent in shares.items()]
        self.journal.record('rollback_intent' if rollback else 'write_intent', service=service, traffic=shares)
        # Any exception after handing a request to the writer has unknown outcome.
        try:
            self.provider.replace(service, body, rollback=rollback)
        except Exception:
            self.journal.record('unknown_write_outcome', service=service, traffic=shares)
            raise UnknownWrite('unknown_write_outcome') from None
        self.journal.record('write_acknowledged', service=service, traffic=shares)

    def wait_traffic(self, service, target, previous):
        deadline = self.clock.monotonic() + 600
        for poll in range(MAX_TRANSITION_POLLS):
            document = self.provider.service(service)
            spec, actual = inspect(document, service, self.candidates[service], self.states[service]['intent'])
            if spec != target or actual not in (target, previous):
                raise Refusal('foreign_traffic_drift')
            if actual == target and reconciled(document):
                self.journal.record('actual_traffic_reconciled', service=service, traffic=actual)
                return document
            if self.clock.monotonic() >= deadline or poll == MAX_TRANSITION_POLLS - 1:
                raise Refusal('traffic_reconcile_timeout')
            self.clock.sleep(30)

    def empty(self, service, start, end):
        rows = self.provider.aggregate(service, start, end, idle=True)
        # The discriminator describes refusal only; idle is never an exemption.
        total = sum(count_points(row, start, end) for row in rows)
        raise Refusal('idle_refused' if rows and total == 0 else 'missing_route_evidence')

    def prepare(self):
        end = math.floor(self.clock.now() / ALIGN) * ALIGN - SETTLE
        start = end - 1800
        for service in SERVICES:
            candidate = self.candidates[service]
            document = self.provider.service(service)
            spec, actual = inspect(document, service, candidate)
            if spec != actual or len(actual) != 1 or candidate in actual or not reconciled(document):
                raise Refusal('old_100_pin_required')
            old = next(iter(actual))
            ready(self.provider.revision(service, candidate), candidate, service)
            ready(self.provider.revision(service, old), old, service)
            validate_descriptors(service, *self.provider.descriptors(service))
            counts = route_counts(self.provider.aggregate(service, start, end), service, start, end)
            if not counts:
                self.empty(service, start, end)
            baseline = defaultdict(int)
            for (route, _), count in counts.items():
                baseline[route] += count
            if not any(count >= 30 for count in baseline.values()):
                raise Refusal('no_eligible_baseline_routes')
            self.states[service] = {'old': old, 'intent': intent(document), 'baseline': dict(baseline)}
            buckets = {route: index for index, route in enumerate(sorted(baseline))}
            self.states[service]['buckets'] = buckets
            self.journal.record(
                'baseline_validated',
                service=service,
                old=old,
                candidate=candidate,
                intent_sha256=intent_hash(document),
                start=timestamp(start),
                end=timestamp(end),
                counts=[
                    {'bucket': buckets[route], 'revision': revision, 'count': count}
                    for (route, revision), count in sorted(counts.items())
                ],
            )

    def split(self, service):
        return {self.states[service]['old']: 90, self.candidates[service]: 10}

    def observe(self, service):
        state = self.states[service]
        self.current(service, self.split(service))
        counts = route_counts(
            self.provider.aggregate(service, state['start'], state['end']),
            service,
            state['start'],
            state['end'],
        )
        if not counts:
            self.empty(service, state['start'], state['end'])
        if any(revision not in self.split(service) for _, revision in counts):
            raise Refusal('foreign_revision_evidence')
        # Record every count, including new/default buckets; never emit route text.
        buckets = dict(state['buckets'])
        for route in sorted({route for route, _ in counts} - set(buckets)):
            buckets[route] = len(buckets)
        if len(buckets) > MAX_ROUTES:
            raise Refusal('route_budget_exhausted')
        self.journal.record(
            'observation_counts',
            service=service,
            counts=[
                {'bucket': buckets[route], 'revision': revision, 'count': count}
                for (route, revision), count in sorted(counts.items())
            ],
        )
        failed = False
        for route, baseline in state['baseline'].items():
            if baseline < 30:
                continue
            old = counts.get((route, state['old']))
            new = counts.get((route, self.candidates[service]))
            if old is None or new is None:
                raise Refusal('missing_eligible_route_evidence')
            # (new / .10) >= .70 * (old / .90), exact integer arithmetic.
            if old == 0 or new == 0 or new * 900 < old * 70:
                failed = True
        if failed:
            raise Regression('completion_regression')
        self.journal.record('settled_evidence_passed', service=service)

    def run(self):
        self.prepare()
        for service in SERVICES:
            old = {self.states[service]['old']: 100}
            document = self.current(service, old)
            self.put(service, document, self.split(service))
            self.wait_traffic(service, self.split(service), old)
            anchor = self.clock.now()
            start = math.ceil(anchor / ALIGN) * ALIGN
            self.states[service].update(
                start=start,
                end=start + WINDOW,
                settled_monotonic=self.clock.monotonic() + (start - anchor) + WINDOW + SETTLE,
            )
            self.journal.record(
                'observation_window',
                service=service,
                anchor=timestamp(anchor),
                start=timestamp(start),
                end=timestamp(start + WINDOW),
                settled=timestamp(start + WINDOW + SETTLE),
            )
        self.pause_until(
            max(state['end'] + SETTLE for state in self.states.values()),
            max(state['settled_monotonic'] for state in self.states.values()),
        )
        try:
            for service in SERVICES:
                self.observe(service)
        except Regression:
            for service in SERVICES:
                document = self.current(service, self.split(service))
                old = self.states[service]['old']
                ready(self.provider.revision(service, old), old, service)
                self.put(service, document, {old: 100}, rollback=True)
                self.wait_traffic(service, {old: 100}, self.split(service))
            raise
        for service in SERVICES:
            candidate = self.candidates[service]
            document = self.current(service, self.split(service))
            ready(self.provider.revision(service, candidate), candidate, service)
            self.put(service, document, {candidate: 100})
            self.wait_traffic(service, {candidate: 100}, self.split(service))
            ready(self.provider.revision(service, candidate), candidate, service)
            self.current(service, {candidate: 100})
        self.journal.record('CANARY_OK')


def rollback_recorded(provider, clock, journal, candidates):
    """Fresh CAS rollback of recorded owned traffic only; no generic restore."""
    anchors = {
        event.get('service'): event for event in journal.data['events'] if event.get('reason') == 'baseline_validated'
    }
    writer_services = {
        event.get('service') for event in journal.data['events'] if event.get('reason') == 'write_intent'
    }
    if not writer_services:
        journal.record('rollback_not_needed_no_write_intent')
        return
    if not writer_services <= set(SERVICES) or not writer_services <= set(anchors):
        raise Refusal('rollback_anchor_missing')
    controller = Canary(provider, clock, journal, candidates)
    for service in SERVICES:
        if service not in writer_services:
            continue
        anchor = anchors[service]
        old, candidate = anchor.get('old'), candidates[service]
        if (
            anchor.get('candidate') != candidate
            or not isinstance(old, str)
            or not REVISION.fullmatch(old)
            or not old.startswith(service + '-')
            or old == candidate
        ):
            raise Refusal('rollback_pin_mismatch')
        document = provider.service(service)
        spec, actual = inspect(document, service, candidate)
        if spec != actual or not reconciled(document) or intent_hash(document) != anchor.get('intent_sha256'):
            raise Refusal('rollback_foreign_or_unreconciled_intent')
        controller.states[service] = dict(old=old, intent=intent(document))
        if actual == {old: 100}:
            journal.record('rollback_already_observed', service=service)
            continue
        if actual not in ({old: 90, candidate: 10}, {candidate: 100}):
            raise Refusal('rollback_foreign_traffic')
        ready(provider.revision(service, old), old, service)
        controller.put(service, document, {old: 100}, rollback=True)
        controller.wait_traffic(service, {old: 100}, actual)
    journal.record('rollback_observed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', action='store_true', help='Guarded rollback using existing redacted evidence')
    parser.add_argument('--project', choices=(PROJECT,), required=True)
    parser.add_argument('--region', choices=(REGION,), required=True)
    parser.add_argument('--candidate', action='append', required=True, metavar='SERVICE=REVISION')
    parser.add_argument('--evidence-path', type=Path, required=True)
    args = parser.parse_args()
    journal = None
    try:
        candidates = dict(item.split('=', 1) for item in args.candidate)
        if len(args.candidate) != 4 or len(candidates) != 4:
            raise Refusal('four_exact_candidates_required')
        clock = Clock()
        journal = Journal(args.evidence_path, clock, resume=args.rollback)
        provider = GoogleProvider(journal)
        if args.rollback:
            rollback_recorded(provider, clock, journal, candidates)
        else:
            Canary(provider, clock, journal, candidates).run()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, Refusal) else 'unreadable_schema_or_local_failure'
        if journal:
            journal.record(reason)
        print('CANARY_REFUSED ' + reason, file=sys.stderr)
        return 1
    print('CANARY_ROLLBACK_OBSERVED' if args.rollback else 'CANARY_OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
