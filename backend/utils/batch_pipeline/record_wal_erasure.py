"""Erase WAL crash orphans without importing sync serving/provider machinery."""

from config.record_wal_storage import private_archive_bucket
from database.account_deletion_operational_holds import delete_owner_bucket_prefix
from utils.other.local_storage import create_storage_client


def purge_record_wal_owner(uid: str) -> None:
    bucket = create_storage_client().bucket(private_archive_bucket())
    delete_owner_bucket_prefix(
        bucket,
        f'record-wal/{uid}/',
        real_gcs=type(bucket).__module__.startswith('google.cloud.storage'),
    )
