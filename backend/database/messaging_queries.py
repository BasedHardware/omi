"""Index requirements owned by durable channel inbox admission."""

from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement

MESSAGING_INDEX_REQUIREMENTS = (
    FirestoreIndexRequirement(
        'messaging_inbox_fifo',
        'inbox',
        'COLLECTION',
        tuple(FirestoreIndexField(name, order='ASCENDING') for name in ('status', 'created_at', '__name__')),
    ),
)
