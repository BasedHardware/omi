#!/usr/bin/env python3
"""Offline same-LB-log storm partition contract. No auth, network or apply mode."""

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / 'charts/monitoring/route-errors'
LOG_NAME = 'projects/based-hardware/logs/requests'
# Only canonical UUID-shaped jobs produced by sync.py/sync_jobs.py qualify.
# Encoded/slashed/noncanonical paths conservatively remain in the nonstorm set.
STORM_URL = (
    r'^https://api[.]omi[.]me/v2/sync-local-files/'
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:[?][^#]*)?$'
)


def atom(field, operation, value):
    return {'field': field, 'operation': operation, 'value': value}


STREAM = {
    'all': [
        atom('resource.type', '=', 'http_load_balancer'),
        atom('resource.labels.project_id', '=', 'based-hardware'),
        atom('logName', '=', LOG_NAME),
    ]
}
STORM = {
    'all': [
        atom('httpRequest.requestMethod', '=~', '^GET$'),
        atom('httpRequest.status', '=', 429),
        atom('httpRequest.requestUrl', '=~', STORM_URL),
    ]
}
BASES = {
    '4xx': {'all': [STREAM, atom('httpRequest.status', '>=', 400), atom('httpRequest.status', '<', 500)]},
    'armor_deny': {
        'all': [
            STREAM,
            {
                'any': [
                    atom('jsonPayload.enforcedSecurityPolicy.outcome', '=~', '^DENY$'),
                    atom('jsonPayload.enforcedEdgeSecurityPolicy.outcome', '=~', '^DENY$'),
                    atom(
                        'jsonPayload.statusDetails',
                        '=~',
                        '^(denied_by_security_policy|body_denied_by_security_policy)$',
                    ),
                ]
            },
        ]
    },
}
NAMES = {(family, part): 'omi_edge_' + family + '_' + part for family in BASES for part in ('storm', 'nonstorm')}


def predicate(family, part):
    return {'all': [BASES[family], STORM if part == 'storm' else {'not': STORM}]}


def render(node):
    if 'all' in node or 'any' in node:
        key = 'all' if 'all' in node else 'any'
        return '(' + (' AND ' if key == 'all' else ' OR ').join(render(n) for n in node[key]) + ')'
    if 'not' in node:
        return 'NOT (' + render(node['not']) + ')'
    return node['field'] + ' ' + node['operation'] + ' ' + json.dumps(node['value'])


def matches(node, entry):
    """Synthetic Boolean contract model, not a Cloud Logging query interpreter."""
    if 'all' in node:
        return all(matches(n, entry) for n in node['all'])
    if 'any' in node:
        return any(matches(n, entry) for n in node['any'])
    if 'not' in node:
        return not matches(node['not'], entry)
    value = entry
    for key in node['field'].split('.'):
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    operation, expected = node['operation'], node['value']
    if operation == '=~':
        return isinstance(value, str) and re.search(expected, value) is not None
    if operation == '=':
        return value == expected
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return value >= expected if operation == '>=' else value < expected


def definition(family, part):
    return {
        'description': (
            'HELD preparation: project-level emitted LB log entries only; '
            + family
            + ' '
            + part
            + '. No URL/ID labels; resource labels inherited. Sampling/coverage calibration required.'
        ),
        'filter': render(predicate(family, part)),
        'metricDescriptor': {'metricKind': 'DELTA', 'valueType': 'INT64', 'unit': '1', 'labels': []},
        'labelExtractors': {},
    }


def metric_fingerprint():
    payload = {name: definition(family, part) for (family, part), name in NAMES.items()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def calibration_failures(plan, receipt):
    failures = []
    if not isinstance(receipt, dict):
        return ['same-LB-stream sampling/coverage receipt missing']
    if receipt.get('metric_set_sha256') != metric_fingerprint():
        failures.append('receipt metric/filter fingerprint differs')
    if receipt.get('resource_type') != 'http_load_balancer' or receipt.get('log_name') != LOG_NAME:
        failures.append('receipt is not the same LB request-log stream')
    for key in (
        'coverage_verified',
        'partition_identity_verified',
        'project_metric_scope',
        'not_derived_from_cloud_run_or_stored_sample',
    ):
        if receipt.get(key) is not True:
            failures.append(key + ' must be verified')
    fingerprint = receipt.get('source_sampling_fingerprint', '')
    if not isinstance(fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', fingerprint):
        failures.append('source sampling fingerprint missing')
    if receipt.get('calibration_sampling_fingerprint') != fingerprint:
        failures.append('calibration and coverage sampling differ')
    sources = receipt.get('backend_sources')
    if not isinstance(sources, list) or not sources:
        failures.append('backend source inventory missing')
    else:
        names = set()
        for source in sources:
            if (
                not isinstance(source, dict)
                or not source.get('backend_service_name')
                or source.get('logging_enabled') is not True
                or not positive(source.get('sample_rate'))
                or source['sample_rate'] > 1
                or not isinstance(source['backend_service_name'], str)
                or source['backend_service_name'] in names
            ):
                failures.append('backend logging/sampling inventory invalid')
                break
            names.add(source['backend_service_name'])
    try:
        start = datetime.fromisoformat(receipt['utc_start'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(receipt['utc_end'].replace('Z', '+00:00'))
        if start.utcoffset() is None or end.utcoffset() is None or (end - start).total_seconds() < 86400:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        failures.append('fixed timezone-aware coverage window must span at least 24h')
    plan_calibration = plan.get('calibration')
    receipt_calibration = receipt.get('calibration')
    if not isinstance(plan_calibration, dict) or not isinstance(receipt_calibration, dict):
        return failures + ['calibration objects missing']
    for family in BASES:
        calibrated = plan_calibration.get(family, {})
        if not isinstance(calibrated, dict):
            failures.append(family + ': calibration object missing')
            continue
        floor, ceiling, escalation = (
            calibrated.get(key)
            for key in ('storm_floor_per_minute', 'observed_storm_ceiling_per_minute', 'escalation_per_minute')
        )
        if not all(positive(v) for v in (floor, ceiling, escalation)):
            failures.append(family + ': positive finite calibrated floor, ceiling and escalation required')
        elif not floor <= ceiling < escalation:
            failures.append(family + ': require floor <= observed ceiling < escalation')
        actual = receipt_calibration.get(family, {})
        if not isinstance(actual, dict) or actual != calibrated or actual.get('reviewed') is not True:
            failures.append(family + ': calibration must match reviewed same-sampling receipt')
    return failures


def lint():
    failures = []
    for (family, part), name in NAMES.items():
        path = ROOT / ('edge-' + family + '-' + part + '.json')
        if json.loads(path.read_text()) != definition(family, part):
            failures.append(name + ': definition differs from bounded partition contract')
    plan = json.loads((ROOT / 'edge-storm-plan.json').read_text())
    if (
        plan.get('state') != 'held'
        or plan.get('auto_apply') is not False
        or plan.get('admission_authorized') is not False
    ):
        failures.append('plan must remain held and cannot auto-apply')
    storm = plan.get('storm_predicate', {})
    if (
        storm.get('method') != 'GET'
        or storm.get('http_status') != 429
        or storm.get('url_regex') != STORM_URL
        or storm.get('static_route') != '/v2/sync-local-files/{job_id}'
    ):
        failures.append('plan storm cohort differs from reviewed GET429 UUID status route')
    expected = {family: {part: name for (f, part), name in NAMES.items() if f == family} for family in BASES}
    if plan.get('families') != expected:
        failures.append('plan metric families differ from partition definitions')
    if plan.get('metric_set_sha256') != metric_fingerprint():
        failures.append('plan metric fingerprint differs')
    if plan.get('existing_rules_action') != 'unchanged-until-separate-reviewed-cutover':
        failures.append('existing broad alerts must remain unchanged')
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--receipt', type=Path, help='validate a reviewed local calibration receipt; no admission/write'
    )
    args = parser.parse_args()
    try:
        failures = lint()
        calibration = ['not requested; plan remains held']
        if args.receipt:
            plan = json.loads((ROOT / 'edge-storm-plan.json').read_text())
            calibration = calibration_failures(plan, json.loads(args.receipt.read_text()))
        print(
            json.dumps(
                {
                    'status': 'invalid' if failures or (args.receipt and calibration) else 'prepared-held',
                    'failures': failures,
                    'calibration_failures': calibration,
                    'admission_authorized': False,
                    'auto_apply': False,
                },
                indent=2,
            )
        )
        return int(bool(failures or (args.receipt and calibration)))
    except (OSError, ValueError, TypeError, KeyError):
        print('{"status":"invalid","reason":"preparation or receipt invalid","admission_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
