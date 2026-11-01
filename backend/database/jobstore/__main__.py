"""Operator entry against Cloud SQL (IAM auth, private IP).

- ``python -m database.jobstore migrate|status``: schema migrations; prints versions only.
- ``python -m database.jobstore backfill <namespace> [--apply] [--tables a,b]``: the A6 backfill (staging only
  until A6 proper). The default is a dry run (census only); ``--apply`` copies missing and differing documents.
  Prints one JSON object of per-table counts; never a key, id or value.

Environment: ``JOBSTORE_PG_HOST`` (private IP), ``JOBSTORE_PG_DATABASE``, ``JOBSTORE_PG_USER`` (IAM database
user). Backfill also needs the batch worker's Firestore settings (``OMI_ENV_STAGE`` matching the namespace,
``OMI_DEPLOYMENT=staging``, ``FIRESTORE_DATABASE_ID=staging``). Never prints a DSN or token. Run it as a Cloud Run
job with direct VPC egress.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from database.jobstore.connection import iam_connector
from database.jobstore.migrate import current_version, migrate


def _pg_target() -> tuple[str, str, str]:
    return os.environ['JOBSTORE_PG_HOST'], os.environ['JOBSTORE_PG_DATABASE'], os.environ['JOBSTORE_PG_USER']


def backfill_main(argv: list[str]) -> int:
    from database.jobstore.dual_store import MIRRORED_TABLES
    from utils.staging_fence import STAGING_DATABASE, is_staging, jobstore_shadow_admits

    parser = argparse.ArgumentParser(prog='python -m database.jobstore backfill')
    parser.add_argument('namespace')
    parser.add_argument('--apply', action='store_true', help='copy missing and differing documents (default: dry run)')
    parser.add_argument('--tables', default=','.join(sorted(MIRRORED_TABLES)))
    args = parser.parse_args(argv)
    tables = [table for table in args.tables.split(',') if table]
    if not set(tables) <= MIRRORED_TABLES:
        print('only mirrored batch tables may be backfilled', file=sys.stderr)
        return 2
    # Staging dry run of A6: refuse anything but a staging deployment on the staging Firestore database.
    if not (
        is_staging()
        and (os.getenv('FIRESTORE_DATABASE_ID') or '').strip() == STAGING_DATABASE
        and jobstore_shadow_admits(args.namespace)
    ):
        print('refused: the backfill runs only in staging on the staging Firestore database', file=sys.stderr)
        return 2

    from database.batch_pipeline_store import FirestoreStore
    from database.jobstore.backfill import backfill
    from database.jobstore.connection import Pool
    from database.jobstore.dual_store import DualStore
    from database.jobstore.postgres_store import PostgresStore

    primary = FirestoreStore(args.namespace)
    pool = Pool('', size=2, connect=iam_connector(*_pg_target()))
    try:
        shadow = PostgresStore(args.namespace, pool=pool, customer_client=None)
        report = backfill(DualStore(primary, shadow, inline=True), primary.client, tables, apply=args.apply)
    finally:
        pool.close()
    totals = {field: sum(row[field] for row in report.values()) for field in next(iter(report.values()), {})}
    print(json.dumps({'namespace': args.namespace, 'apply': args.apply, 'tables': report, 'total': totals}))
    return 1 if totals.get('copy_errors') else 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else 'status'
    if command == 'backfill':
        return backfill_main(argv[1:])
    if command not in {'migrate', 'status'}:
        print('usage: python -m database.jobstore migrate|status|backfill', file=sys.stderr)
        return 2
    conn = iam_connector(*_pg_target())()
    try:
        if command == 'migrate':
            print('applied', migrate(conn))
        print('schema version', current_version(conn))
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
