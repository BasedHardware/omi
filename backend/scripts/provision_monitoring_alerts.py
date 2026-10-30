#!/usr/bin/env python3
"""Check or upsert the production Grafana alert export; never delete live rules.

Read-back compares all managed definition fields, including paused state and
notification timing. Runtime IDs and update timestamps are not configuration.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / 'backend/charts/monitoring/alert-rules.json'
FIELDS = (
    'uid',
    'orgID',
    'folderUID',
    'ruleGroup',
    'title',
    'condition',
    'data',
    'noDataState',
    'execErrState',
    'for',
    'keep_firing_for',
    'annotations',
    'labels',
    'isPaused',
    'notification_settings',
    'record',
    'missingSeriesEvalsToResolve',
)
API = '/api/v1/provisioning/alert-rules'
RECEIVER = 'Omi - Services Alerting (Telegram)'
CANARY_UIDS = ('omi-datasource-prometheus', 'omi-datasource-cloud-monitoring', 'omi-datasource-gmp')


def index_rules(payload: object) -> dict[str, dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError('rules must be a nonempty list')
    result = {}
    for rule in payload:
        if not isinstance(rule, dict):
            raise ValueError('each rule must be an object')
        uid = rule.get('uid')
        if not isinstance(uid, str) or not uid or uid in result:
            raise ValueError('missing or duplicate rule UID')
        result[uid] = rule
    return result


# Grafana 13 writes these defaults into every query on save, so readback carries
# them even when the committed source omits them; they are not semantic drift.
QUERY_DEFAULTS = (('queryType', ''),)
MODEL_DEFAULTS = (('intervalMs', 1000), ('maxDataPoints', 43200))
DURATION_UNITS = {'ms': 0.001, 's': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}


def duration_seconds(value: object) -> object:
    # Grafana 13 re-renders notification durations (24h reads back as 1d).
    if not isinstance(value, str):
        return value
    parts = re.fullmatch(r'(?:\d+(?:ms|[smhdw]))+', value) and re.findall(r'(\d+)(ms|[smhdw])', value)
    return sum(int(n) * DURATION_UNITS[u] for n, u in parts) if parts else value


def definition(rule: dict) -> dict:
    # Grafana12.1 nullable semantic fields use null and omission equivalently.
    nullable = {'record', 'missingSeriesEvalsToResolve'}
    return {key: rule[key] for key in FIELDS if key in rule and (key not in nullable or rule[key] is not None)}


def comparable(rule: dict) -> dict:
    """definition() with Grafana's save-time rewrites undone, for readback comparison only.

    Never send this to Grafana: it renders durations as seconds."""
    result = copy.deepcopy(definition(rule))
    for query in result.get('data') or []:
        if not isinstance(query, dict):
            continue
        for key, default in QUERY_DEFAULTS:
            if query.get(key) == default:
                query.pop(key)
        model = query.get('model')
        if isinstance(model, dict):
            for key, default in MODEL_DEFAULTS:
                if model.get(key) == default:
                    model.pop(key)
    settings = result.get('notification_settings')
    if isinstance(settings, dict):
        for key in ('group_wait', 'group_interval', 'repeat_interval'):
            if key in settings:
                settings[key] = duration_seconds(settings[key])
    return result


def load_rules(path: Path) -> dict[str, dict]:
    rules = index_rules(json.loads(path.read_text()))
    sources = []
    for source in sorted((path.parent / 'alerts').glob('*.json')):
        sources.extend(json.loads(source.read_text()))
    if index_rules(sources) != rules:
        raise ValueError('split alert sources differ from combined export')
    for uid, rule in rules.items():
        if not {'folderUID', 'ruleGroup', 'condition', 'data', 'isPaused'} <= rule.keys():
            raise ValueError(f'{uid}: incomplete alert definition')
        if rule.get('labels', {}).get('alert_identity') != uid:
            raise ValueError(f'{uid}: missing stable alert identity')
        if rule.get('notification_settings', {}).get('receiver') != RECEIVER:
            raise ValueError(f'{uid}: unexpected notification receiver')
    return rules


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Grafana:
    def __init__(self, base: str, token: str):
        if base.rstrip('/') != 'https://monitor.omi.me':
            raise ValueError('alert sources are production-specific: expected https://monitor.omi.me')
        self.base, self.token = base.rstrip('/'), token

    def request(self, path: str, body: dict | None = None, method: str = 'GET', *, editable: bool = False):
        headers = {
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        if editable:
            headers['X-Disable-Provenance'] = 'true'
        request = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                data = response.read(8_000_001)
        except urllib.error.HTTPError as exc:
            raise ValueError(f'Grafana {method} {path}: HTTP {exc.code}') from None
        except OSError:
            raise ValueError(f'Grafana {method} {path}: connection failed') from None
        if len(data) > 8_000_000:
            raise ValueError('Grafana response exceeds size limit')
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise ValueError('Grafana response is not JSON') from None

    def rules(self) -> dict[str, dict]:
        payload = self.request(API)
        return {} if payload == [] else index_rules(payload)


def drift(desired: dict[str, dict], live: dict[str, dict]) -> list[str]:
    result = []
    for uid, rule in sorted(desired.items()):
        if uid not in live:
            result.append(f'{uid}: absent')
        else:
            want, have = comparable(rule), comparable(live[uid])
            keys = [key for key in FIELDS if want.get(key) != have.get(key)]
            if keys:
                result.append(f'{uid}: divergent fields: {",".join(keys)}')
    for uid in sorted(live.keys() - desired.keys()):
        result.append(f'{uid}: live but uncommitted (retained)')
    return result


def probe_datasources(api: Grafana, rules: dict[str, dict]) -> list[str]:
    """Read-only query probes; no raw frames or datasource errors are printed."""
    failures = []
    now = int(time.time() * 1000)
    for uid, rule in sorted(rules.items()):
        if not uid.startswith('omi-datasource-') or rule.get('isPaused'):
            continue
        node = rule['data'][0]
        window = node['relativeTimeRange']
        payload = api.request(
            '/api/ds/query',
            {
                'from': str(now - window['from'] * 1000),
                'to': str(now - window['to'] * 1000),
                'queries': [node['model']],
            },
            'POST',
        )
        if not isinstance(payload, dict) or not isinstance(payload.get('results'), dict):
            failures.append(f'{uid}: invalid query response')
            continue
        result = payload['results'].get(node['refId'], {})
        if not isinstance(result, dict) or not isinstance(result.get('frames', []), list):
            failures.append(f'{uid}: invalid query result')
            continue
        last_values = []
        invalid = False
        for frame in result.get('frames', []):
            if (
                not isinstance(frame, dict)
                or not isinstance(frame.get('schema'), dict)
                or not isinstance(frame.get('data'), dict)
            ):
                invalid = True
                continue
            fields, columns = frame.get('schema', {}).get('fields', []), frame.get('data', {}).get('values', [])
            if not isinstance(fields, list) or not isinstance(columns, list) or len(fields) != len(columns):
                invalid = True
                continue
            for field, values in zip(fields, columns):
                if not isinstance(field, dict) or not isinstance(values, list):
                    invalid = True
                    continue
                if field.get('type') == 'number' and values:
                    value = values[-1]
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        last_values.append(value)
                    else:
                        invalid = True
        condition = rule['data'][-1]['model']['conditions'][0]['evaluator']
        if condition['type'] != 'lt':
            raise ValueError('datasource canary probe only supports less-than sentinel thresholds')
        status = result.get('status', 200)
        if invalid or result.get('error') or not isinstance(status, int) or status >= 400 or not last_values:
            failures.append(f'{uid}: query failed or returned no finite sentinel sample')
        elif any(value < condition['params'][0] for value in last_values):
            failures.append(f'{uid}: sentinel is unhealthy')
        else:
            print(f'PROBE OK {uid}: {len(last_values)} finite sentinel field(s)')
    return failures


def reconcile(api: Grafana, desired: dict[str, dict], *, backup: Path | None = None) -> list[str]:
    live = api.rules()
    if backup is None:
        return drift(desired, live)
    needs_canaries = any(rule.get('execErrState') == 'KeepLast' for rule in desired.values())
    canaries = {uid: desired[uid] for uid in CANARY_UIDS if uid in desired}
    if needs_canaries and len(canaries) != len(CANARY_UIDS):
        raise ValueError('KeepLast requires every committed datasource canary')
    for rule in canaries.values():
        if (
            rule.get('isPaused') is not False
            or rule.get('execErrState') != 'Alerting'
            or rule.get('noDataState') != 'Alerting'
        ):
            raise ValueError('datasource canaries must be active and page on errors and no data')
    contacts = api.request('/api/v1/provisioning/contact-points')
    if not isinstance(contacts, list) or not any(
        point.get('name') == RECEIVER
        and point.get('type') == 'telegram'
        and point.get('disableResolveMessage') is not True
        for point in contacts
        if isinstance(point, dict)
    ):
        raise ValueError('Telegram receiver is missing or resolve notifications disabled')
    for folder in sorted({rule['folderUID'] for rule in desired.values()}):
        api.request('/api/folders/' + urllib.parse.quote(folder, safe=''))
    # Grafana forbids mixing API- and UI-provisioned rules in a group. Preserve
    # each existing group's provenance; new groups are API-managed. File-owned
    # resources require their owning provisioner, never partial API takeover.
    provenance = {}
    for rule in live.values():
        group = (rule.get('folderUID'), rule.get('ruleGroup'))
        value = rule.get('provenance', '')
        if group in provenance and provenance[group] != value:
            raise ValueError('live rule group has mixed provenance')
        provenance[group] = value
    planned = []
    for uid, rule in sorted(desired.items()):
        if uid in live and comparable(rule) == comparable(live[uid]):
            continue
        current = live[uid].get('provenance', '') if uid in live else 'api'
        group = (rule['folderUID'], rule['ruleGroup'])
        target = provenance.get(group, current)
        if current not in ('', 'api') or target not in ('', 'api'):
            raise ValueError(f'{uid}: rule or group belongs to another provisioner')
        if uid in live and target != current:
            raise ValueError(f'{uid}: moving rule across provenance boundaries requires separate migration')
        planned.append((uid, rule, target))
    # Exclusive creation refuses symlinks/overwrites and preserves the pre-write state.
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(
            {'rules': list(live.values()), 'created_uids': sorted(desired.keys() - live.keys())}, handle, indent=2
        )
        handle.flush()
        os.fsync(handle.fileno())

    def apply_rules(batch):
        for uid, rule, provenance in batch:
            path = API + '/' + urllib.parse.quote(uid, safe='') if uid in live else API
            api.request(path, definition(rule), 'PUT' if uid in live else 'POST', editable=provenance == '')
            print(f'UPSERTED {uid}')

    # Install and verify replacement pages before any business rule can retain
    # its last state. A failed probe leaves business definitions untouched.
    apply_rules(item for item in planned if item[0] in canaries)
    if canaries:
        current = api.rules()
        failures = [
            f'{uid}: canary readback differs'
            for uid, rule in canaries.items()
            if uid not in current or comparable(current[uid]) != comparable(rule)
        ]
        if failures:
            return failures
        failures = probe_datasources(api, canaries)
        if failures:
            return failures
    apply_rules(item for item in planned if item[0] not in canaries)
    return drift(desired, api.rules())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rules', type=Path, default=RULES)
    parser.add_argument('--grafana-url', default='https://monitor.omi.me')
    parser.add_argument('--token-env', default='MONITOR_GRAFANA_TOKEN')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-file', type=Path)
    parser.add_argument('--lint', action='store_true')
    parser.add_argument('--probe-datasources', action='store_true', help='read-only canary queries through Grafana')
    args = parser.parse_args()
    try:
        rules = load_rules(args.rules)
        if args.probe_datasources and (args.lint or args.apply or args.backup_file):
            raise ValueError('datasource probes are read-only and cannot be combined with other modes')
        if args.lint:
            print(f'Validated {len(rules)} combined/split production alert definitions')
            return 0
        if args.apply != (args.backup_file is not None):
            raise ValueError('--apply requires --backup-file; backup is forbidden for read-only checks')
        token = os.environ.get(args.token_env, '').strip()
        if not token:
            raise ValueError(f'{args.token_env} is empty')
        api = Grafana(args.grafana_url, token)
        differences = (
            probe_datasources(api, rules) if args.probe_datasources else reconcile(api, rules, backup=args.backup_file)
        )
        for difference in differences:
            print('DRIFT ' + difference)
        if differences:
            return 1
        print(
            'Canary query probes passed'
            if args.probe_datasources
            else f'Verified {len(rules)} production alert definitions; no drift'
        )
        return 0
    except (ValueError, OSError):
        # Do not expose API bodies, credentials, annotations, or local file contents.
        exc = sys.exc_info()[1]
        print(f'FAIL: {exc}' if isinstance(exc, ValueError) else 'FAIL: local file operation failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
