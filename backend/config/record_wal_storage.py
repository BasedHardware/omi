"""Archive infrastructure identity shared by WAL custody and privacy erasure."""

import os


def private_archive_bucket() -> str:
    return os.getenv('BUCKET_PRIVATE_CLOUD_SYNC', 'omi-private-cloud-sync')
