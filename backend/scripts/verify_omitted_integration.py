"""Read-only before/after identity guard for the consumers-only native workflow.

Only a fingerprint and revision identity are persisted, never the service's
configuration. This guard supplies drift evidence; it authorizes no writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.integration_canary_metrics import Clock, Refused, command, decode, io_budget, require  # noqa: E402

SERVICE = 'backend-integration'


def fingerprint(doc):
    require(isinstance(doc, dict), 'omitted_service_missing')
    meta, spec, status = (doc.get(k) for k in ('metadata', 'spec', 'status'))
    require(all(isinstance(v, dict) for v in (meta, spec, status)), 'omitted_service_malformed')
    require(
        meta.get('name') == SERVICE
        and all(isinstance(meta.get(k), str) and meta[k] for k in ('uid', 'resourceVersion')),
        'omitted_service_identity_missing',
    )
    require(
        isinstance(spec.get('template'), dict) and isinstance(spec.get('traffic'), list), 'omitted_service_spec_missing'
    )
    require(
        isinstance(status.get('traffic'), list) and bool(status.get('latestReadyRevisionName')),
        'omitted_service_traffic_missing',
    )
    receiving = [row for row in status['traffic'] if isinstance(row, dict) and row.get('percent', 0)]
    require(
        len(receiving) == 1
        and receiving[0].get('percent') == 100
        and receiving[0].get('revisionName') == 'backend-integration-provfix-off1114',
        'omitted_service_rollback_target_not_serving',
    )
    projection = {
        'uid': meta['uid'],
        'resourceVersion': meta['resourceVersion'],
        'spec': spec,
        'traffic': status['traffic'],
        'ready': status['latestReadyRevisionName'],
        'created': status.get('latestCreatedRevisionName'),
    }
    raw = json.dumps(projection, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {'schema_version': 1, 'service': SERVICE, 'uid': meta['uid'], 'sha256': hashlib.sha256(raw).hexdigest()}


def observe():
    return fingerprint(
        decode(
            command(
                [
                    'gcloud',
                    'run',
                    'services',
                    'describe',
                    SERVICE,
                    '--project',
                    'based-hardware',
                    '--region',
                    'us-central1',
                    '--format=json',
                    '--quiet',
                ]
            )
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('capture', 'verify'))
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    try:
        with io_budget(35, Clock()):
            current = observe()
            current['run_id'] = os.environ['GITHUB_RUN_ID']
            current['run_attempt'] = os.environ['GITHUB_RUN_ATTEMPT']
            if args.mode == 'capture':
                fd = os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as output:
                    json.dump(current, output, allow_nan=False)
                    output.flush()
                    os.fsync(output.fileno())
            else:
                require(
                    not args.state.is_symlink() and args.state.stat().st_size <= 4096, 'omitted_service_state_invalid'
                )
                require(json.loads(args.state.read_text()) == current, 'omitted_service_changed')
        print(
            'Omitted integration identity unchanged.'
            if args.mode == 'verify'
            else 'Omitted integration identity captured.'
        )
        return 0
    except (Refused, ValueError, KeyError, OSError):
        print('Omitted integration guard refused.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
