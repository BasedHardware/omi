#!/usr/bin/env python3
"""Render the stuck-state age alarms from the census registry (SCA-2119).

The registry is the single source of truth: a stock with ``age_alarm_seconds``
gets one Grafana rule over its exact ``(machine, state)`` series. A stock
without it is still measured and shown on the dashboard; it just has no page.

Writes ``backend/charts/monitoring/alerts/batch-census.json`` and appends the
same rules to the combined export, preserving existing rule order. ``--check``
verifies both files match the registry without writing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from config.batch_census import ENTRIES, CensusEntry  # noqa: E402

MONITORING = ROOT / 'backend' / 'charts' / 'monitoring'
SPLIT_PATH = MONITORING / 'alerts' / 'batch-census.json'
COMBINED_PATH = MONITORING / 'alert-rules.json'
FOLDER_UID = 'betdycdziadc0e'
RULE_GROUP = 'Batch stuck-state census'
RUNBOOK = 'backend/docs/runbooks/batch-stuck-census.md'
DASHBOARD_UID = 'omi-batch-stuck-census'
DASHBOARD_URL = f'https://monitor.omi.me/d/{DASHBOARD_UID}'
# An age reading is only useful while its own observation is fresh. The
# scheduler runs every ten minutes; thirty minutes leaves two missed runs.
FRESH_SECONDS = 1800
BLIND_UID = 'omi-census-stocks-blind'
SNAPSHOT_BLIND_UID = 'omi-census-snapshot-blind'

# Grafana rejects a UID longer than 40 characters at create time.
MACHINE_TAGS = {
    'batch': 'b',
    'batch_projection': 'p',
    'batch_recovery': 'r',
    'provider_outbox': 'po',
    'memory_outbox': 'mo',
    'enrichment_outbox': 'eo',
    'speaker_outbox': 'so',
    'cap_hold': 'ch',
    'pipeline_ledger': 'pl',
}

# One sentence per family explains the human consequence of a stuck stock.
IMPACT = {
    'batch': 'A recorded unit is not progressing through the batch pipeline, so its conversation may never appear.',
    'batch_projection': 'A committed transcript has not been projected, so the user cannot see that conversation yet.',
    'batch_recovery': 'A recovery attempt is stalled, leaving a unit neither recovered nor terminated.',
    'provider_outbox': 'A provider-STT obligation is not being delivered, so its audio waits without a result.',
    'memory_outbox': 'A memory write is waiting, so a fact the user recorded is not searchable or applied.',
    'enrichment_outbox': 'A conversation enrichment obligation is waiting, so its summary or notepad result is late.',
    'speaker_outbox': 'The speaker final pass is waiting, so a conversation may keep unlabeled speakers.',
    'cap_hold': 'Held audio is not advancing, so that recording is not being transcribed.',
    'pipeline_ledger': 'A capture is stuck in the live ledger between admission and its terminal projection.',
}


def _tag(entry: CensusEntry) -> str:
    return MACHINE_TAGS[entry.machine]


def rule_uid(entry: CensusEntry) -> str:
    return f'omi-census-age-{_tag(entry)}-{entry.state}'


def _selector(entry: CensusEntry) -> str:
    return f'{{machine="{entry.machine}",state="{entry.state}"}}'


def _query(ref_id: str, expr: str) -> dict:
    return {
        'refId': ref_id,
        'queryType': '',
        'relativeTimeRange': {'from': 900, 'to': 0},
        'datasourceUid': 'prometheus',
        'model': {
            'datasource': {'type': 'prometheus', 'uid': 'prometheus'},
            'expr': expr,
            'instant': True,
            'intervalMs': 1000,
            'maxDataPoints': 43200,
            'refId': ref_id,
        },
    }


def _math(ref_id: str, expression: str) -> dict:
    return {
        'refId': ref_id,
        'queryType': '',
        'relativeTimeRange': {'from': 0, 'to': 0},
        'datasourceUid': '__expr__',
        'model': {
            'datasource': {'type': '__expr__', 'uid': '__expr__'},
            'expression': expression,
            'intervalMs': 1000,
            'maxDataPoints': 43200,
            'refId': ref_id,
            'type': 'math',
        },
    }


def _reduce(ref_id: str, expression: str) -> dict:
    return {
        'refId': ref_id,
        'queryType': '',
        'relativeTimeRange': {'from': 0, 'to': 0},
        'datasourceUid': '__expr__',
        'model': {
            'conditions': [
                {
                    'evaluator': {'params': [], 'type': 'gt'},
                    'operator': {'type': 'and'},
                    'query': {'params': [ref_id], 'type': 'query'},
                    'reducer': {'params': [], 'type': 'last'},
                    'type': 'query',
                }
            ],
            'datasource': {'type': '__expr__', 'uid': '__expr__'},
            'expression': expression,
            'intervalMs': 1000,
            'maxDataPoints': 43200,
            'reducer': 'last',
            'refId': ref_id,
            'type': 'reduce',
        },
    }


def _rule(entry: CensusEntry) -> dict:
    threshold = int(entry.age_alarm_seconds or 0)
    uid = rule_uid(entry)
    selector = _selector(entry)
    age_expr = f'max(omi_batch_pipeline_census_state_oldest_age_seconds{selector}) or vector(0)'
    stale_expr = f'(time() - max(omi_batch_pipeline_census_state_observed_at_seconds{selector})) or vector(1e9)'
    severity = entry.age_alarm_severity or 'warning'
    tier = 'page' if severity == 'critical' else 'agent'
    return {
        'uid': uid,
        'orgID': 1,
        'folderUID': FOLDER_UID,
        'ruleGroup': RULE_GROUP,
        'title': f'Batch {entry.machine} {entry.state}: oldest row older than {threshold}s',
        'condition': 'D',
        'data': [
            _query('A', age_expr),
            _query('B', stale_expr),
            _math('C', f'($A > {threshold}) && ($B < {FRESH_SECONDS})'),
            _reduce('D', 'C'),
        ],
        'updated': '2026-11-14T00:00:00Z',
        'noDataState': 'OK',
        'execErrState': 'KeepLast',
        'for': '10m',
        'keep_firing_for': '0s',
        'annotations': {
            'summary': f'The oldest {entry.machine} {entry.state} row is older than {threshold}s with a fresh census sample.',
            'user_impact': IMPACT[entry.machine],
            'scope': (
                'Exact count and one oldest-clock projection over the registered stock; no document content, '
                'transcript, audio reference, uid or email is read. Age is measured from '
                f'{entry.clock or "no clock"}{"" if entry.clock_verified else " (unverified clock)"}.'
            ),
            'verification': (
                f'Open {DASHBOARD_URL} and read the {entry.machine}:{entry.state} count and oldest age; '
                'confirm omi_batch_pipeline_census_state_observed_at_seconds for that state is newer than '
                f'{FRESH_SECONDS}s. A -1 age means rows exist but none carries an ageable clock.'
            ),
            'safe_next_action': (
                'Follow backend/docs/runbooks/batch-stuck-census.md for this state; never delete staged audio, '
                'held content or a lease by hand. Silence only a broken sample, never a real breach.'
            ),
            'dashboard_url': DASHBOARD_URL,
            'runbook': RUNBOOK,
            'threshold': f'oldest age > {threshold}s with observation newer than {FRESH_SECONDS}s, for 10m',
        },
        'labels': {
            'alert_identity': uid,
            'component': 'batch-census',
            'impact': 'product',
            'severity': severity,
            'tier': tier,
            'audience': 'human' if tier == 'page' else 'agent',
            'instatus_component': 'speech-processing',
            'owner': 'batch-pipeline',
        },
        'isPaused': False,
        'notification_settings': {
            'receiver': 'Omi - Services Alerting (Telegram)',
            'group_by': ['alertname'],
            'group_wait': '30s',
            'group_interval': '5m',
            'repeat_interval': '4h',
            'mute_time_intervals': [] if tier == 'page' else ['omi-tier-silent'],
        },
        'record': None,
    }


def _blind_rule(uid: str, title: str, expr: str, summary: str) -> dict:
    return {
        'uid': uid,
        'orgID': 1,
        'folderUID': FOLDER_UID,
        'ruleGroup': RULE_GROUP,
        'title': title,
        'condition': 'C',
        'data': [_query('A', expr), _math('B', '$A > 0'), _reduce('C', 'B')],
        'updated': '2026-11-14T00:00:00Z',
        'noDataState': 'Alerting',
        'execErrState': 'KeepLast',
        'for': '15m',
        'keep_firing_for': '0s',
        'annotations': {
            'summary': summary,
            'user_impact': 'A stuck stock is unmeasurable, so nobody can tell whether users are waiting on it.',
            'scope': (
                'Completeness of the census itself, not of the pipeline. Every registered stock must report a '
                'fresh observation; an unregistered or failing stock must not read as a healthy zero.'
            ),
            'verification': (
                f'Open {DASHBOARD_URL}; compare omi_batch_pipeline_census_registered_stocks with the number of '
                'states reporting a fresh observation. Check the scheduled batch-stock-census run and its logs.'
            ),
            'safe_next_action': (
                'Fix the census sample (scheduler invocation, Firestore index, query error) before routing the '
                'missing stock through a manual count. Never widen the alarm instead of restoring the sample.'
            ),
            'dashboard_url': DASHBOARD_URL,
            'runbook': RUNBOOK,
        },
        'labels': {
            'alert_identity': uid,
            'component': 'batch-census',
            'impact': 'product',
            'severity': 'critical',
            'tier': 'page',
            'audience': 'human',
            'instatus_component': 'speech-processing',
            'owner': 'batch-pipeline',
        },
        'isPaused': False,
        'notification_settings': {
            'receiver': 'Omi - Services Alerting (Telegram)',
            'group_by': ['alertname'],
            'group_wait': '30s',
            'group_interval': '5m',
            'repeat_interval': '4h',
            'mute_time_intervals': [],
        },
        'record': None,
    }


def rules() -> list[dict]:
    rendered = [_rule(entry) for entry in ENTRIES if entry.age_alarm_seconds]
    rendered.append(
        _blind_rule(
            SNAPSHOT_BLIND_UID,
            'Batch stuck-state census has not completed',
            '(time() - max(omi_batch_pipeline_census_snapshot_timestamp_seconds)) or vector(1e9)',
            'No completed census pass in the last 15 minutes; the scheduled exporter is not running or failing.',
        )
    )
    rendered.append(
        _blind_rule(
            BLIND_UID,
            'Batch stuck-state census is missing stocks',
            '(omi_batch_pipeline_census_registered_stocks or vector(0)) '
            '- count(count by (machine, state) (omi_batch_pipeline_census_state_observed_at_seconds '
            f'> (time() - {FRESH_SECONDS})))',
            'One or more registered stocks has no fresh observation; its count and age are unmeasured.',
        )
    )
    return rendered


def render() -> str:
    return json.dumps(rules(), indent=2, ensure_ascii=False) + '\n'


def check() -> int:
    expected = {rule['uid']: rule for rule in rules()}
    split = {rule['uid']: rule for rule in json.loads(SPLIT_PATH.read_text())}
    combined = {rule['uid']: rule for rule in json.loads(COMBINED_PATH.read_text())}
    problems = []
    if split != expected:
        problems.append(f'{SPLIT_PATH.relative_to(ROOT)} does not match the registry')
    missing = [uid for uid in expected if uid not in combined]
    different = [uid for uid in expected if uid in combined and combined[uid] != expected[uid]]
    if missing:
        problems.append(f'{COMBINED_PATH.relative_to(ROOT)} is missing {missing}')
    if different:
        problems.append(f'{COMBINED_PATH.relative_to(ROOT)} differs for {different}')
    if problems:
        print('ERROR: ' + '; '.join(problems))
        print('Run: python3 backend/scripts/generate_batch_census_alerts.py --write')
        return 1
    print(f'{len(expected)} census alert rules match the registry')
    return 0


def write() -> int:
    SPLIT_PATH.write_text(render())
    from scripts.provision_monitoring_alerts import regenerate_export

    regenerate_export(COMBINED_PATH)
    print(f'Regenerated {len(rules())} census alert rules and the combined export')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='rewrite the split and combined alert exports')
    arguments = parser.parse_args()
    raise SystemExit(write() if arguments.write else check())
