"""Read-only post-deploy gate; prints aggregate counts only, never document IDs.

Run after sourcing ~/.local/bin/gcp-agent-env.sh ro-prod:
  python3 -I backend/scripts/batch_recovery_large_held_check.py --since <release-UTC-ISO>

Uses recovery.settled_at rather than admission time so older queued audio that
fails after deployment is included. Exit 0: clean; 1: matching held units;
2: incomplete evidence or query failure. No mutation or redrive operations.
"""

import argparse
import datetime as dt
import json
import subprocess
import urllib.request


def scalar(value):
    if 'mapValue' in value:
        return {key: scalar(item) for key, item in value['mapValue'].get('fields', {}).items()}
    for field in ('stringValue', 'doubleValue', 'integerValue'):
        if field in value:
            return float(value[field]) if field != 'stringValue' else value[field]
    return None


def summarize(rows, since):
    matching, unknown = 0, 0
    for entry in rows:
        if 'error' in entry:
            raise ValueError('query error')
        document = entry.get('document')
        if document is None:
            continue
        row = {key: scalar(value) for key, value in document.get('fields', {}).items()}
        if (row.get('duration_seconds') or 0) <= 3277:
            continue
        recovery = row.get('recovery') or {}
        if (recovery.get('failure') or {}).get('reason') != 'provider_failed':
            continue
        settled = recovery.get('settled_at')
        if not isinstance(settled, (int, float)):
            unknown += 1
        elif settled >= since:
            matching += 1
    return {'new_large_provider_failed_held': matching, 'unknown_settlement_time': unknown}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', required=True, help='UTC release time, e.g. 2026-11-04T00:00:00Z')
    args = parser.parse_args()
    since = dt.datetime.fromisoformat(args.since.replace('Z', '+00:00'))
    if since.tzinfo is None:
        parser.error('--since requires a timezone')
    fields = ['duration_seconds', 'recovery.settled_at', 'recovery.failure.reason']
    query = {
        'structuredQuery': {
            'from': [{'collectionId': 'batch_pipeline_prod_jobs'}],
            'select': {'fields': [{'fieldPath': field} for field in fields]},
            'where': {
                'fieldFilter': {
                    'field': {'fieldPath': 'recovery_state'},
                    'op': 'EQUAL',
                    'value': {'stringValue': 'failed_held'},
                }
            },
        }
    }
    try:
        token = subprocess.run(
            ['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True, check=True, timeout=60
        ).stdout.strip()
        request = urllib.request.Request(
            'https://firestore.googleapis.com/v1/projects/based-hardware/databases/(default)/documents:runQuery',
            data=json.dumps(query).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            result = summarize(json.load(response), since.timestamp())
    except Exception:
        print(json.dumps({'status': 'UNKNOWN', 'reason': 'query_failed'}))
        return 2
    print(json.dumps({'since': args.since, **result}, sort_keys=True))
    return 2 if result['unknown_settlement_time'] else int(result['new_large_provider_failed_held'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
