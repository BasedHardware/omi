#!/usr/bin/env python3
"""Manually retire four known paused Loki rules after log-view parity acceptance.

Default preflight is GET-only. Apply requires canonical source removal and an
exclusive private backup. No workflow invokes this destructive helper.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from provision_monitoring_alerts import (
    API,
    ROOT,
    RULES,
    Grafana,
    NoRedirect,
    comparable,
    definition,
    index_rules,
    load_rules,
)

MANIFEST = ROOT / 'backend/charts/monitoring/retired-loki-alerts.json'
UIDS = frozenset({'afd0krbk1bugwf', 'fewwk2goqfklcf', 'devzd05c0bocgc', 'df2a40h2fbjswe'})
LOKI = 'aet29e27cgmwwc'


def retired_rules(path: Path = MANIFEST) -> dict[str, dict]:
    payload = json.loads(path.read_text())
    if payload.get('schema_version') != 1:
        raise ValueError('invalid retirement manifest')
    rules = index_rules(payload['rules'])
    if set(rules) != UIDS:
        raise ValueError('retirement manifest must contain exactly the four reviewed UIDs')
    for uid, rule in rules.items():
        validate(uid, rule, rule)
    return rules


def validate(uid: str, live: dict, expected: dict) -> None:
    if not isinstance(live, dict) or live.get('uid') != uid or live.get('isPaused') is not True:
        raise ValueError(uid)
    # Grafana12.1 provisioning semantics not represented by historical exports
    # still belong to identity: never delete a repurposed recording rule or a
    # changed missing-series resolution policy. Null/absent share API defaults.
    if live.get('record') is not None or expected.get('record') is not None:
        raise ValueError(uid)
    if live.get('missingSeriesEvalsToResolve') != expected.get('missingSeriesEvalsToResolve'):
        raise ValueError(uid)
    # Grafana 13 rewrites durations on save ('24h' reads back as '1d').
    if comparable(live) != comparable(expected):
        raise ValueError(uid)
    if live.get('labels', {}).get('alert_identity') != uid or live.get('provenance', '') not in ('', 'api'):
        raise ValueError(uid)
    queries = [node for node in live.get('data', []) if node.get('datasourceUid') not in ('__expr__', '-100')]
    if not queries or any(
        node.get('datasourceUid') != LOKI
        or node.get('model', {}).get('datasource', {}).get('type') != 'loki'
        or node.get('model', {}).get('datasource', {}).get('uid') != LOKI
        or not node.get('model', {}).get('expr')
        for node in queries
    ):
        raise ValueError(uid)


class RetirementGrafana(Grafana):
    def request(self, path: str, body: dict | None = None, method: str = 'GET', *, editable: bool = False):
        uid = path.removeprefix(API + '/')
        if body is not None or path != API + '/' + uid or uid not in UIDS or method not in ('GET', 'DELETE'):
            raise ValueError('unsupported retirement request')
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json'}
        if editable:
            headers['X-Disable-Provenance'] = 'true'
        request = urllib.request.Request(self.base + path, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise ValueError(uid)
        except urllib.error.HTTPError as exc:
            if method == 'GET' and exc.code == 404:
                return None
            raise ValueError(uid) from None
        except OSError:
            raise ValueError(uid) from None
        if method == 'DELETE':
            return None
        try:
            payload = json.loads(data)
            if not isinstance(payload, dict) or payload.get('uid') != uid:
                raise ValueError(uid)
            return payload
        except (ValueError, UnicodeError):
            raise ValueError(uid) from None


def retire(api, canonical: dict, expected: dict, *, backup: Path | None = None) -> list[str]:
    if set(expected) != UIDS:
        raise ValueError('unexpected retirement set')
    if UIDS & canonical.keys():
        raise ValueError('retired UIDs remain in canonical sources')
    snapshot = {}
    for uid in sorted(UIDS):
        live = api.request(API + '/' + uid)
        if live is not None:
            validate(uid, live, expected[uid])
            snapshot[uid] = live
    if backup is None:
        return [f'READY {uid}' if uid in snapshot else f'ABSENT {uid}' for uid in sorted(UIDS)]
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump({'schema_version': 1, 'retired_uids': sorted(UIDS), 'rules': snapshot}, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    for uid, saved in snapshot.items():
        # Recheck after backup and immediately before each delete; changed or
        # unpaused rules require fresh review, never a blind retry.
        live = api.request(API + '/' + uid)
        validate(uid, live, expected[uid])
        if definition(live) != definition(saved) or live.get('provenance', '') != saved.get('provenance', ''):
            raise ValueError(uid)
        api.request(API + '/' + uid, method='DELETE', editable=live.get('provenance', '') == '')
        if api.request(API + '/' + uid) is not None:
            raise ValueError(uid)
    for uid in sorted(UIDS):
        if api.request(API + '/' + uid) is not None:
            raise ValueError(uid)
    return [f'ABSENT {uid}' for uid in sorted(UIDS)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grafana-url', default='https://monitor.omi.me')
    parser.add_argument('--token-env', default='MONITOR_GRAFANA_TOKEN')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-file', type=Path)
    args = parser.parse_args()
    try:
        if args.apply != (args.backup_file is not None):
            raise ValueError('--apply and --backup-file must be supplied together')
        token = os.environ.get(args.token_env, '').strip()
        if not token:
            raise ValueError('missing token')
        canonical = load_rules(RULES)
        expected = retired_rules()
        api = RetirementGrafana(args.grafana_url, token)
        for status in retire(api, canonical, expected, backup=args.backup_file):
            print(status)
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        # No API bodies, logs, annotations, token values or arbitrary server text.
        print('FAIL retirement preconditions or verification', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
