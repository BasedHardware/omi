"""Collection-level accounting for every Firestore document read.

Cloud Monitoring's ``firestore.googleapis.com/document/read_count`` carries no
collection or document-path dimension -- every one of its 31 descriptors reports
``module="__unknown__"`` for server SDKs -- so a read-volume regression is visible
in the bill but not attributable to anything. Hand-placed call-site counters only
ever cover the paths someone remembered to annotate, which is how the existing
``omi_firestore_read_operations_total`` ended up describing five query families
while production issued reads from several hundred sites.

This probe instead wraps the SDK's own read entry points, so coverage is
structural rather than remembered: a new call site is counted the day it is
written, without touching it. Lookups wrap ``DocumentReference.get`` and
``Client.get_all``; queries wrap ``Query.stream`` (the funnel for ``Query.get``
and ``CollectionReference.get`` / ``.stream``) and ``AggregationQuery.stream``.
It records only the collection *pattern* (document ids elided) and whether the
document existed, which is exactly the pair needed to find waste -- a read that
is billed but returns nothing.

Cardinality is bounded by construction: ids are stripped, and any pattern outside
the reviewed set collapses to ``other``. No uid, document id, or query text can
reach a label.
"""

import logging
import math
from typing import Any

from prometheus_client import Counter

logger = logging.getLogger(__name__)

__all__ = [
    'FIRESTORE_DOCUMENT_READS',
    'collection_pattern',
    'install_document_read_probe',
]


FIRESTORE_DOCUMENT_READS = Counter(
    'omi_firestore_document_reads_total',
    'Firestore document reads by collection pattern and whether the document existed. '
    'Includes lookups and query streams. outcome="miss" is a billed read that returned nothing.',
    ['collection', 'outcome'],
)


# Firestore bills an aggregation one read per batch of up to this many index
# entries, not one read per matched document.
_AGGREGATION_INDEX_ENTRIES_PER_READ = 1000


# Reviewed patterns. Anything else is folded into `other` so an unforeseen
# collection cannot expand the label space. Add a pattern here only after
# confirming it is a bounded, non-user-derived name.
_KNOWN_PATTERNS = frozenset(
    {
        'users',
        'users/conversations',
        'users/memory_items',
        'users/memory_outbox',
        'users/memory_historical_overrides',
        'users/memory_state',
        'users/task_intelligence_control',
        'users/recording_sessions',
        'users/conversation_finalization_jobs',
        'users/action_items',
        'users/photos',
        'users/conversations/photos',
        'users/hourly_usage',
        'users/messages',
        'users/fcm_tokens',
        'users/chat_messages',
        'users/people',
        'users/facts',
        'users/apps',
        'users/calendar_meetings',
        'users/payments',
        'users/usage',
        'account_deletions',
        'testers',
        'apps',
        'plugins',
        'migration_requests',
    }
)

_OTHER = 'other'
_UNKNOWN = 'unknown'


def collection_pattern(path_parts: Any) -> str:
    """Reduce a Firestore document path to its collection pattern.

    ``('users', 'abc123', 'conversations', 'def456')`` -> ``'users/conversations'``.
    Document ids sit at the odd indices and are dropped, so no user-derived value
    survives into a label.
    """
    try:
        parts = tuple(path_parts or ())
        if not parts:
            return _UNKNOWN
        pattern = '/'.join(str(parts[i]) for i in range(0, len(parts), 2))
    except Exception:
        return _UNKNOWN
    return pattern if pattern in _KNOWN_PATTERNS else _OTHER


def _record(path_parts: Any, exists: bool, amount: float = 1) -> None:
    """Count document reads. Never raises: telemetry must not break a read."""
    try:
        FIRESTORE_DOCUMENT_READS.labels(
            collection=collection_pattern(path_parts),
            outcome='hit' if exists else 'miss',
        ).inc(amount)
    except Exception:
        logger.warning('firestore document read probe failed to record', exc_info=True)


_installed = False


def install_document_read_probe() -> None:
    """Wrap SDK read entry points to count document reads by collection.

    Imported lazily and guarded on ImportError for the same reason the query
    retry compat shim in ``_client`` is: unit-test harnesses stub the ``google``
    namespace package, so there is no real SDK class to wrap and skipping is
    correct.
    """
    global _installed
    if _installed:
        return
    try:
        from google.cloud.firestore_v1.document import DocumentReference
        from google.cloud.firestore_v1.client import Client
        from google.cloud.firestore_v1.query import Query
        from google.cloud.firestore_v1.aggregation import AggregationQuery
    except ImportError:
        return

    original_get = DocumentReference.get
    original_get_all = Client.get_all
    original_stream = Query.stream
    original_agg_stream = AggregationQuery.stream

    def get(self: Any, *args: Any, **kwargs: Any) -> Any:
        snapshot = original_get(self, *args, **kwargs)
        _record(getattr(self, '_path', ()), bool(getattr(snapshot, 'exists', False)))
        return snapshot

    def get_all(self: Any, references: Any, *args: Any, **kwargs: Any) -> Any:
        # get_all streams; count each snapshot as it passes rather than
        # materialising the generator, which would change the caller's memory
        # profile on large batches.
        refs = list(references)
        for snapshot in original_get_all(self, refs, *args, **kwargs):
            reference = getattr(snapshot, 'reference', None)
            _record(getattr(reference, '_path', ()), bool(getattr(snapshot, 'exists', False)))
            yield snapshot

    def stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Query.get and CollectionReference.get/stream all call Query.stream
        # (google-cloud-firestore 2.20.0). Wrapping those too would double-count.
        for snapshot in original_stream(self, *args, **kwargs):
            reference = getattr(snapshot, 'reference', None)
            _record(getattr(reference, '_path', ()), bool(getattr(snapshot, 'exists', False)))
            yield snapshot

    def aggregation_stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        # AggregationQuery.get materialises this stream.
        #
        # An aggregation is NOT billed per matched document: "You are charged one
        # read operation for each batch of up to 1000 index entries read." Counting
        # the matched value directly would overstate a count() by up to 1000x and
        # would make cheap aggregations dominate this counter, which exists to
        # attribute the *billed* read line. Charge the billed batches instead.
        path = getattr(getattr(self, '_collection_ref', None), '_path', ())
        for result in original_agg_stream(self, *args, **kwargs):
            try:
                rows = result if isinstance(result, (list, tuple)) else (result,)
                for row in rows:
                    matched = int(getattr(row, 'value', 0) or 0)
                    billed = max(1, math.ceil(matched / _AGGREGATION_INDEX_ENTRIES_PER_READ))
                    _record(path, matched > 0, amount=billed)
            except Exception:
                logger.warning('firestore document read probe failed to record', exc_info=True)
            yield result

    setattr(DocumentReference, 'get', get)
    setattr(Client, 'get_all', get_all)
    setattr(Query, 'stream', stream)
    setattr(AggregationQuery, 'stream', aggregation_stream)
    _installed = True
