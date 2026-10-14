"""Index requirements owned by durable channel inbox admission."""

from database.firestore_query_types import FieldIndexRequirement, FirestoreIndexField, FirestoreIndexRequirement

MESSAGING_INDEX_REQUIREMENTS = (
    FirestoreIndexRequirement(
        'chat_context_summary_source',
        'messages',
        'COLLECTION',
        tuple(FirestoreIndexField(name, order='ASCENDING') for name in ('chat_session_id', 'created_at', '__name__')),
    ),
    FirestoreIndexRequirement(
        'messaging_inbox_fifo',
        'inbox',
        'COLLECTION',
        tuple(FirestoreIndexField(name, order='ASCENDING') for name in ('status', 'created_at', '__name__')),
    ),
    FirestoreIndexRequirement(
        'messaging_pending_recovery',
        'inbox',
        'COLLECTION_GROUP',
        tuple(
            FirestoreIndexField(name, order='ASCENDING')
            for name in ('status', 'channel', 'provider', 'created_at', '__name__')
        ),
    ),
    FirestoreIndexRequirement(
        'messaging_expired_notices',
        'inbox',
        'COLLECTION_GROUP',
        tuple(FirestoreIndexField(name, order='ASCENDING') for name in ('status', 'channel', 'provider', '__name__')),
    ),
    FirestoreIndexRequirement(
        'messaging_done_retention',
        'inbox',
        'COLLECTION_GROUP',
        tuple(FirestoreIndexField(name, order='ASCENDING') for name in ('status', 'done_at', '__name__')),
    ),
    FirestoreIndexRequirement(
        'messaging_unknown_retention',
        'channel_identities',
        'COLLECTION',
        tuple(FirestoreIndexField(name, order='ASCENDING') for name in ('active', 'last_inbound_at', '__name__')),
    ),
)

MESSAGING_FIELD_REQUIREMENTS = (
    FieldIndexRequirement('messaging_waitlist_expiry', 'channel_waitlist', 'expires_at', ('ASCENDING',)),
)
