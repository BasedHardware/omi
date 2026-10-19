"""Operator entry: ``python -m database.jobstore migrate|status`` against Cloud SQL (IAM auth, private IP).

Environment: ``JOBSTORE_PG_HOST`` (private IP), ``JOBSTORE_PG_DATABASE``, ``JOBSTORE_PG_USER`` (IAM database
user). Prints versions only; never a DSN, token or row. Run it as a Cloud Run job with direct VPC egress.
"""

from __future__ import annotations

import os
import sys

from database.jobstore.connection import iam_connector
from database.jobstore.migrate import current_version, migrate


def main(argv: list[str]) -> int:
    command = argv[0] if argv else 'status'
    if command not in {'migrate', 'status'}:
        print('usage: python -m database.jobstore migrate|status', file=sys.stderr)
        return 2
    conn = iam_connector(
        os.environ['JOBSTORE_PG_HOST'], os.environ['JOBSTORE_PG_DATABASE'], os.environ['JOBSTORE_PG_USER']
    )()
    try:
        if command == 'migrate':
            print('applied', migrate(conn))
        print('schema version', current_version(conn))
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
