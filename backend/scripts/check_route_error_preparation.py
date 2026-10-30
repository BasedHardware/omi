#!/usr/bin/env python3
"""Offline bounded-label checks and optional read-only descriptor verification."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'charts/monitoring/route-errors'
METRICS = ('omi_cloud_run_request_5xx', 'omi_cloud_run_long_504', 'omi_cloud_run_sync_poll_429')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def extract(expression, value):
    match = re.fullmatch(r'REGEXP_EXTRACT\(httpRequest\.requestUrl, ("(?:\\.|[^"\\])*")\)', expression)
    if not match:
        raise ValueError('unsupported extractor')
    pattern = re.compile(json.loads(match[1]))
    if pattern.groups != 1:
        raise ValueError('extractor must contain one capture group')
    result = pattern.search(value)
    return result.group(1) if result else ''


def lint():
    errors = []
    for name in METRICS:
        metric = json.loads((ROOT / (name + '.json')).read_text())
        if 'resource.labels.service_name=' in metric['filter']:
            errors.append(name + ': must cover every service name')
        if 'run.googleapis.com%2Frequests' not in metric['filter']:
            errors.append(name + ': requires platform request log')
        keys = {x['key'] for x in metric['metricDescriptor']['labels']}
        if keys != set(metric.get('labelExtractors', {})) or keys - {'route', 'action'}:
            errors.append(name + ': unsafe or inconsistent labels')
        for key, expression in metric.get('labelExtractors', {}).items():
            # Exercise both registered families and varied data; outputs must stay finite.
            for suffix in (
                'models/example:batchEmbedContents',
                'models/private-id:unknown',
                'anything/secret:generateContent?key=redacted',
                'models/a:embedContent',
                'models/a:streamGenerateContent',
            ):
                for family in ('gemini', 'gemini-stream', 'gemini-unknown'):
                    value = extract(expression, 'https://example.invalid/v1/proxy/' + family + '/' + suffix)
                    allowed = (
                        {'', '/v1/proxy/gemini', '/v1/proxy/gemini-stream'}
                        if key == 'route'
                        else {'', 'batchEmbedContents', 'embedContent', 'generateContent', 'streamGenerateContent'}
                    )
                    if value not in allowed:
                        errors.append(name + ': unbounded extraction')
    for rule in json.loads((ROOT / 'grafana-candidates.json').read_text()):
        if not rule.get('isPaused') or not rule.get('annotations', {}).get('admission_hold'):
            errors.append(rule['uid'] + ': candidate must remain held')
        for node in rule['data']:
            if node['datasourceUid'] not in ('gmp-cloud-run', '__expr__'):
                errors.append(rule['uid'] + ': metric datasource only')
            if re.search(r'__name__\s*(?:=~|!~|!=)', node['model'].get('expr', '')):
                errors.append(rule['uid'] + ': exact metric names required')
    return errors


def descriptor_shape(expected, actual, *, monitoring=False):
    """Compare metric semantics, including the bounded string-label contract."""
    if not isinstance(actual, dict):
        return False
    for key in ('metricKind', 'valueType', 'unit'):
        if actual.get(key) != expected.get(key):
            return False
    labels = actual.get('labels', [])
    if not isinstance(labels, list) or any(not isinstance(label, dict) for label in labels):
        return False
    actual_types = {label.get('key'): label.get('valueType', 'STRING') for label in labels}
    expected_types = {label['key']: label.get('valueType', 'STRING') for label in expected['labels']}
    if len(actual_types) != len(labels) or not all(actual_types.get(k) == v for k, v in expected_types.items()):
        return False
    if not monitoring and actual_types != expected_types:
        return False
    return not monitoring or 'cloud_run_revision' in actual.get('monitoredResourceTypes', [])


def verify_live():
    """Metadata GETs only. Never log API bodies, credential material or label values."""
    proc = subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True, timeout=30)
    if proc.returncode or not proc.stdout.strip():
        return [{'status': 'unproven', 'reason': 'read-only credentials unavailable'}]
    token = proc.stdout.strip()
    results = []
    for name in METRICS:
        row = {'metric': name, 'status': 'unproven'}
        try:
            definition = json.loads((ROOT / (name + '.json')).read_text())
            url = 'https://logging.googleapis.com/v2/projects/based-hardware/metrics/' + name
            request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                live = json.load(response)
            url = (
                'https://monitoring.googleapis.com/v3/projects/based-hardware/metricDescriptors/'
                'logging.googleapis.com/user/' + name
            )
            request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                descriptor = json.load(response)
            same = all(live.get(k, {}) == definition.get(k, {}) for k in ('filter', 'labelExtractors'))
            correct = (
                descriptor_shape(definition['metricDescriptor'], live.get('metricDescriptor'))
                and descriptor_shape(definition['metricDescriptor'], descriptor, monitoring=True)
                and not live.get('disabled', False)
            )
            row.update(
                status='definition-matched' if same and correct else 'unproven',
                filter_and_extractors_match=same,
                descriptor_shape_matches=correct,
            )
        except urllib.error.HTTPError as exc:
            row['reason'] = 'HTTP ' + str(exc.code) + (' absent metric/descriptor' if exc.code == 404 else '')
        except (OSError, ValueError):
            row['reason'] = 'metadata read or JSON failure'
        results.append(row)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-live', action='store_true', help='read-only metadata; select ro-prod first')
    parser.add_argument('--output')
    args = parser.parse_args()
    failures = lint()
    result = {
        'status': 'offline-valid' if not failures else 'failed',
        'failures': failures,
        'admission_authorized': False,
    }
    if args.verify_live:
        result['live_metadata'] = verify_live()
        result['status'] = (
            'metadata-matched'
            if not failures and all(r['status'] == 'definition-matched' for r in result['live_metadata'])
            else 'unproven'
        )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in ('offline-valid', 'metadata-matched') else 1


if __name__ == '__main__':
    raise SystemExit(main())
