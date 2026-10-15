#!/usr/bin/env python3
"""Read-only inventory and fail-closed local-Prometheus/Monarch shadow queries.

No datasource/rule changes are implemented. Credentials are environment-only and
HTTP error bodies are never printed. A successful comparison is evidence, not
permission to cut over. Uses only the Python standard library.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

MONITORING = Path(__file__).resolve().parents[1] / 'charts/monitoring'
MAPPINGS = MONITORING / 'gmp-shadow-mappings.json'
BRIDGE = 'cloud-run-application-metrics'
MANAGED_URL = 'https://monitoring.googleapis.com/v1/projects/based-hardware/location/global/prometheus'
GRAFANA_LOCAL_URL = 'https://monitor.omi.me/api/datasources/proxy/uid/prometheus'
GRAFANA_MANAGED_URL = 'https://monitor.omi.me/api/datasources/proxy/uid/gmp-cloud-run'


class Unproven(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def expressions(value, pointer=''):
    """Include nested panels, library definitions, variables and rule query models."""
    if isinstance(value, dict):
        for key, child in value.items():
            path = pointer + '/' + str(key).replace('~', '~0').replace('/', '~1')
            if key in ('expr', 'query', 'expression', 'definition') and isinstance(child, str):
                yield path, child
            else:
                yield from expressions(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from expressions(child, pointer + '/' + str(index))


def references(expr):
    # Token discovery only, never an automatic PromQL rewriting/parser service.
    clean = re.sub(r'"(?:\\.|[^"\\])*"', '', expr)
    return sorted(set(re.findall(r'\b(?:omi_[A-Za-z0-9_]+|stackdriver_[A-Za-z0-9_]+)', clean)))


def inventory(root=MONITORING):
    entries = []
    # Split files are authoritative and include source location; combined checked separately.
    files = sorted((root / 'alerts').glob('*.json')) + sorted((root / 'dashboards').rglob('*.json'))
    for path in files:
        data = json.loads(path.read_text())
        owners = data if isinstance(data, list) else [data]
        for owner in owners:
            for pointer, expr in expressions(owner):
                names = references(expr)
                explicit = bool(re.search(r'(?<![\w-])' + re.escape(BRIDGE) + r'(?![\w-])', expr)) or bool(
                    re.search(r'stackdriver_[^"\s]*omi', expr)
                )
                if not explicit and not any(n.startswith('omi_') for n in names):
                    continue
                issues = []
                if re.search(r'__name__\s*(?:=~|!~|!=)', expr):
                    issues.append('metric-name-regex: retain-local; enumerate exact names before migration')
                if any(n.startswith('omi_sync_phase_') for n in names):
                    issues.append('custom generic_task distribution; never rewrite to native GMP omi metric')
                if '$' in expr:
                    issues.append('dashboard variables/macros require explicit expansion before shadow')
                panel = owner
                for segment in pointer.strip('/').split('/'):
                    if isinstance(panel, dict) and segment == 'targets':
                        break
                    try:
                        panel = panel[int(segment)] if isinstance(panel, list) else panel[segment]
                    except (KeyError, IndexError, ValueError, TypeError):
                        panel = {}
                        break
                panel_info = {'id': panel.get('id'), 'title': panel.get('title')} if isinstance(panel, dict) else None
                entries.append(
                    {
                        'file': str(path.relative_to(root)),
                        'owner_uid': owner.get('uid'),
                        'owner_title': owner.get('title'),
                        'panel': panel_info if str(path).find('/dashboards/') >= 0 else None,
                        'pointer': pointer,
                        'expression': expr,
                        'scope': 'explicit-bridge' if explicit else 'normalized-omi-consumer-source-review',
                        'metrics': names,
                        'issues': issues,
                    }
                )
    combined = json.loads((root / 'alert-rules.json').read_text())
    split = {r['uid']: r for p in (root / 'alerts').glob('*.json') for r in json.loads(p.read_text())}
    combined_equal = len(combined) == len(split) and all(split.get(r['uid']) == r for r in combined)
    return {
        'schema_version': 1,
        'source': 'repository, not live Grafana export',
        'combined_equals_split': combined_equal,
        'consumers': entries,
        'counts': {
            'query_consumers': len(entries),
            'explicit_bridge': sum(e['scope'] == 'explicit-bridge' for e in entries),
        },
    }


def validate_mapping(mapping):
    if not mapping.get('id') or not mapping.get('producer'):
        raise Unproven('mapping requires identity and producer')
    for field in ('local_query', 'managed_query'):
        expr = mapping.get(field, '')
        if not expr or '$' in expr or re.search(r'__name__\s*(?:=~|!~|!=)', expr):
            raise Unproven('mapping requires explicit expanded exact-name queries')
        if 'or vector(0)' in expr:
            raise Unproven('zero-fill can hide missing telemetry')
    if mapping['producer'] == 'custom-generic-task' and 'custom.googleapis.com/' not in mapping['managed_query']:
        raise Unproven('custom metric must keep its exact Cloud Monitoring name')
    for key in ('relative_tolerance', 'absolute_tolerance'):
        val = mapping.get(key, 0)
        if not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
            raise Unproven('invalid comparison tolerance')


def matrix(payload):
    if payload.get('status') != 'success' or payload.get('warnings') or payload.get('infos'):
        raise Unproven('API error, warning, or annotation')
    data = payload.get('data', {})
    if data.get('resultType') != 'matrix' or not data.get('result'):
        raise Unproven('empty or non-matrix result')
    result = {}
    for series in data['result']:
        labels = tuple(sorted((k, str(v)) for k, v in series.get('metric', {}).items() if k != '__name__'))
        if labels in result or not series.get('values') or series.get('histograms'):
            raise Unproven('duplicate labels, empty series, or unsupported native histogram')
        values = {}
        for timestamp, raw in series['values']:
            timestamp, val = float(timestamp), float(raw)
            if not math.isfinite(timestamp) or not math.isfinite(val) or timestamp in values:
                raise Unproven('nonfinite or duplicate sample')
            values[timestamp] = val
        result[labels] = values
    return result


def compare(left, right, start, end, step, relative=0.05, absolute=0.001):
    left, right = matrix(left), matrix(right)
    expected = {float(t) for t in range(start, end + 1, step)}
    left_only, right_only = set(left) - set(right), set(right) - set(left)
    missing_left = sum(len(expected - set(v)) for v in left.values())
    missing_right = sum(len(expected - set(v)) for v in right.values())
    unexpected = sum(len(set(v) - expected) for v in list(left.values()) + list(right.values()))
    mismatch, compared, max_relative = 0, 0, 0.0
    for labels in set(left) & set(right):
        for stamp in set(left[labels]) & set(right[labels]):
            a, b = left[labels][stamp], right[labels][stamp]
            delta = abs(a - b)
            max_relative = max(max_relative, delta / max(abs(a), abs(b), absolute, 1e-300))
            mismatch += delta > absolute + relative * max(abs(a), abs(b))
            compared += 1
    passed = not (left_only or right_only or missing_left or missing_right or unexpected or mismatch) and compared > 0
    # Do not print label values, which can contain user-defined payloads.
    return {
        'status': 'matched' if passed else 'mismatch',
        'left_series': len(left),
        'right_series': len(right),
        'left_only_labelsets': len(left_only),
        'right_only_labelsets': len(right_only),
        'missing_left_points': missing_left,
        'missing_right_points': missing_right,
        'unexpected_points': unexpected,
        'compared_points': compared,
        'value_mismatches': mismatch,
        'max_relative_difference': max_relative,
    }


def query_range(base, expr, start, end, step, token=None):
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise Unproven('invalid endpoint')
    if (parsed.hostname or '').rstrip('.') == 'api.omi.me':
        raise Unproven('production application endpoint forbidden')
    if parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise Unproven('plaintext endpoints require loopback port-forward')
    if token and base.rstrip('/') not in (MANAGED_URL, GRAFANA_LOCAL_URL, GRAFANA_MANAGED_URL):
        raise Unproven('credentialed query requires an approved monitoring endpoint')
    params = urllib.parse.urlencode({'query': expr, 'start': start, 'end': end, 'step': step})
    request = urllib.request.Request(base.rstrip('/') + '/api/v1/query_range?' + params)
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=55) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise Unproven('query HTTP status ' + str(exc.code)) from None
    except (OSError, ValueError):
        raise Unproven('query transport or JSON failure') from None


PROD_CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'


def kube_query_range(context, expr, start, end, step):
    if context != PROD_CONTEXT:
        raise Unproven('only the explicitly authorized production context is supported')
    params = urllib.parse.urlencode({'query': expr, 'start': start, 'end': end, 'step': step})
    path = (
        '/api/v1/namespaces/prod-omi-monitoring/services/'
        'prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/query_range?' + params
    )
    try:
        proc = subprocess.run(
            ['kubectl', '--context', context, 'get', '--raw', path], capture_output=True, text=True, timeout=55
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Unproven('Kubernetes read transport failure or timeout') from None
    if proc.returncode:
        raise Unproven('Kubernetes read failed (stderr suppressed)')
    try:
        result = json.loads(proc.stdout)
        matrix(result)
        return result
    except (ValueError, TypeError, KeyError):
        raise Unproven('Kubernetes query returned empty, invalid or error data') from None


def run(args):
    if args.gcloud_token and args.managed_url.rstrip('/') != MANAGED_URL:
        raise Unproven('gcloud credentials require the fixed production Google Monitoring endpoint')
    if args.managed_token_env and (args.gcloud_token or args.managed_url.rstrip('/') != GRAFANA_MANAGED_URL):
        raise Unproven('managed token requires the fixed production Grafana GMP proxy')
    if args.local_token_env and (not args.local_url or args.local_url.rstrip('/') != GRAFANA_LOCAL_URL):
        raise Unproven('local token requires the fixed production Grafana Prometheus proxy')
    mappings = json.loads(Path(args.mappings).read_text())['mappings']
    if args.ids:
        ids = set(args.ids.split(','))
        mappings = [m for m in mappings if m['id'] in ids]
        if {m['id'] for m in mappings} != ids:
            raise Unproven('unknown mapping id')
    if not mappings:
        raise Unproven('no mappings selected')
    if args.hours < 24 or args.step < 60 or args.step > 300 or not math.isfinite(args.hours):
        raise Unproven('shadow requires >=24h and 60..300s steps')
    end = args.end or int(time.time()) - 600
    end -= end % args.step
    start = end - int(args.hours * 3600)
    start -= start % args.step
    report = {'window_start': start, 'window_end': end, 'step': args.step, 'cutover_authorized': False, 'results': []}
    for mapping in mappings:
        row = {'id': mapping['id'], 'producer': mapping['producer']}
        try:
            validate_mapping(mapping)
            if mapping.get('blocked_reason'):
                raise Unproven(mapping['blocked_reason'])
            token = os.environ.get(args.managed_token_env) if args.managed_token_env else None
            if args.managed_token_env and not token:
                raise Unproven('managed token environment is empty')
            if args.gcloud_token:
                proc = subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True)
                if proc.returncode or not proc.stdout.strip():
                    raise Unproven('gcloud read-only credential unavailable')
                token = proc.stdout.strip()
            local_token = os.environ.get(args.local_token_env) if args.local_token_env else None
            if args.local_token_env and not local_token:
                raise Unproven('local token environment is empty')
            if args.kube_context:
                left = kube_query_range(args.kube_context, mapping['local_query'], start, end, args.step)
            else:
                left = query_range(
                    args.local_url,
                    mapping['local_query'],
                    start,
                    end,
                    args.step,
                    local_token,
                )
            right = query_range(args.managed_url, mapping['managed_query'], start, end, args.step, token)
            row.update(
                compare(
                    left,
                    right,
                    start,
                    end,
                    args.step,
                    mapping.get('relative_tolerance', 0.05),
                    mapping.get('absolute_tolerance', 0.001),
                )
            )
        except (Unproven, KeyError, TypeError, ValueError) as exc:
            row.update(
                status='unproven', reason=str(exc) if isinstance(exc, Unproven) else 'malformed result or mapping'
            )
        report['results'].append(row)
    report['status'] = 'matched' if all(r['status'] == 'matched' for r in report['results']) else 'unproven'
    report['mapping_sha256'] = hashlib.sha256(Path(args.mappings).read_bytes()).hexdigest()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--output', required=True)
    parser.add_argument('--mappings', default=str(MAPPINGS))
    local = parser.add_mutually_exclusive_group()
    local.add_argument('--local-url')
    local.add_argument('--kube-context', choices=[PROD_CONTEXT])
    parser.add_argument(
        '--managed-url',
        default=MANAGED_URL,
    )
    parser.add_argument('--local-token-env')
    parser.add_argument('--managed-token-env')
    parser.add_argument(
        '--gcloud-token', action='store_true', help='use active ro-prod gcloud credentials, never print token'
    )
    parser.add_argument('--hours', type=float, default=24)
    parser.add_argument('--end', type=int, help='UTC Unix timestamp; default 10 minutes behind now')
    parser.add_argument('--step', type=int, default=300)
    parser.add_argument('--ids', help='comma-separated exact mapping IDs')
    args = parser.parse_args()
    try:
        if not args.inventory and not (args.local_url or args.kube_context):
            raise Unproven('--local-url or --kube-context required')
        report = inventory() if args.inventory else run(args)
        Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': report.get('status', 'inventory'), 'output': args.output}))
        return 0 if args.inventory or report['status'] == 'matched' else 1
    except (Unproven, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, Unproven) else 'invalid or unreadable input/output'
        print(json.dumps({'status': 'unproven', 'reason': reason}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
