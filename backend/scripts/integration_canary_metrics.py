"""Bounded authenticated metadata transport and strict Cloud Run metric evidence.

CPU distributions are merged BEFORE percentile alignment; percentiles are never
averaged. See https://cloud.google.com/monitoring/api/v3/aggregation and the
projects.timeSeries.list secondaryAggregation contract. No production IO at import.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import selectors
import signal
import subprocess
import time as _time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

PROJECT = 'based-hardware'
REGION = 'us-central1'
SERVICE = 'backend-integration'
MAX_BYTES = 2 * 1024 * 1024
METRIC_LAG = 120  # Query complete minute buckets, allowing bounded publication latency.


class Refused(ValueError):
    """Only constant, content-free reason codes may cross the CLI boundary."""


class Clock:
    time = staticmethod(_time.time)
    monotonic = staticmethod(_time.monotonic)
    sleep = staticmethod(_time.sleep)


_io_budget = ContextVar('integration_canary_io_budget', default=None)


@contextmanager
def io_budget(seconds, clock):
    stop = clock.monotonic() + seconds
    previous = _io_budget.get()
    if previous:
        stop = min(stop, previous[0])
    token = _io_budget.set((stop, clock))
    try:
        yield
        require(clock.monotonic() <= stop, 'io_deadline')
    finally:
        _io_budget.reset(token)


def io_remaining(limit):
    budget = _io_budget.get()
    if budget:
        limit = min(limit, budget[0] - budget[1].monotonic())
    require(limit > 0, 'io_deadline')
    return limit


def require(condition, code):
    if not condition:
        raise Refused(code)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'invalid_number')
    return value


def fraction(value):
    require(0 <= number(value) <= 1, 'invalid_fraction')
    return value


def command(argv):
    """No shell, no retries, no stderr/argv in exceptions; run reaps on cancellation."""
    child = None
    try:
        stop = _time.monotonic() + io_remaining(30)
        child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        output = bytearray()
        total = 0
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ, True)
            selector.register(child.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                remaining = stop - _time.monotonic()
                require(remaining > 0, 'command_deadline')
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), min(65536, MAX_BYTES + 1 - total))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    require(total <= MAX_BYTES, 'command_output_budget')
                    if key.data:
                        output.extend(chunk)
        require(child.wait(timeout=max(0.001, stop - _time.monotonic())) == 0, 'command_failed')
        io_remaining(30)
        return output.decode('utf-8').strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Refused('command_failed') from None
    finally:
        if child is not None:
            # Kill the exact child process group, including descendants retaining
            # pipe handles. Reap on timeout, cap, exception and cancellation.
            try:
                try:
                    if child.returncode is None:
                        os.killpg(child.pid, signal.SIGKILL)
                    else:
                        # An already-reaped leader cannot authorize a new kill.
                        os.killpg(child.pid, 0)
                        raise Refused('command_group_survived')
                except ProcessLookupError:
                    pass
            finally:
                # A signal denial is not proof of exit and must still refuse.
                # Retain/reap the exact child even if the signal raised.
                child.wait(timeout=5)
                child.stdout.close()
                child.stderr.close()


def decode(raw):
    try:

        def invalid(_):
            raise Refused('invalid_json')

        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'duplicate_json_key')
                result[key] = value
            return result

        doc = json.loads(raw, parse_constant=invalid, object_pairs_hook=unique)
        require(isinstance(doc, dict), 'invalid_json')
        return doc
    except (ValueError, UnicodeError):
        raise Refused('invalid_json') from None


@dataclass
class Reply:
    doc: dict
    raw: bytes
    headers: dict


class Transport:
    """HTTPS only, no proxies; Monitoring/Run never redirect. Tokens stay in memory."""

    def __init__(self, clock=None):
        self.clock = clock or Clock()
        self._token = None

    def request(self, method, url, body=None, deadline=None, registry_blob=False):
        parts = urlsplit(url)
        require(
            parts.scheme == 'https'
            and parts.netloc in ('monitoring.googleapis.com', 'us-central1-run.googleapis.com', 'gcr.io')
            and parts.username is None
            and parts.password is None
            and parts.port is None
            and not parts.fragment
            and method in ('GET', 'PUT'),
            'transport_origin_refused',
        )
        if self._token is None:
            with io_budget(5, self.clock):
                self._token = command(['gcloud', 'auth', 'print-access-token', '--project', PROJECT, '--quiet'])
            require(bool(self._token) and '\n' not in self._token, 'token_unavailable')
        stop = min(deadline or float('inf'), self.clock.monotonic() + io_remaining(10))

        def remaining():
            seconds = stop - self.clock.monotonic()
            require(seconds > 0, 'transport_deadline')
            return seconds

        conn = http.client.HTTPSConnection(parts.netloc, timeout=remaining())
        try:
            payload = None if body is None else json.dumps(body, allow_nan=False).encode()
            require(payload is None or len(payload) <= MAX_BYTES, 'body_too_large')
            conn.request(
                method,
                parts.path + ('?' + parts.query if parts.query else ''),
                body=payload,
                headers={
                    'Authorization': 'Bearer ' + self._token,
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, application/vnd.docker.distribution.manifest.v2+json, '
                    'application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, '
                    'application/vnd.docker.distribution.manifest.list.v2+json',
                },
            )
            conn.sock.settimeout(remaining())
            response = conn.getresponse()
            require(response.getheader('Content-Encoding', 'identity') == 'identity', 'compressed_response_refused')
            require(200 <= response.status < 300, 'http_request_refused')
            raw = bytearray()
            while True:
                if conn.sock:
                    conn.sock.settimeout(remaining())
                remaining()
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                require(len(raw) <= MAX_BYTES, 'response_too_large')
            return Reply(decode(bytes(raw)), bytes(raw), {k.lower(): v for k, v in response.getheaders()})
        except (OSError, http.client.HTTPException, ValueError):
            raise Refused('transport_failed') from None
        finally:
            conn.close()


def timestamp(value):
    try:
        require(isinstance(value, str) and value.endswith('Z'), 'invalid_timestamp')
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError):
        raise Refused('invalid_timestamp') from None


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class Minute:
    end: int
    requests: int
    errors: int
    cpu_p95: float


def window(rows, start, end):
    require(type(start) is int and type(end) is int and start % 60 == end % 60 == 0, 'unaligned_window')
    require(end > start, 'invalid_window')
    for row in rows:
        require(isinstance(row, Minute), 'invalid_minute')
        require(type(row.end) is int and type(row.requests) is int and type(row.errors) is int, 'invalid_minute')
        require(0 <= row.errors <= row.requests and row.requests > 0, 'idle_or_invalid_minute')
        fraction(row.cpu_p95)
    require(sorted(r.end for r in rows) == list(range(start + 60, end + 1, 60)), 'incomplete_minutes')
    return rows


def decision(rows, *, moved_at, now, baseline_share, end):
    """Timing adapted from offline integration_canary.py at design 504f33f3.

    The reviewed design is a timing reference, not workflow admission.
    """
    fraction(baseline_share)
    require(number(moved_at) <= number(now), 'invalid_move_clock')
    require(type(end) is int and end % 60 == 0 and 0 <= now - end <= 180, 'stale_metrics')
    if end - 600 < moved_at + 180:
        return {'state': 'immature', 'reason': 'post_warmup_window_incomplete'}
    rows = window(rows, end - 600, end)
    rate = sum(r.errors for r in rows) / sum(r.requests for r in rows)
    threshold = max(0.015, 2 * baseline_share)
    return {
        'state': 'rollback' if rate > threshold or all(r.cpu_p95 >= 0.95 for r in rows) else 'below_threshold',
        'error_share': rate,
        'error_threshold': threshold,
    }


class Metrics:
    def __init__(self, transport, clock=None):
        self.transport = transport
        self.clock = clock or Clock()

    def series(self, metric, start, end, period, cpu, deadline):
        params = {
            'filter': f'metric.type="run.googleapis.com/{metric}" AND resource.type="cloud_run_revision" '
            f'AND resource.labels.project_id="{PROJECT}" AND resource.labels.location="{REGION}" '
            f'AND resource.labels.service_name="{SERVICE}"',
            'interval.startTime': iso(start),
            'interval.endTime': iso(end),
            'view': 'FULL',
            'pageSize': '10000',
            'aggregation.alignmentPeriod': f'{period}s',
            'aggregation.perSeriesAligner': 'ALIGN_SUM',
            'aggregation.crossSeriesReducer': 'REDUCE_SUM',
        }
        if cpu:
            # Merge distributions across ALL revisions/instances before percentile.
            params['secondaryAggregation.alignmentPeriod'] = f'{period}s'
            params['secondaryAggregation.perSeriesAligner'] = 'ALIGN_PERCENTILE_95'
        else:
            params['aggregation.groupByFields'] = 'metric.labels.response_code_class'
        series, seen = [], set()
        for _ in range(8):
            require(self.clock.monotonic() < deadline, 'metric_collection_deadline')
            reply = self.transport.request(
                'GET',
                f'https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries?' + urlencode(params),
                deadline=deadline,
            )
            require(self.clock.monotonic() <= deadline, 'metric_collection_deadline')
            doc = reply.doc
            require(isinstance(doc, dict) and len(reply.raw) <= MAX_BYTES, 'malformed_metric_page')
            for key in ('executionErrors', 'unreachable'):
                require(key not in doc or (isinstance(doc[key], list) and not doc[key]), 'metric_page_error')
            require('error' not in doc, 'metric_page_error')
            items = doc.get('timeSeries', [])
            require(isinstance(items, list), 'malformed_metric_page')
            series.extend(items)
            token = doc.get('nextPageToken', '')
            require(isinstance(token, str) and len(token) <= 4096, 'malformed_page_token')
            if not token:
                return series
            require(token not in seen, 'metric_page_cycle')
            seen.add(token)
            params['pageToken'] = token
        raise Refused('metric_page_budget')

    @staticmethod
    def points(series, start, end, period, cpu):
        result, seen = {}, set()
        require(bool(series), 'metrics_missing')
        for item in series:
            require(isinstance(item, dict), 'malformed_series')
            require(item.get('valueType') == ('DOUBLE' if cpu else 'INT64'), 'unexpected_metric_type')
            require(item.get('metricKind') == ('GAUGE' if cpu else 'DELTA'), 'unexpected_metric_kind')
            code = 'cpu' if cpu else item.get('metric', {}).get('labels', {}).get('response_code_class')
            require(cpu or code in ('1xx', '2xx', '3xx', '4xx', '5xx'), 'unknown_response_class')
            points = item.get('points')
            require(isinstance(points, list) and points, 'metrics_missing')
            for point in points:
                interval = point['interval']
                at = timestamp(interval['endTime'])
                require(
                    at.is_integer() and at % 60 == 0 and (end - at) % period == 0 and start < at <= end,
                    'metric_time_mismatch',
                )
                if not cpu:
                    require(timestamp(interval['startTime']) == at - period, 'metric_interval_mismatch')
                key = (code, int(at))
                require(key not in seen, 'duplicate_metric_point')
                seen.add(key)
                value = point['value']
                if cpu:
                    require(set(value) == {'doubleValue'}, 'invalid_metric_value')
                    result[int(at)] = fraction(value['doubleValue'])
                else:
                    require(set(value) == {'int64Value'}, 'invalid_metric_value')
                    text = value['int64Value']
                    require(isinstance(text, str) and text.isascii() and text.isdigit(), 'invalid_metric_value')
                    count = int(text)
                    require(count <= 2**63 - 1, 'invalid_metric_value')
                    total, errors = result.get(int(at), (0, 0))
                    result[int(at)] = (total + count, errors + (count if code == '5xx' else 0))
        require(set(result) == set(range(start + period, end + 1, period)), 'incomplete_minutes')
        return result

    def collect(self, minutes=10, preflight=False):
        """At most 24 requests / 60 seconds / 8 pages per query; never retry."""
        deadline = self.clock.monotonic() + 60
        end = int((self.clock.time() - METRIC_LAG) // 60) * 60
        start = end - minutes * 60
        requests = self.points(self.series('request_count', start, end, 60, False, deadline), start, end, 60, False)
        cpu = self.points(
            self.series('container/cpu/utilizations', start, end, 60, True, deadline), start, end, 60, True
        )
        rows = window([Minute(t, *requests[t], cpu[t]) for t in sorted(requests)], start, end)
        result = {'end': end, 'read_at': self.clock.time(), 'rows': rows}
        require(0 <= self.clock.time() - end <= 180, 'stale_metrics')
        if preflight:
            require(minutes == 30, 'preflight_window_invalid')
            actual = self.points(
                self.series('container/cpu/utilizations', start, end, 1800, True, deadline),
                start,
                end,
                1800,
                True,
            )
            # 30-minute alignment boundaries need not coincide with the minute end;
            # see series(): interval's end anchors Cloud Monitoring alignment.
            result['cpu_p95'] = actual[end]
            result['share'] = sum(r.errors for r in rows) / sum(r.requests for r in rows)
            require(result['cpu_p95'] <= 0.90 and result['share'] < 0.01, 'preflight_threshold')
        require(self.clock.monotonic() <= deadline, 'metric_collection_deadline')
        result['read_at'] = self.clock.time()
        require(0 <= result['read_at'] - end <= 180, 'stale_metrics')
        return result
