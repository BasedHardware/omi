"""Count authenticated private-sync object GET attempts at the HTTP boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit

from prometheus_client import Counter


class Reader(StrEnum):
    RECEIPT_READBACK = 'receipt_readback'
    PLAYBACK_INVENTORY = 'playback_inventory'
    PLAYBACK_MEDIA = 'playback_media'
    ARCHIVE_RECONCILE = 'archive_reconcile'
    BATCH_SOURCE = 'batch_source'
    SYNC_RECOVERY = 'sync_recovery'
    SPEAKER_EVIDENCE = 'speaker_evidence'
    OTHER = 'other'


OBJECT_GETS = Counter(
    'omi_private_sync_object_get_total',
    'Authenticated HTTP attempts to read one object from the configured private-sync bucket',
    ('reader', 'kind'),
)
_reader = ContextVar('private_sync_get_reader', default=Reader.OTHER)
_GCS_URL_PREFIXES = ('https://storage.googleapis.com/', 'https://storage.mtls.googleapis.com/')


@contextmanager
def object_get_reader(reader: Reader) -> Iterator[None]:
    token = _reader.set(reader)
    try:
        yield
    finally:
        _reader.reset(token)


def instrument_storage_session(session, bucket_name: str) -> None:
    """Observe prepared requests after auth without changing the SDK transport."""
    send = session.send
    object_prefix = f'/storage/v1/b/{bucket_name}/o/'
    download_prefix = f'/download{object_prefix}'

    def send_with_metric(request, **kwargs):
        try:
            if request.method == 'GET' and request.url.startswith(_GCS_URL_PREFIXES):
                target = urlsplit(request.url)
                prefix = download_prefix if target.path.startswith(download_prefix) else object_prefix
                object_part = target.path[len(prefix) :]
                if target.path.startswith(prefix) and object_part and '/' not in object_part:
                    alt = parse_qs(target.query).get('alt')
                    kind = 'payload' if alt == ['media'] else 'metadata'
                    OBJECT_GETS.labels(_reader.get().value, kind).inc()
        except Exception:
            pass  # An observation failure must never change the storage operation.
        return send(request, **kwargs)

    session.send = send_with_metric
