"""Direct IAM migration operator; never prints connection settings.

Run from backend/: ``python -m database.directory migrate|status`` (``--help`` for usage).
Set ``DIRECTORY_PG_HOST`` to the direct Cloud SQL private IP, never a pooler endpoint;
the connection uses port 5432. Set ``DIRECTORY_PG_DATABASE`` and ``DIRECTORY_PG_USER``
to the target database and migration-owner IAM database user (service account email
without ``.gserviceaccount.com``). Run with that identity's application default
credentials (ADC); the password is a fresh short-lived IAM token. Both commands use
one direct connection, with no pool or fallback. No additional flags or password env vars.
"""

import argparse
import os
from pathlib import Path

from database.jobstore.connection import iam_connector
from database.jobstore.migrate import current_version, migrate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('migrate', 'status'))
    args = parser.parse_args()
    conn = iam_connector(
        os.environ['DIRECTORY_PG_HOST'], os.environ['DIRECTORY_PG_DATABASE'], os.environ['DIRECTORY_PG_USER']
    )()
    try:
        if args.command == 'migrate':
            print(migrate(conn, directory=Path(__file__).parent / 'migrations'))
        else:
            print(current_version(conn))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
