OUTSIDE_SERVING_FIELD_INDEX_CALLERS = {
    ('fair_use_events', 'case_ref'): (
        'database/serving_query_reads.py:find_fair_use_case_snapshots',
        'routers/fair_use_admin.py:lookup_case,get_public_case_status',
        'web/admin/app/api/omi/fair-use/case/[caseRef]/route.ts:GET',
    ),
    ('chat_first_proactive_intents', 'created_at'): (
        'utils/task_intelligence/chat_first_materialization_health.py:_documents',
        'utils/other/jobs.py:start_job',
    ),
    ('chat_first_dead_letters', 'created_at'): (
        'utils/task_intelligence/chat_first_materialization_health.py:_documents',
        'utils/other/jobs.py:start_job',
    ),
    ('llm_usage', 'date'): (
        'web/admin/app/api/omi/stats/infra-costs/route.ts:GET',
        'database/llm_usage.py:get_global_top_features',
    ),
}
OUTSIDE_SERVING_FIELD_INDEXES = tuple(
    {
        'collectionGroup': collection,
        'fieldPath': field,
        'indexes': [
            {'order': 'ASCENDING', 'queryScope': 'COLLECTION'},
            {'order': 'DESCENDING', 'queryScope': 'COLLECTION'},
            {'arrayConfig': 'CONTAINS', 'queryScope': 'COLLECTION'},
            {'order': 'ASCENDING', 'queryScope': 'COLLECTION_GROUP'},
        ],
    }
    for collection, field in OUTSIDE_SERVING_FIELD_INDEX_CALLERS
)
