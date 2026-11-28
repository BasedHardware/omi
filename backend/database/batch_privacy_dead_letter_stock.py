"""Read-only stock census for delayed batch privacy erasure failures."""

from datetime import datetime, timezone
from functools import lru_cache
import logging
import time
from typing import Any

from google.cloud.firestore import FieldFilter
from prometheus_client import Gauge

from database._client import get_data_plane_firestore_client
from database.batch_privacy_late_intents import COLLECTION
from database.firestore_read_origin import read_origin
from database.redis_connection import create_bounded_redis_client

logger = logging.getLogger(__name__)
_INTERVAL_SECONDS = 300
_SAMPLE_KEY = 'omi:batch_privacy:post_window_dead_letter_stock:v1'
_EARLIEST_TIMESTAMP = datetime.min.replace(tzinfo=timezone.utc)

DEAD_LETTER_UNITS = Gauge(
    'omi_batch_pipeline_privacy_post_window_dead_letter_units',
    'Retained delayed batch erasure intent and receipt dead letters',
)
DEAD_LETTER_OBSERVED_AT = Gauge(
    'omi_batch_pipeline_privacy_post_window_dead_letter_observed_at_seconds',
    'Unix time of the last successful delayed batch erasure dead-letter count',
)


@lru_cache(maxsize=1)
def _redis_client():
    return create_bounded_redis_client(0.25)


def count_dead_letters(*, firestore_client: Any = None) -> int:
    """Both intent and receipt failures retain a timestamp until recovery removes the row.

    The collection has no separate resolution field. The timestamp range uses the
    built-in single-field index and excludes pending rows without a timestamp.
    """
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    return (
        client.collection(COLLECTION)
        .where(filter=FieldFilter('dead_lettered_at', '>=', _EARLIEST_TIMESTAMP))
        .count()
        .get(timeout=5, retry=None)[0][0]
        .value
    )


def publish_dead_letter_stock() -> None:
    try:
        # Keep the cooldown even on count failure. A missing Redis admission
        # leaves the metrics stale and never fans out Firestore reads.
        if not _redis_client().set(_SAMPLE_KEY, '1', nx=True, ex=_INTERVAL_SECONDS):
            return
        observed_at = time.time()
        with read_origin('job:publish_batch_privacy_dead_letter_stock'):
            stock = count_dead_letters()
        DEAD_LETTER_UNITS.set(stock)
        DEAD_LETTER_OBSERVED_AT.set(observed_at)
    except Exception as error:
        logger.warning('delayed batch erasure dead-letter stock unavailable error_type=%s', type(error).__name__)
