"""Query specs owned by the Review feature (registered in the shared index registry)."""

from database.firestore_query_types import FirestoreIndexField as I, FirestoreQueryFilter as F, FirestoreQuerySpec as Q

PROPOSALS = Q(
    'review_pending_proposals',
    'review_proposals',
    'COLLECTION',
    (F('status', '==', 'status'),),
    (I('status', order='ASCENDING'), I('created_at', order='DESCENDING'), I('__name__', order='DESCENDING')),
)
CHANGES = Q(
    'review_recent_changes',
    'review_changes',
    'COLLECTION',
    (F('created_at', '>=', 'since'),),
    (I('created_at', order='DESCENDING'), I('__name__', order='DESCENDING')),
)
ENTITY_FACTS = Q(
    'review_entity_facts',
    'memories',
    'COLLECTION',
    (F('subject_entity_id', '==', 'entity_id'),),
    (I('subject_entity_id', order='ASCENDING'), I('created_at', order='DESCENDING'), I('__name__', order='DESCENDING')),
)
CANONICAL_FACTS = Q(
    'review_canonical_entity_facts',
    'memory_items',
    'COLLECTION',
    (F('subject_entity_id', '==', 'entity_id'),),
    (
        I('subject_entity_id', order='ASCENDING'),
        I('captured_at', order='DESCENDING'),
        I('__name__', order='DESCENDING'),
    ),
)
PROJECT_TASKS = Q(
    'review_project_tasks',
    'action_items',
    'COLLECTION',
    (F('workstream_id', '==', 'entity_id'),),
    (I('workstream_id', order='ASCENDING'), I('created_at', order='DESCENDING'), I('__name__', order='DESCENDING')),
)
REVIEW_QUERY_SPECS = (PROPOSALS, CHANGES, ENTITY_FACTS, CANONICAL_FACTS, PROJECT_TASKS)
