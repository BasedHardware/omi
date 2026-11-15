"""Erase WAL crash orphans without importing sync serving/provider machinery."""

from google.cloud.exceptions import NotFound

from config.record_wal_storage import private_archive_bucket
from utils.other.local_storage import create_storage_client


def purge_record_wal_owner(uid: str) -> None:
    """Privacy-only sweep of all owner generations, including unreceipted writes."""
    if not uid or '/' in uid:
        raise ValueError('bounded WAL erasure owner required')
    bucket = create_storage_client().bucket(private_archive_bucket())
    prefix = f'record-wal/{uid}/'
    for blob in bucket.list_blobs(prefix=prefix, versions=True, timeout=10, retry=None):
        generation = int(blob.generation or 0)
        if generation <= 0:
            raise ValueError('WAL erasure requires an immutable generation')
        options = {'if_generation_match': generation, 'timeout': 10, 'retry': None}
        if metadata_generation := getattr(blob, 'metageneration', None):
            options['if_metageneration_match'] = int(metadata_generation)
        try:
            blob.delete(**options)
        except NotFound:
            pass
    if list(bucket.list_blobs(prefix=prefix, versions=True, max_results=1, timeout=10, retry=None)):
        raise RuntimeError('WAL owner storage purge did not converge')
