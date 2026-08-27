"""Collection-level accounting for every Firestore single-document read.

Cloud Monitoring's ``firestore.googleapis.com/document/read_count`` carries no
collection or document-path dimension -- every one of its 31 descriptors reports
``module="__unknown__"`` for server SDKs -- so a read-volume regression is visible
in the bill but not attributable to anything. Hand-placed call-site counters only
ever cover the paths someone remembered to annotate, which is how the existing
``omi_firestore_read_operations_total`` ended up describing five query families
while production issued reads from several hundred sites.

This probe instead wraps the SDK's own read entry points, so coverage is
structural rather than remembered: a new call site is counted the day it is
written, without touching it. It records only the collection *pattern* (document
ids elided) and whether the document existed, which is exactly the pair needed to
find waste -- a read that is billed but returns nothing.

Cardinality is bounded by construction: ids are stripped, and any pattern outside
the reviewed set collapses to ``other``. No uid, document id, or query text can
reach a label.
"""

import logging
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
    'Single-document Firestore reads by collection pattern and whether the document existed. '
    'outcome="miss" is a billed read that returned nothing.',
    ['collection', 'outcome'],
)


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


def _record(path_parts: Any, exists: bool) -> None:
    """Count one document read. Never raises: telemetry must not break a read."""
    try:
        FIRESTORE_DOCUMENT_READS.labels(
            collection=collection_pattern(path_parts),
            outcome='hit' if exists else 'miss',
        ).inc()
    except Exception:
        logger.warning('firestore document read probe failed to record', exc_info=True)


_installed = False


def install_document_read_probe() -> None:
    """Wrap ``DocumentReference.get`` and ``Client.get_all`` to count reads.

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
    except ImportError:
        return

    original_get = DocumentReference.get
    original_get_all = Client.get_all

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

    setattr(DocumentReference, 'get', get)
    setattr(Client, 'get_all', get_all)
    _installed = True
