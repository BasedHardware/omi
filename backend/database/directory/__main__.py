"""IAM-env-only migration operator; never prints connection settings."""

import argparse
import os
from pathlib import Path

from database.jobstore.connection import Pool, iam_connector
from database.jobstore.migrate import current_version, migrate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('migrate', 'status'))
    args = parser.parse_args()
    connect = iam_connector(
        os.environ['DIRECTORY_PG_HOST'], os.environ['DIRECTORY_PG_DATABASE'], os.environ['DIRECTORY_PG_USER']
    )
    pool = Pool('', size=2, connect=connect)
    try:
        with pool.connection() as conn:
            if args.command == 'migrate':
                print(migrate(conn, directory=Path(__file__).parent / 'migrations'))
            else:
                print(current_version(conn))
    finally:
        pool.close()


if __name__ == '__main__':
    main()
