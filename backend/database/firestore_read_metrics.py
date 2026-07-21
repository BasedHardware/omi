"""Low-cardinality telemetry for Firestore reads that can amplify with user data.

The enum-backed labels deliberately rule out user identifiers, query text, and
routes. Add a family only for a reviewed, bounded set of read paths.
"""

from enum import StrEnum

from prometheus_client import Counter, Histogram


class FirestoreReadFamily(StrEnum):
    ACTION_ITEMS_LIST = 'action_items_list'
    LISTEN_MONTHLY_USAGE = 'listen_monthly_usage'


class FirestoreReadMode(StrEnum):
    UNBOUNDED = 'unbounded'


FIRESTORE_READ_OPERATIONS = Counter(
    'omi_firestore_read_operations_total',
    'Firestore reads by reviewed query family and boundedness',
    ['family', 'mode'],
)

FIRESTORE_DOCUMENTS_PER_OPERATION = Histogram(
    'omi_firestore_documents_per_operation',
    'Firestore documents iterated for a reviewed read operation',
    ['family'],
    buckets=(0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500),
)


def record_firestore_read(
    family: FirestoreReadFamily,
    mode: FirestoreReadMode,
    documents: int,
) -> None:
    """Record one completed Firestore read without accepting dynamic labels."""
    FIRESTORE_READ_OPERATIONS.labels(family=family.value, mode=mode.value).inc()
    FIRESTORE_DOCUMENTS_PER_OPERATION.labels(family=family.value).observe(documents)
