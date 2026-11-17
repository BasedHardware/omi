"""Stateless pinned reads and operation counters; no metadata or proof cache."""

from contextlib import contextmanager
from contextvars import ContextVar

from google.api_core.exceptions import PreconditionFailed
from prometheus_client import Counter

OPERATIONS = Counter(
    'omi_sync_audio_gcs_operations_total',
    'Logical GCS calls attempted by audio reads; LIST pagination/retries are not counted separately',
    ['scope', 'operation'],
)


_in_rebuild: ContextVar[bool] = ContextVar('audio_gcs_in_rebuild', default=False)


def operation(name: str):
    OPERATIONS.labels(scope='rebuild' if _in_rebuild.get() else 'read', operation=name).inc()


@contextmanager
def rebuilding():
    token = _in_rebuild.set(True)
    operation('rebuild')
    try:
        yield
    finally:
        _in_rebuild.reset(token)


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
