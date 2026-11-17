"""Request-scoped metadata reuse; never cache audio, custody or permissions."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import os
import time

from google.api_core.exceptions import PreconditionFailed
from prometheus_client import Counter

OPERATIONS = Counter(
    'omi_sync_audio_gcs_operations_total',
    'Logical GCS calls attempted by audio reads; LIST pagination/retries are not counted separately',
    ['scope', 'operation'],
)


@dataclass
class RebuildReads:
    started: float = field(default_factory=time.monotonic)
    manifests: dict = field(default_factory=dict)
    proofs: dict = field(default_factory=dict)


_current: ContextVar[RebuildReads | None] = ContextVar('audio_rebuild_reads', default=None)


def listing_reuse_enabled() -> bool:
    return os.getenv('SYNC_GCS_REBUILD_LISTING_REUSE_ENABLED', '1').strip().lower() not in {'0', 'false', 'off'}


def current() -> RebuildReads | None:
    return _current.get()


def operation(name: str):
    OPERATIONS.labels(scope='rebuild' if current() is not None else 'read', operation=name).inc()


@contextmanager
def rebuilding():
    token = _current.set(RebuildReads())
    operation('rebuild')
    try:
        yield
    finally:
        _current.reset(token)


def has_metadata(blob) -> bool:
    # Without metageneration we cannot pin the metadata interpretation, so refresh.
    return (
        getattr(blob, 'generation', None) is not None
        and getattr(blob, 'metageneration', None) is not None
        and isinstance(blob.metadata, dict)
        and blob.size is not None
    )


def pinned_download(blob, kwargs):
    """The body must match the exact metadata snapshot used to interpret it."""
    result = dict(kwargs)
    generation = int(blob.generation)
    if generation <= 0:
        raise ValueError('audio object requires generation')
    if result.get('if_generation_match') is not None and int(result['if_generation_match']) != generation:
        raise PreconditionFailed('audio generation changed')
    result['if_generation_match'] = generation
    metageneration = getattr(blob, 'metageneration', None)
    if metageneration is not None:
        metageneration = int(metageneration)
        if (
            result.get('if_metageneration_match') is not None
            and int(result['if_metageneration_match']) != metageneration
        ):
            raise PreconditionFailed('audio metadata generation changed')
        result['if_metageneration_match'] = metageneration
    return result
