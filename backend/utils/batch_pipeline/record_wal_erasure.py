"""Erase WAL crash orphans without importing sync serving/provider machinery."""

from google.cloud.exceptions import NotFound
from google.api_core.retry import Retry

from config.record_wal_storage import private_archive_bucket
from utils.other.local_storage import create_storage_client


def _prefix(uid: str, conversation_id: str | None = None) -> str:
    if not uid or '/' in uid or uid in {'.', '..'}:
        raise ValueError('bounded WAL erasure owner required')
    if conversation_id is not None and (
        not conversation_id or '/' in conversation_id or conversation_id in {'.', '..'}
    ):
        raise ValueError('bounded WAL erasure conversation required')
    return f'record-wal/{uid}/' + (f'{conversation_id}/' if conversation_id is not None else '')


def conversation_objects(uid: str, conversation_id: str, *, limit: int = 10) -> list[str]:
    """One bounded page, every generation, from the handoff's sole write bucket.

    Delete each URI through the conversation purge's existing fenced remote
    erasure units; a restart re-lists the first page, including crash orphans.
    """
    name = private_archive_bucket()
    bucket = create_storage_client().bucket(name)
    result = []
    for blob in bucket.list_blobs(
        prefix=_prefix(uid, conversation_id), versions=True, max_results=limit, timeout=5, retry=Retry(deadline=5)
    ):
        generation = int(blob.generation or 0)
        if generation <= 0:
            raise ValueError('WAL erasure requires an immutable generation')
        result.append(f'gs://{name}/{blob.name}#{generation}')
        if len(result) >= limit:
            break
    return result


def purge_record_wal_owner(uid: str, conversation_id: str | None = None) -> None:
    """Privacy-only sweep of every generation, including unreceipted writes."""
    prefix = _prefix(uid, conversation_id)
    bucket = create_storage_client().bucket(private_archive_bucket())
    listing_retry = Retry(deadline=10)
    for blob in bucket.list_blobs(prefix=prefix, versions=True, timeout=10, retry=listing_retry):
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
    if list(bucket.list_blobs(prefix=prefix, versions=True, max_results=1, timeout=10, retry=listing_retry)):
        raise RuntimeError('WAL storage purge did not converge')
