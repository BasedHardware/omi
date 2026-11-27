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

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redis_pager_route import (  # noqa: E402
    CONTACT_POINTS_PATH,
    POLICIES_PATH,
    REDIS_PAGER_UID,
    TELEGRAM_RECEIVER as RECEIVER,
    redis_contact_error,
    redis_receiver_scope_error,
    rule_route_error,
    validate_publisher_url,
)

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
SONIOX_DAILY_HOURS_UID = 'omi-batch-soniox-daily-hours'
APP_ALERT_RULES_API = '/apis/rules.alerting.grafana.app/v1beta1/namespaces/default/alertrules'
CANARY_UIDS = ('omi-datasource-prometheus', 'omi-datasource-cloud-monitoring', 'omi-datasource-gmp')
EXPRESSION_DATASOURCES = ('__expr__', '-100')


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
# Grafana's NotificationSettings marks these lists `omitempty`, so an empty list
# is dropped on save and readback omits the key. Empty and absent are the same
# setting: an empty group_by inherits the parent group, and no mute/active
# interval is no interval.
NOTIFICATION_LIST_DEFAULTS = ('group_by', 'mute_time_intervals', 'active_time_intervals')
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
        for key in NOTIFICATION_LIST_DEFAULTS:
            if key in settings and settings[key] == []:
                settings.pop(key)
        for key in ('group_wait', 'group_interval', 'repeat_interval'):
            if key in settings:
                settings[key] = duration_seconds(settings[key])
    return result


def regenerate_export(path: Path) -> None:
    """Offline only: preserve existing rule order, append new UIDs in split-source order."""
    sources = []
    for source in sorted((path.parent / 'alerts').glob('*.json')):
        sources.extend(json.loads(source.read_text()))
    indexed = index_rules(sources)
    previous = index_rules(json.loads(path.read_text())) if path.exists() else {}
    ordered = [indexed.pop(uid) for uid in previous if uid in indexed]
    ordered.extend(indexed.values())
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + '\n')


def invalid_query_windows(rule: dict) -> list[str]:
    """Grafana rejects an empty relative time range on a datasource-backed query.

    Grafana's ``AlertQuery.PreSave`` accepts a query when it is an expression or
    when ``relativeTimeRange.from`` is strictly greater than ``to``. A ``0s`` to
    ``0s`` window on a real datasource fails provisioning with
    ``invalid relative time range [From: 0s, To: 0s]`` (SCA-2055/SCA-2062), so
    reject it offline before any API call.
    """
    errors = []
    for query in rule.get('data') or []:
        if not isinstance(query, dict) or query.get('datasourceUid') in EXPRESSION_DATASOURCES:
            continue
        window = query.get('relativeTimeRange')
        start = window.get('from') if isinstance(window, dict) else None
        end = window.get('to') if isinstance(window, dict) else None
        numeric = all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (start, end))
        if not numeric or start <= end:
            errors.append(
                f'{rule.get("uid")}: query {query.get("refId")} has an invalid relative time range '
                f'[From: {start}, To: {end}]; a datasource query needs from > to'
            )
    return errors


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
        if error := rule_route_error(uid, rule):
            raise ValueError(error)
    errors = [error for rule in rules.values() for error in invalid_query_windows(rule)]
    if errors:
        raise ValueError('\n'.join(errors))
    return rules


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Grafana:
    def __init__(self, base: str, token: str):
        if base.rstrip('/') != 'https://monitor.omi.me':
            raise ValueError('alert sources are production-specific: expected https://monitor.omi.me')
        self.base, self.token = base.rstrip('/'), token

    def request(
        self,
        path: str,
        body: dict | None = None,
        method: str = 'GET',
        *,
        editable: bool = False,
        allow_not_found: bool = False,
    ):
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
            if allow_not_found and exc.code == 404:
                return None
            raise ValueError(f'Grafana {method} {path}: HTTP {exc.code}') from None
        except OSError:
            raise ValueError(f'Grafana {method} {path}: connection failed') from None
        if len(data) > 8_000_000:
            raise ValueError('Grafana response exceeds size limit')
        try:
            return json.loads(data) if data else None
        except (ValueError, UnicodeError):
            raise ValueError('Grafana response is not JSON') from None

    def rules(self) -> dict[str, dict]:
        payload = self.request(API)
        return {} if payload == [] else index_rules(payload)

    def app_alert_rules(self) -> list[dict]:
        payload = self.request(APP_ALERT_RULES_API + '?limit=1')
        if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
            raise ValueError('Grafana App Platform alert-rule API returned an invalid list')
        return payload['items']

    def app_alert_rule(self, uid: str) -> dict | None:
        resource = self.request(
            APP_ALERT_RULES_API + '/' + urllib.parse.quote(uid, safe=''),
            allow_not_found=True,
        )
        if resource is None:
            return None
        metadata = resource.get('metadata') if isinstance(resource, dict) else None
        if (
            not isinstance(resource, dict)
            or resource.get('kind') != 'AlertRule'
            or not isinstance(metadata, dict)
            or metadata.get('name') != uid
            or not isinstance(metadata.get('resourceVersion'), str)
            or not metadata['resourceVersion']
            or not isinstance(resource.get('spec'), dict)
        ):
            raise ValueError(f'{uid}: Grafana App Platform returned an invalid alert resource')
        return resource


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


def _app_rule_semantics(resource: dict) -> dict:
    """Drop only server-maintained metadata before comparing App Platform objects."""
    result = copy.deepcopy(resource)
    result.pop('status', None)
    metadata = result.get('metadata')
    if not isinstance(metadata, dict):
        return result
    for key in ('namespace', 'uid', 'resourceVersion', 'generation', 'creationTimestamp', 'managedFields'):
        metadata.pop(key, None)
    annotations = metadata.get('annotations')
    if isinstance(annotations, dict):
        for key in ('grafana.app/createdBy', 'grafana.app/updatedBy', 'grafana.app/updatedTimestamp'):
            annotations.pop(key, None)
    return result


def _rule_group_interval(api: Grafana, rule: dict) -> str:
    path = (
        '/api/v1/provisioning/folder/'
        + urllib.parse.quote(rule['folderUID'], safe='')
        + '/rule-groups/'
        + urllib.parse.quote(rule['ruleGroup'], safe='')
    )
    group = api.request(path)
    interval = group.get('interval') if isinstance(group, dict) else None
    if isinstance(interval, int) and not isinstance(interval, bool) and interval > 0:
        return f'{interval}s'
    if isinstance(interval, str) and interval.strip():
        return interval.strip()
    raise ValueError(f'{rule["ruleGroup"]}: could not read the Grafana rule-group interval')


def _app_alert_resource(
    rule: dict,
    interval: str,
    existing: dict | None = None,
    *,
    provenance: str = 'api',
) -> dict:
    metadata = {'name': rule['uid']}
    annotations = {}
    labels = {}
    if existing is not None:
        current_metadata = existing.get('metadata', {})
        annotations = copy.deepcopy(current_metadata.get('annotations', {}))
        labels = copy.deepcopy(current_metadata.get('labels', {}))
        if not isinstance(annotations, dict) or not isinstance(labels, dict):
            raise ValueError(f'{rule["uid"]}: malformed Grafana resource metadata')
        for key in ('grafana.app/createdBy', 'grafana.app/updatedBy', 'grafana.app/updatedTimestamp'):
            annotations.pop(key, None)
        metadata['resourceVersion'] = current_metadata['resourceVersion']
    annotations['grafana.app/folder'] = rule['folderUID']
    if provenance == 'api':
        annotations['grafana.com/provenance'] = 'api'
    elif provenance == '':
        annotations.pop('grafana.com/provenance', None)
    else:
        raise ValueError(f'{rule["uid"]}: rule belongs to another provisioner')
    metadata['annotations'] = annotations
    if labels:
        metadata['labels'] = labels

    expressions = {}
    for query in rule.get('data') or []:
        ref_id = query.get('refId')
        if not isinstance(ref_id, str) or not ref_id or ref_id in expressions:
            raise ValueError(f'{rule["uid"]}: invalid or duplicate expression reference')
        expression = {}
        if 'queryType' in query:
            expression['queryType'] = query['queryType']
        if 'datasourceUid' in query:
            expression['datasourceUID'] = query['datasourceUid']
        relative_range = query.get('relativeTimeRange')
        if isinstance(relative_range, dict):
            converted = {}
            for side in ('from', 'to'):
                value = relative_range.get(side)
                if isinstance(value, int) and not isinstance(value, bool):
                    converted[side] = f'{value}s'
                elif isinstance(value, str) and value:
                    converted[side] = value
                else:
                    raise ValueError(f'{rule["uid"]}: invalid expression time range')
            expression['relativeTimeRange'] = converted
        model = query.get('model')
        if not isinstance(model, dict):
            raise ValueError(f'{rule["uid"]}: expression model is missing')
        expression['model'] = copy.deepcopy(model)
        if ref_id == rule.get('condition'):
            expression['source'] = True
        expressions[ref_id] = expression
    if not expressions or rule.get('condition') not in expressions:
        raise ValueError(f'{rule["uid"]}: alert condition does not identify an expression')

    spec = {
        'title': rule['title'],
        'trigger': {'interval': interval},
        'expressions': expressions,
    }
    for source, target in (
        ('for', 'for'),
        ('keep_firing_for', 'keepFiringFor'),
        ('noDataState', 'noDataState'),
        ('execErrState', 'execErrState'),
        ('isPaused', 'paused'),
        ('labels', 'labels'),
        ('annotations', 'annotations'),
    ):
        if source in rule and rule[source] is not None:
            spec[target] = copy.deepcopy(rule[source])
    notification = rule.get('notification_settings')
    if isinstance(notification, dict):
        settings = {'type': 'SimplifiedRouting'}
        for source, target in (
            ('receiver', 'receiver'),
            ('group_by', 'groupBy'),
            ('group_wait', 'groupWait'),
            ('group_interval', 'groupInterval'),
            ('repeat_interval', 'repeatInterval'),
            ('mute_time_intervals', 'muteTimeIntervals'),
            ('active_time_intervals', 'activeTimeIntervals'),
        ):
            if source in notification:
                settings[target] = copy.deepcopy(notification[source])
        spec['notificationSettings'] = settings

    return {
        'apiVersion': 'rules.alerting.grafana.app/v1beta1',
        'kind': 'AlertRule',
        'metadata': metadata,
        'spec': spec,
    }


def _write_soniox_snapshot(path: Path, snapshot: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(snapshot, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def prepare_soniox_alert(
    api: Grafana,
    desired: dict,
    canary_rules: dict[str, dict],
    backup: Path,
    *,
    source_sha: str,
    source_run_id: str,
) -> None:
    """Read and persist the preimage. This mode performs no Grafana writes."""
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha) or not re.fullmatch(r'[1-9][0-9]*', source_run_id):
        raise ValueError('Soniox preparation requires a full source SHA and positive workflow run ID')
    uid = SONIOX_DAILY_HOURS_UID
    rule = desired.get(uid)
    if not isinstance(rule, dict):
        raise ValueError(f'{uid}: committed alert is missing')

    # Check the versioned API before saving a rollback artifact. Release must
    # separately confirm unified alert-rule storage: legacy storage can ignore
    # resourceVersion even when this API endpoint is present.
    api.app_alert_rules()
    legacy_live = api.rules()
    previous = api.app_alert_rule(uid)
    if (uid in legacy_live) != (previous is not None):
        raise ValueError(f'{uid}: legacy and versioned Grafana APIs disagree; refusing to prepare')
    if previous is not None:
        previous_annotations = previous['metadata'].get('annotations', {})
        if previous_annotations.get('grafana.app/folder') != rule['folderUID']:
            raise ValueError(f'{uid}: existing rule is in a different folder')
        trigger = previous.get('spec', {}).get('trigger')
        interval = trigger.get('interval') if isinstance(trigger, dict) else None
        if not isinstance(interval, str) or not interval:
            raise ValueError(f'{uid}: existing rule has no evaluation interval')
    else:
        interval = _rule_group_interval(api, rule)

    group = (rule['folderUID'], rule['ruleGroup'])
    group_provenance = None
    for live_rule in legacy_live.values():
        if (live_rule.get('folderUID'), live_rule.get('ruleGroup')) != group:
            continue
        current_provenance = live_rule.get('provenance', '')
        if current_provenance not in ('', 'api'):
            raise ValueError(f'{uid}: rule group belongs to another provisioner')
        if group_provenance is not None and current_provenance != group_provenance:
            raise ValueError(f'{uid}: live rule group has mixed provenance')
        group_provenance = current_provenance
    target_provenance = group_provenance if group_provenance is not None else 'api'

    # Reuse the same receiver, folder, provenance, and canary gates as the
    # existing provisioner before producing an artifact for a production run.
    contacts = api.request(CONTACT_POINTS_PATH)
    if not isinstance(contacts, list) or not any(
        point.get('name') == RECEIVER
        and point.get('type') == 'telegram'
        and point.get('disableResolveMessage') is not True
        for point in contacts
        if isinstance(point, dict)
    ):
        raise ValueError('Telegram receiver is missing or resolve notifications disabled')
    api.request('/api/folders/' + urllib.parse.quote(rule['folderUID'], safe=''))
    if rule.get('execErrState') == 'KeepLast':
        canaries = {key: canary_rules[key] for key in CANARY_UIDS if key in canary_rules}
        if len(canaries) != len(CANARY_UIDS):
            raise ValueError('KeepLast requires every committed datasource canary')
        for canary in canaries.values():
            if (
                canary.get('isPaused') is not False
                or canary.get('execErrState') != 'Alerting'
                or canary.get('noDataState') != 'Alerting'
            ):
                raise ValueError('datasource canaries must be active and page on errors and no data')
        failures = probe_datasources(api, canaries)
        if failures:
            raise ValueError('\n'.join(failures))

    desired_resource = _app_alert_resource(rule, interval, previous, provenance=target_provenance)
    _write_soniox_snapshot(
        backup,
        {
            'schema_version': 2,
            'source_sha': source_sha,
            'source_run_id': source_run_id,
            'rules': [legacy_live[uid]] if uid in legacy_live else [],
            'created_uids': [] if previous is not None else [uid],
            'soniox_alert_rollback': {
                'uid': uid,
                'desired': definition(rule),
                'previous_resource': previous,
                'desired_resource': desired_resource,
            },
        },
    )


def apply_soniox_snapshot(api: Grafana, snapshot: dict, expected_desired: dict) -> None:
    rollback = snapshot['soniox_alert_rollback']
    uid = rollback['uid']
    if definition(expected_desired) != rollback['desired']:
        raise ValueError('committed Soniox definition differs from the uploaded pre-apply snapshot')
    previous = rollback['previous_resource']
    desired = copy.deepcopy(rollback['desired_resource'])
    current = api.app_alert_rule(uid)
    path = APP_ALERT_RULES_API + '/' + urllib.parse.quote(uid, safe='')
    if previous is None:
        if current is not None:
            raise ValueError('live Soniox rule changed since the pre-apply snapshot; refusing to create')
        api.request(APP_ALERT_RULES_API, desired, 'POST')
    else:
        captured_version = previous['metadata']['resourceVersion']
        if (
            current is None
            or current['metadata']['resourceVersion'] != captured_version
            or _app_rule_semantics(current) != _app_rule_semantics(previous)
        ):
            raise ValueError('live Soniox rule changed since the pre-apply snapshot; refusing to update')
        desired['metadata']['resourceVersion'] = captured_version
        api.request(path, desired, 'PUT')

    applied = api.app_alert_rule(uid)
    if applied is None or _app_rule_semantics(applied) != _app_rule_semantics(rollback['desired_resource']):
        raise ValueError('Soniox alert read-back differs from the requested versioned resource')


def load_soniox_snapshot(path: Path, expected_sha: str, expected_run_id: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', expected_sha) or not re.fullmatch(r'[1-9][0-9]*', expected_run_id):
        raise ValueError('expected Soniox snapshot coordinates are invalid')
    if path.stat().st_size > 16_000_000:
        raise ValueError('Soniox snapshot exceeds size limit')
    snapshot = json.loads(path.read_text())
    rollback = snapshot.get('soniox_alert_rollback') if isinstance(snapshot, dict) else None
    if (
        not isinstance(snapshot, dict)
        or snapshot.get('schema_version') != 2
        or snapshot.get('source_sha') != expected_sha
        or str(snapshot.get('source_run_id')) != expected_run_id
        or not isinstance(rollback, dict)
        or rollback.get('uid') != SONIOX_DAILY_HOURS_UID
        or not isinstance(rollback.get('desired'), dict)
        or not isinstance(rollback.get('desired_resource'), dict)
        or (rollback.get('previous_resource') is not None and not isinstance(rollback.get('previous_resource'), dict))
    ):
        raise ValueError('Soniox snapshot does not match this source run or supported schema')
    return snapshot


def reconcile(
    api: Grafana,
    desired: dict[str, dict],
    *,
    backup: Path | None = None,
    source_sha: str = '',
    source_run_id: str = '',
    soniox_alert_only: bool = False,
    canary_rules: dict[str, dict] | None = None,
) -> list[str]:
    if soniox_alert_only and backup is not None:
        raise ValueError('Soniox writes require prepare, artifact upload, and versioned apply steps')
    live = api.rules()
    # The Redis phone cutover has its own approval and readback scope.
    bulk_desired = {uid: rule for uid, rule in desired.items() if uid != REDIS_PAGER_UID}
    if backup is None:
        observed = (
            {uid: rule for uid, rule in live.items() if uid in bulk_desired}
            if soniox_alert_only
            else {uid: rule for uid, rule in live.items() if uid != REDIS_PAGER_UID}
        )
        return drift(bulk_desired, observed)
    needs_canaries = any(rule.get('execErrState') == 'KeepLast' for rule in bulk_desired.values())
    canary_source = canary_rules if canary_rules is not None else desired
    canaries = {uid: canary_source[uid] for uid in CANARY_UIDS if uid in canary_source}
    if needs_canaries and len(canaries) != len(CANARY_UIDS):
        raise ValueError('KeepLast requires every committed datasource canary')
    for rule in canaries.values():
        if (
            rule.get('isPaused') is not False
            or rule.get('execErrState') != 'Alerting'
            or rule.get('noDataState') != 'Alerting'
        ):
            raise ValueError('datasource canaries must be active and page on errors and no data')
    contacts = api.request(CONTACT_POINTS_PATH)
    if not isinstance(contacts, list) or not any(
        point.get('name') == RECEIVER
        and point.get('type') == 'telegram'
        and point.get('disableResolveMessage') is not True
        for point in contacts
        if isinstance(point, dict)
    ):
        raise ValueError('Telegram receiver is missing or resolve notifications disabled')
    for folder in sorted({rule['folderUID'] for rule in bulk_desired.values()}):
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
    for uid, rule in sorted(bulk_desired.items()):
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
        snapshot_rules = (
            [live[uid] for uid in bulk_desired if uid in live] if soniox_alert_only else list(live.values())
        )
        snapshot = {
            'schema_version': 1,
            'source_sha': source_sha,
            'source_run_id': str(source_run_id),
            'rules': snapshot_rules,
            'created_uids': sorted(bulk_desired.keys() - live.keys()),
        }
        if soniox_alert_only:
            snapshot['soniox_alert_rollback'] = {
                'uid': SONIOX_DAILY_HOURS_UID,
                'desired': definition(bulk_desired[SONIOX_DAILY_HOURS_UID]),
            }
        json.dump(snapshot, handle, indent=2)
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
    current = api.rules()
    bulk_live = (
        {uid: current[uid] for uid in bulk_desired if uid in current}
        if soniox_alert_only
        else {uid: rule for uid, rule in current.items() if uid != REDIS_PAGER_UID}
    )
    return drift(bulk_desired, bulk_live)


def check_redis_pilot(
    api: Grafana, rules: dict[str, dict], publisher_url: str, alias_hosts: tuple[str, ...] = ()
) -> list[str]:
    validate_publisher_url(publisher_url)
    desired = rules.get(REDIS_PAGER_UID)
    if desired is None:
        raise ValueError('committed Redis pilot rule is missing')
    if error := redis_contact_error(api.request(CONTACT_POINTS_PATH), publisher_url, alias_hosts):
        return [error]
    current = api.rules()
    if error := redis_receiver_scope_error(current, api.request(POLICIES_PATH)):
        return [error]
    return drift({REDIS_PAGER_UID: desired}, {uid: rule for uid, rule in current.items() if uid == REDIS_PAGER_UID})


def select_rules(rules: dict[str, dict], *, soniox_alert_only: bool) -> dict[str, dict]:
    if not soniox_alert_only:
        return rules
    rule = rules.get(SONIOX_DAILY_HOURS_UID)
    if rule is None:
        raise ValueError(f'{SONIOX_DAILY_HOURS_UID}: committed alert is missing')
    return {SONIOX_DAILY_HOURS_UID: rule}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rules', type=Path, default=RULES)
    parser.add_argument('--grafana-url', default='https://monitor.omi.me')
    parser.add_argument('--token-env', default='MONITOR_GRAFANA_TOKEN')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--prepare-soniox-alert', action='store_true')
    parser.add_argument('--apply-soniox-alert', action='store_true')
    parser.add_argument('--backup-file', type=Path)
    parser.add_argument('--source-sha', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--source-run-id', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument(
        '--soniox-alert-only',
        action='store_true',
        help='apply only omi-batch-soniox-daily-hours and capture its inverse',
    )
    parser.add_argument('--lint', action='store_true')
    parser.add_argument('--regenerate', action='store_true', help='offline: rebuild combined export from split sources')
    parser.add_argument('--probe-datasources', action='store_true', help='read-only canary queries through Grafana')
    parser.add_argument('--redis-pilot-url', help='read-only Redis pilot rule and dedicated contact check')
    parser.add_argument('--redis-pilot-alias-host', action='append', default=[], help='reviewed relay ingress alias')
    args = parser.parse_args()
    try:
        if args.prepare_soniox_alert and args.apply_soniox_alert:
            raise ValueError('prepare and apply Soniox alert modes are separate steps')
        soniox_stage = args.prepare_soniox_alert or args.apply_soniox_alert
        if soniox_stage and (
            not args.soniox_alert_only
            or args.backup_file is None
            or args.apply
            or args.probe_datasources
            or args.lint
            or args.regenerate
            or args.redis_pilot_url is not None
        ):
            raise ValueError('Soniox prepare/apply requires its scoped mode and --backup-file only')
        if args.redis_pilot_alias_host and args.redis_pilot_url is None:
            raise ValueError('--redis-pilot-alias-host requires --redis-pilot-url')
        if args.redis_pilot_url is not None and (
            args.apply
            or args.backup_file
            or args.regenerate
            or args.lint
            or args.probe_datasources
            or args.soniox_alert_only
        ):
            raise ValueError('--redis-pilot-url is a standalone read-only check')
        if args.regenerate:
            if args.apply or args.backup_file or args.probe_datasources:
                raise ValueError('regeneration is offline only')
            regenerate_export(args.rules)
            print(f'Regenerated {len(load_rules(args.rules))} combined/split alert definitions')
            return 0
        all_rules = load_rules(args.rules)
        rules = select_rules(all_rules, soniox_alert_only=args.soniox_alert_only)
        if soniox_stage:
            token = os.environ.get(args.token_env, '').strip()
            if not token:
                raise ValueError(f'{args.token_env} is empty')
            api = Grafana(args.grafana_url, token)
            if args.prepare_soniox_alert:
                prepare_soniox_alert(
                    api,
                    rules,
                    all_rules,
                    args.backup_file,
                    source_sha=args.source_sha,
                    source_run_id=args.source_run_id,
                )
                print('Prepared the version-bound Soniox alert preimage; no Grafana write occurred')
            else:
                snapshot = load_soniox_snapshot(args.backup_file, args.source_sha, args.source_run_id)
                apply_soniox_snapshot(api, snapshot, rules[SONIOX_DAILY_HOURS_UID])
                print('Applied and verified the Soniox alert with its captured resource version')
            return 0
        if (
            args.soniox_alert_only
            and args.apply
            and (
                not re.fullmatch(r'[0-9a-f]{40}', args.source_sha)
                or not re.fullmatch(r'[1-9][0-9]*', args.source_run_id)
            )
        ):
            raise ValueError('Soniox-only apply requires a full source SHA and GitHub run ID')
        if args.probe_datasources and (args.lint or args.apply or args.backup_file):
            raise ValueError('datasource probes are read-only and cannot be combined with other modes')
        if args.lint:
            print(f'Validated {len(rules)} combined/split production alert definitions')
            return 0
        if args.soniox_alert_only and args.apply:
            raise ValueError('Soniox alert writes require --prepare-soniox-alert then --apply-soniox-alert')
        if args.apply != (args.backup_file is not None):
            raise ValueError('--apply requires --backup-file; backup is forbidden for read-only checks')
        token = os.environ.get(args.token_env, '').strip()
        if not token:
            raise ValueError(f'{args.token_env} is empty')
        api = Grafana(args.grafana_url, token)
        if args.redis_pilot_url is not None:
            differences = check_redis_pilot(api, rules, args.redis_pilot_url, tuple(args.redis_pilot_alias_host))
        elif args.probe_datasources:
            differences = probe_datasources(api, rules)
        else:
            differences = reconcile(
                api,
                rules,
                backup=args.backup_file,
                source_sha=args.source_sha,
                source_run_id=args.source_run_id,
                soniox_alert_only=args.soniox_alert_only,
                canary_rules=all_rules if args.soniox_alert_only else None,
            )
        for difference in differences:
            print('DRIFT ' + difference)
        if differences:
            return 1
        if args.redis_pilot_url is not None:
            print('Verified Redis pilot rule and dedicated webhook')
            return 0
        print(
            'Canary query probes passed'
            if args.probe_datasources
            else f'Verified {len(rules) - int(REDIS_PAGER_UID in rules)} bulk-managed alert definitions; no drift'
        )
        return 0
    except (ValueError, OSError):
        # Do not expose API bodies, credentials, annotations, or local file contents.
        exc = sys.exc_info()[1]
        print(f'FAIL: {exc}' if isinstance(exc, ValueError) else 'FAIL: local file operation failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
