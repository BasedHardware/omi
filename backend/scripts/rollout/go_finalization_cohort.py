# LIFECYCLE: permanent
"""Operator CLI for Go finalization cohort membership (SCA-3883). Never prints uids or SDK errors.

Each change writes `rollout_cohorts/{uid}.cohorts.<env>.go-finalization` and its append-only audit
row in one transaction. The switch is separate: `ramp_set.py --percent go-finalization=100` opens it
(CAS plus a history row); any other value closes it. Admitting a real owner needs the release
issue's go-ahead first; this tool records who acted and why, it does not grant that authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Callable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from database import rollout_cohorts as store  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=store.GO_FINALIZATION_ENVS, required=True)
    parser.add_argument('--uid-file', required=True, help='File holding exactly one uid (kept out of argv and logs)')
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument('--add', action='store_true')
    state.add_argument('--remove', action='store_true')
    parser.add_argument('--actor', required=True)
    parser.add_argument('--reason', required=True, help='Lowercase token, e.g. release_go_sca_1234')
    return parser


def main(argv: Sequence[str] | None = None, *, client_factory: Callable[[], object] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uid = Path(args.uid_file).read_text().strip()
    client = client_factory() if client_factory else None
    before, after = store.write_go_finalization_membership(
        uid,
        args.env,
        bool(args.add),
        actor=args.actor,
        reason=args.reason,
        at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        firestore_client=client,
    )
    print(json.dumps({'env': args.env, 'cohort': store.GO_FINALIZATION_COHORT, 'before': before, 'after': after}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
