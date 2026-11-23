# LIFECYCLE: permanent
"""Operator CLI for Go finalization cohort membership (SCA-3883). Never prints uids or SDK errors.

Each change writes `rollout_cohorts/{uid}.cohorts.<env>.go-finalization` and its append-only audit
row in one transaction. The default is a dry run; `--apply` requires the operator tier that matches
the selected project. The switch is separate: `ramp_set.py --percent go-finalization=100` opens it
(CAS plus a history row), and any other value closes it. Admitting a real owner needs the release
issue's go-ahead first. This tool records who acted and why; it does not grant that authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.rollout_cohorts import valid_uid  # noqa: E402
from database import rollout_cohorts as store  # noqa: E402

# Each cohort environment is bound to exactly one project and the tier allowed to write it.
TARGETS = {'prod': ('based-hardware', 'prod-operator'), 'dev': ('based-hardware-dev', 'dev-operator')}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=sorted(TARGETS), required=True)
    parser.add_argument(
        '--uid-file', type=Path, required=True, help='File holding exactly one uid (kept out of argv and logs)'
    )
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument('--add', action='store_true')
    state.add_argument('--remove', action='store_true')
    parser.add_argument('--actor', required=True)
    parser.add_argument('--reason', required=True, help='Lowercase token, e.g. release_go_sca_1234')
    parser.add_argument('--apply', action='store_true', help='Write; without it the command is a dry run')
    return parser


def _read_uid(path: Path) -> str | None:
    try:
        # A bound avoids reading a large payload. No path or value in errors.
        with path.open(encoding='utf-8') as handle:
            uid = handle.read(1024).strip()
    except (OSError, UnicodeError):
        return None
    if not valid_uid(uid) or '\n' in uid or '\r' in uid:
        return None
    return uid


def main(argv: Sequence[str] | None = None, *, client_factory: Callable[..., Any] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uid = _read_uid(args.uid_file)
    if uid is None:
        print('Invalid UID file; expected one private UID.', file=sys.stderr)
        return 2
    project, tier = TARGETS[args.env]
    action = 'add' if args.add else 'remove'
    if not args.apply:
        print(json.dumps({'dry_run': True, 'env': args.env, 'project': project, 'action': action}))
        return 0
    if client_factory is None:
        if os.getenv('GCP_AGENT_TIER') != tier or not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            print(f'Select the {tier} GCP tier before applying.', file=sys.stderr)
            return 2
        client_factory = firestore.Client
    try:
        before, after = store.write_go_finalization_membership(
            uid,
            args.env,
            bool(args.add),
            actor=args.actor,
            reason=args.reason,
            at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            firestore_client=client_factory(project=project),
        )
    except ValueError:
        print('Refused: invalid actor, reason or stored cohort document. Nothing was written.', file=sys.stderr)
        return 2
    except Exception:
        # SDK errors may name the document path, which carries the uid. Never print or re-raise them.
        # A commit-time timeout is ambiguous: the write may have landed.
        print(
            'Membership write outcome unknown; no UID or SDK error is logged. Re-read the flag and its '
            'audit row before retrying.',
            file=sys.stderr,
        )
        return 1
    print(json.dumps({'env': args.env, 'cohort': store.GO_FINALIZATION_COHORT, 'before': before, 'after': after}))
    print('Allow 60 seconds for process caches before expecting admission to change.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
