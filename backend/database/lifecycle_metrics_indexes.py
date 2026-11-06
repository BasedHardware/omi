"""Pure index declarations for lifecycle alarm samplers and minimal CI."""

from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement


def _index(name, collection, *fields):
    return FirestoreIndexRequirement(
        name,
        collection,
        'COLLECTION',
        tuple(FirestoreIndexField(field, order='ASCENDING') for field in (*fields, '__name__')),
    )


INDEX_REQUIREMENTS = (
    _index('enrichment_summary_repair_stock', 'sync_reprocess_outbox', 'summary_repair', 'due_at'),
    _index('enrichment_active_cohort', 'sync_reprocess_outbox', 'dormant', 'first_pending_at'),
    _index('enrichment_lane_stock', 'sync_reprocess_outbox', 'summary_lane', 'due_at'),
    _index('finalization_byok_entry_cohort', 'conversation_finalization_jobs', 'status', 'blocked_byok_at'),
)
