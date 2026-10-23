"""Owned MCP card projections and query/index contracts."""

from database.firestore_query_types import FirestoreIndexField, FirestoreQueryFilter, FirestoreQuerySpec


def _asc(path: str) -> FirestoreIndexField:
    return FirestoreIndexField(path, order='ASCENDING')


def _desc(path: str) -> FirestoreIndexField:
    return FirestoreIndexField(path, order='DESCENDING')


MCP_CONVERSATION_CARD_FIELD_PATHS = (
    'id',
    'status',
    'discarded',
    'deleted',
    'dream_duplicate_of',
    'relevance_decision',
    'sync_relevance_user_kept',
    'has_photos',
    'starred',
    'folder_user_set',
    'created_at',
    'started_at',
    'finished_at',
    'language',
    'is_locked',
    'data_protection_level',
    'user_title',
    'source',
    'is_call',
    'call_platform',
    'calendar_event_id',
    'calendar_meeting_context',
    'external_data.calendar_meeting_context',
    'calendar_event',
    'structured.title',
    'structured.overview',
    'structured.category',
    'structured.emoji',
)
MCP_CONVERSATION_TRANSCRIPT_FIELD_PATHS = MCP_CONVERSATION_CARD_FIELD_PATHS + (
    'transcript_segments',
    'transcript_segments_compressed',
    'has_transcript_corrections',
)

MCP_DAILY_RECORDINGS_QUERY = FirestoreQuerySpec(
    identifier='mcp_daily_recordings_count',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('discarded', '==', 'discarded'),
        FirestoreQueryFilter('started_at', '>=', 'start'),
        FirestoreQueryFilter('started_at', '<=', 'end'),
    ),
    index_fields=(_asc('discarded'), _asc('started_at'), _asc('__name__')),
)

# MCP candidate windows use a single necessary predicate; the policy adapter
# rechecks every filter after canonical/historical suppression and decryption.
MCP_MEMORY_FILTER_QUERIES = {}
for _origin in ('memory_items', 'memories'):
    for _predicate, _path, _op in (
        ('all', None, None),
        ('updated_after', 'updated_at', '>='),
        ('reviewed', 'promotion.reviewed' if _origin == 'memory_items' else 'reviewed', '=='),
        ('manually_added', 'user_asserted' if _origin == 'memory_items' else 'manually_added', '=='),
        ('categories', 'promotion.category' if _origin == 'memory_items' else 'category', 'in'),
    ):
        MCP_MEMORY_FILTER_QUERIES[(_origin, _predicate)] = FirestoreQuerySpec(
            identifier=f'mcp_{_origin}_{_predicate}',
            collection_group=_origin,
            query_scope='COLLECTION',
            filters=(FirestoreQueryFilter(_path, _op, _predicate),) if _path is not None and _op is not None else (),
            index_fields=((_asc(_path),) if _path and _path != 'updated_at' else ())
            + (_desc('updated_at'), _asc('__name__')),
        )

MCP_CONVERSATION_CARD_QUERY_SPECS: dict[tuple[bool, bool, bool], FirestoreQuerySpec] = {}
for _has_categories in (False, True):
    for _has_start_date in (False, True):
        for _has_end_date in (False, True):
            _suffixes = []
            _filters = [
                FirestoreQueryFilter('discarded', '==', 'discarded'),
                FirestoreQueryFilter('status', '==', 'status'),
            ]
            _index_fields = [_asc('discarded'), _asc('status')]
            if _has_categories:
                _suffixes.append('category')
                _filters.append(FirestoreQueryFilter('structured.category', 'in', 'categories'))
                _index_fields.append(_asc('structured.category'))
            if _has_start_date:
                _suffixes.append('start')
                _filters.append(FirestoreQueryFilter('created_at', '>=', 'start_date'))
            if _has_end_date:
                _suffixes.append('end')
                _filters.append(FirestoreQueryFilter('created_at', '<=', 'end_date'))
            _variant = '_'.join(_suffixes) or 'all'
            MCP_CONVERSATION_CARD_QUERY_SPECS[(_has_categories, _has_start_date, _has_end_date)] = FirestoreQuerySpec(
                identifier=f'mcp_conversation_cards_{_variant}',
                collection_group='conversations',
                query_scope='COLLECTION',
                filters=tuple(_filters),
                index_fields=tuple((*_index_fields, _desc('created_at'), _desc('__name__'))),
            )
