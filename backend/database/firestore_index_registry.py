"""Repository-owned Firestore query and index requirements.

The Firebase manifest is generated from this registry.  Query specs are added
incrementally: a registered query spec both builds its production query and
declares the exact composite index that query needs.  Existing index-only
requirements remain explicit here until their callers are migrated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class FirestoreIndexField:
    field_path: str
    order: str | None = None
    array_config: str | None = None

    def to_manifest(self) -> dict[str, str]:
        if self.order is not None:
            return {'fieldPath': self.field_path, 'order': self.order}
        if self.array_config is not None:
            return {'fieldPath': self.field_path, 'arrayConfig': self.array_config}
        raise ValueError(f'Firestore index field {self.field_path!r} needs order or array_config')


@dataclass(frozen=True)
class FirestoreIndexRequirement:
    identifier: str
    collection_group: str
    query_scope: str
    fields: tuple[FirestoreIndexField, ...]

    def to_manifest(self) -> dict[str, Any]:
        return {
            'collectionGroup': self.collection_group,
            'queryScope': self.query_scope,
            'fields': [field.to_manifest() for field in self.fields],
        }

    @property
    def signature(self) -> tuple[str, str, tuple[tuple[str, str], ...]]:
        return (
            self.collection_group,
            self.query_scope,
            tuple((field.field_path, field.order or field.array_config or '') for field in self.fields),
        )


@dataclass(frozen=True)
class FirestoreQueryFilter:
    field_path: str
    operator: str
    value_name: str


@dataclass(frozen=True)
class FirestoreQuerySpec:
    """A serving compound query and the index requirement derived from it."""

    identifier: str
    collection_group: str
    query_scope: str
    filters: tuple[FirestoreQueryFilter, ...]
    index_fields: tuple[FirestoreIndexField, ...]

    @property
    def index_requirement(self) -> FirestoreIndexRequirement:
        return FirestoreIndexRequirement(
            identifier=self.identifier,
            collection_group=self.collection_group,
            query_scope=self.query_scope,
            fields=self.index_fields,
        )

    @property
    def query_signature(self) -> tuple[str, str, tuple[tuple[str, str], ...]]:
        return (
            self.collection_group,
            self.query_scope,
            tuple((query_filter.field_path, query_filter.operator) for query_filter in self.filters),
        )

    def build(
        self,
        collection: Any,
        values: Mapping[str, Any],
        *,
        field_filter_factory: Callable[[str, str, Any], Any],
    ) -> Any:
        """Build the actual Firestore query from declared filters and values."""

        query = collection
        for query_filter in self.filters:
            try:
                value = values[query_filter.value_name]
            except KeyError as exc:
                raise ValueError(f'{self.identifier} requires {query_filter.value_name!r}') from exc
            query = query.where(filter=field_filter_factory(query_filter.field_path, query_filter.operator, value))
        return query


def _asc(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, order='ASCENDING')


def _desc(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, order='DESCENDING')


def _contains(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, array_config='CONTAINS')


# These explicit requirements preserve the current deployed index set while
# callers migrate one compound serving query at a time into QUERY_SPECS.
INDEX_ONLY_REQUIREMENTS = (
    FirestoreIndexRequirement(
        'memory_items_collection_group_uid_generation_updated',
        'memory_items',
        'COLLECTION_GROUP',
        (_asc('uid'), _asc('generation'), _desc('updated_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'conversations_category_created',
        'conversations',
        'COLLECTION',
        (_asc('discarded'), _asc('status'), _asc('structured.category'), _desc('created_at'), _desc('__name__')),
    ),
    # `GET /v1/conversations?sources=...` retains the legacy
    # `include_discarded=true` default, so this is distinct from the archive
    # query below that explicitly excludes discarded captures.
    FirestoreIndexRequirement(
        'conversations_source_status_created',
        'conversations',
        'COLLECTION',
        (_asc('source'), _asc('status'), _desc('created_at'), _desc('__name__')),
    ),
    FirestoreIndexRequirement(
        'conversations_discarded_source_status_created',
        'conversations',
        'COLLECTION',
        (_asc('discarded'), _asc('source'), _asc('status'), _desc('created_at'), _desc('__name__')),
    ),
    FirestoreIndexRequirement(
        'conversations_status_finished',
        'conversations',
        'COLLECTION',
        (_asc('status'), _asc('finished_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'memory_items_tier_status_updated',
        'memory_items',
        'COLLECTION',
        (_asc('tier'), _asc('status'), _desc('updated_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'memory_items_tier_status_expires',
        'memory_items',
        'COLLECTION',
        (_asc('tier'), _asc('status'), _asc('expires_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'memory_items_source_state_updated',
        'memory_items',
        'COLLECTION',
        (_asc('source_state'), _desc('updated_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'memory_operations_status_created',
        'memory_operations',
        'COLLECTION',
        (_asc('status'), _desc('created_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'screen_activity_app_timestamp',
        'screen_activity',
        'COLLECTION',
        (_asc('appName'), _asc('timestamp'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'candidates_status_generation_created',
        'candidates',
        'COLLECTION',
        (_asc('status'), _asc('account_generation'), _desc('created_at'), _desc('__name__')),
    ),
    FirestoreIndexRequirement(
        'action_items_completed_due',
        'action_items',
        'COLLECTION',
        (_asc('completed'), _asc('due_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'action_items_conversation_due',
        'action_items',
        'COLLECTION',
        (_asc('conversation_id'), _asc('due_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'action_items_completed_conversation_due',
        'action_items',
        'COLLECTION',
        (_asc('completed'), _asc('conversation_id'), _asc('due_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'candidate_integration_outbox_generation_status',
        'candidate_integration_outbox',
        'COLLECTION',
        (_asc('account_generation'), _asc('status'), _asc('__name__')),
    ),
)


ACTIVE_ATTENTION_OVERRIDE_QUERY = FirestoreQuerySpec(
    identifier='task_attention_overrides_active_by_generation',
    collection_group='task_attention_overrides',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('account_generation', '==', 'account_generation'),
        FirestoreQueryFilter('expires_at', '>', 'now'),
    ),
    index_fields=(_asc('account_generation'), _asc('expires_at'), _asc('__name__')),
)

CANDIDATES_COMPATIBILITY_QUERY = FirestoreQuerySpec(
    identifier='candidates_generation_created',
    collection_group='candidates',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('account_generation', '==', 'account_generation'),),
    index_fields=(_asc('account_generation'), _desc('created_at'), _desc('__name__')),
)

LEGACY_CONVERSATION_RECOVERY_QUERY = FirestoreQuerySpec(
    identifier='staged_tasks_legacy_conversation_recovery_by_id',
    collection_group='staged_tasks',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('source', '==', 'source'),),
    index_fields=(_asc('source'), _asc('__name__')),
)

REQUIRED_MEMORY_PROCESSING_QUERY = FirestoreQuerySpec(
    identifier='memory_items_required_processing_by_capture',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', '==', 'processing_state'),
        FirestoreQueryFilter('promotion.required', '==', 'required'),
        FirestoreQueryFilter('promotion.processing_status', 'in', 'processing_statuses'),
    ),
    index_fields=(
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
        _asc('promotion.required'),
        _asc('promotion.processing_status'),
        _asc('captured_at'),
        _asc('memory_id'),
        _asc('__name__'),
    ),
)

CANONICAL_CONSOLIDATION_QUERY = FirestoreQuerySpec(
    identifier='memory_items_consolidation_by_capture',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', '==', 'processing_state'),
        FirestoreQueryFilter('source_state', '==', 'source_state'),
    ),
    index_fields=(
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
        _asc('source_state'),
        _asc('captured_at'),
        _asc('memory_id'),
        _asc('__name__'),
    ),
)

POLICY_EXPIRED_SHORT_TERM_QUERY = FirestoreQuerySpec(
    identifier='memory_items_policy_expired_short_term_by_capture',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', '==', 'processing_state'),
        FirestoreQueryFilter('source_state', '==', 'source_state'),
        FirestoreQueryFilter('captured_at', '<=', 'captured_at'),
    ),
    index_fields=(
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
        _asc('source_state'),
        _asc('captured_at'),
        _asc('memory_id'),
        _asc('__name__'),
    ),
)

CANONICAL_GRAPH_READ_QUERY = FirestoreQuerySpec(
    identifier='memory_items_canonical_graph_read',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('account_generation', '==', 'account_generation'),
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', '==', 'processing_state'),
        FirestoreQueryFilter('graph_ready', '==', 'graph_ready'),
    ),
    index_fields=(
        _asc('account_generation'),
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
        _asc('graph_ready'),
        _desc('updated_at'),
        _desc('__name__'),
    ),
)

CANONICAL_MEMORY_ATLAS_READ_QUERY = FirestoreQuerySpec(
    identifier='memory_items_canonical_atlas_read',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('account_generation', '==', 'account_generation'),
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', '==', 'processing_state'),
    ),
    index_fields=(
        _asc('account_generation'),
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
        _desc('updated_at'),
        _desc('__name__'),
    ),
)

# Collection-scoped newest-first scan for universal mixed list cursor paging.
# Equality filters are intentionally empty: access/device/pending/archive are
# applied after each bounded raw page so filtered rows still advance the keyset.
# Firestore auto single-field indexes only cover field+__name__ in the *same*
# direction (DESC+DESC / ASC+ASC). updated_at DESC + __name__ ASC is a real
# composite and must be declared (#11684).
UNIVERSAL_CANONICAL_LIST_SCAN_QUERY = FirestoreQuerySpec(
    identifier='memory_items_universal_list_scan',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(),
    index_fields=(_desc('updated_at'), _asc('__name__')),
)

# Historical dual-stream keysets for effective updated_at-or-created_at order.
# Docs with updated_at ride the updated stream; created stream skips those
# duplicates in Python so each document is emitted once. Opposite-direction
# __name__ tie-breaks need composite indexes (same class as #11684).
UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY = FirestoreQuerySpec(
    identifier='memories_universal_list_scan_updated_at',
    collection_group='memories',
    query_scope='COLLECTION',
    filters=(),
    index_fields=(_desc('updated_at'), _asc('__name__')),
)

UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY = FirestoreQuerySpec(
    identifier='memories_universal_list_scan_created_at',
    collection_group='memories',
    query_scope='COLLECTION',
    filters=(),
    index_fields=(_desc('created_at'), _asc('__name__')),
)

CONVERSATION_SOURCE_MEMORY_QUERY = FirestoreQuerySpec(
    identifier='memory_items_by_conversation_source',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('source_ids', 'array_contains', 'source_id'),),
    index_fields=(
        _contains('source_ids'),
        _asc('__name__'),
    ),
)

SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY = FirestoreQuerySpec(
    identifier='memory_items_superseded_by_canonical_target',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('canonical_memory_id', 'in', 'target_memory_ids'),
    ),
    index_fields=(
        _asc('status'),
        _asc('canonical_memory_id'),
        _asc('__name__'),
    ),
)

SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY = FirestoreQuerySpec(
    identifier='memory_items_superseded_by_legacy_target',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('superseded_by', 'in', 'target_memory_ids'),
    ),
    index_fields=(
        _asc('status'),
        _asc('superseded_by'),
        _asc('__name__'),
    ),
)

EXPIRED_SHORT_TERM_LIFECYCLE_QUERY = FirestoreQuerySpec(
    identifier='memory_items_expired_short_term_by_expiry',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', '==', 'processing_state'),
        FirestoreQueryFilter('expires_at', '<=', 'expires_at'),
    ),
    index_fields=(
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
        _asc('expires_at'),
        _asc('memory_id'),
        _asc('__name__'),
    ),
)

DUE_MEMORY_OUTBOX_QUERY = FirestoreQuerySpec(
    identifier='memory_outbox_due_by_availability',
    collection_group='memory_outbox',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('available_at', '<=', 'available_at'),
    ),
    index_fields=(_asc('status'), _asc('available_at'), _asc('__name__')),
)

EXPIRED_MEMORY_OUTBOX_LEASE_QUERY = FirestoreQuerySpec(
    identifier='memory_outbox_expired_lease_by_event_type',
    collection_group='memory_outbox',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('event_type', '==', 'event_type'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('lease_expires_at', '<=', 'lease_expires_at'),
    ),
    index_fields=(
        _asc('event_type'),
        _asc('status'),
        _asc('lease_expires_at'),
        _asc('__name__'),
    ),
)

REVIEW_QUEUE_BY_FACT_QUERY = FirestoreQuerySpec(
    identifier='memory_review_queue_by_fact',
    collection_group='memory_review_queue',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter(
            'fact_id',
            'in',
            'fact_ids',
        ),
    ),
    index_fields=(
        _asc('fact_id'),
        _asc('__name__'),
    ),
)

REVIEW_QUEUE_BY_CONFLICT_QUERY = FirestoreQuerySpec(
    identifier='memory_review_queue_by_conflict',
    collection_group='memory_review_queue',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter(
            'conflict_with',
            'array_contains_any',
            'conflict_ids',
        ),
    ),
    index_fields=(
        _contains('conflict_with'),
        _asc('__name__'),
    ),
)

REVIEW_QUEUE_BY_STATUS_QUERY = FirestoreQuerySpec(
    identifier='memory_review_queue_by_status_impact',
    collection_group='memory_review_queue',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('status', '==', 'status'),),
    index_fields=(
        _asc('status'),
        _desc('impact'),
        _desc('created_at'),
        _desc('__name__'),
    ),
)

REVIEW_QUEUE_ORDERED_QUERY = FirestoreQuerySpec(
    identifier='memory_review_queue_by_impact',
    collection_group='memory_review_queue',
    query_scope='COLLECTION',
    filters=(),
    index_fields=(
        _desc('impact'),
        _desc('created_at'),
        _desc('__name__'),
    ),
)

REVIEW_QUEUE_BY_STATUS_ID_QUERY = FirestoreQuerySpec(
    identifier='memory_review_queue_by_status_id',
    collection_group='memory_review_queue',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('status', '==', 'status'),),
    index_fields=(
        _asc('status'),
        _desc('__name__'),
    ),
)

STALE_IN_PROGRESS_CONVERSATIONS_QUERY = FirestoreQuerySpec(
    identifier='conversations_in_progress_by_finished_at',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('status', '==', 'status'),),
    index_fields=(
        _asc('status'),
        _asc('finished_at'),
        _asc('__name__'),
    ),
)

CHAT_FIRST_DEFERRALS_DUE_QUERY = FirestoreQuerySpec(
    identifier='chat_first_deferrals_due',
    collection_group='chat_first_deferrals',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('account_generation', '==', 'account_generation'),
        FirestoreQueryFilter('state', '==', 'state'),
        FirestoreQueryFilter('due_at', '<=', 'due_at'),
    ),
    index_fields=(_asc('account_generation'), _asc('state'), _asc('due_at'), _asc('__name__')),
)

CHAT_FIRST_DEFERRALS_SUBJECT_QUERY = FirestoreQuerySpec(
    identifier='chat_first_deferrals_by_subject',
    collection_group='chat_first_deferrals',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('account_generation', '==', 'account_generation'),
        FirestoreQueryFilter('state', '==', 'state'),
        FirestoreQueryFilter('subject.kind', '==', 'subject_kind'),
        FirestoreQueryFilter('subject.id', '==', 'subject_id'),
    ),
    index_fields=(
        _asc('account_generation'),
        _asc('state'),
        _asc('subject.kind'),
        _asc('subject.id'),
        _asc('__name__'),
    ),
)

QUERY_SPECS = (
    CANDIDATES_COMPATIBILITY_QUERY,
    DUE_MEMORY_OUTBOX_QUERY,
    EXPIRED_MEMORY_OUTBOX_LEASE_QUERY,
    REVIEW_QUEUE_BY_FACT_QUERY,
    REVIEW_QUEUE_BY_CONFLICT_QUERY,
    REVIEW_QUEUE_BY_STATUS_QUERY,
    REVIEW_QUEUE_ORDERED_QUERY,
    REVIEW_QUEUE_BY_STATUS_ID_QUERY,
    REQUIRED_MEMORY_PROCESSING_QUERY,
    CANONICAL_CONSOLIDATION_QUERY,
    POLICY_EXPIRED_SHORT_TERM_QUERY,
    CANONICAL_GRAPH_READ_QUERY,
    CANONICAL_MEMORY_ATLAS_READ_QUERY,
    UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY,
    CONVERSATION_SOURCE_MEMORY_QUERY,
    SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
    SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
    EXPIRED_SHORT_TERM_LIFECYCLE_QUERY,
    ACTIVE_ATTENTION_OVERRIDE_QUERY,
    LEGACY_CONVERSATION_RECOVERY_QUERY,
    STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
    CHAT_FIRST_DEFERRALS_DUE_QUERY,
    CHAT_FIRST_DEFERRALS_SUBJECT_QUERY,
)

_INDEX_ONLY_REQUIREMENT_SIGNATURES = frozenset(requirement.signature for requirement in INDEX_ONLY_REQUIREMENTS)


def _index_fields_need_composite_manifest(index_fields: tuple[FirestoreIndexField, ...]) -> bool:
    """Return True when Firestore will not serve this order from automatic indexes.

    Automatic single-field indexes cover ``field ASC, __name__ ASC`` and
    ``field DESC, __name__ DESC`` only. A lone ordered field with an opposite
    ``__name__`` direction is a composite Firestore must be given explicitly
    (#11684). Multi-field orders always need the composite manifest.
    Array-contains (+ ``__name__``) stays out of the composite manifest — the
    existing unified-memory index contract keeps those automatic.
    """

    non_name = [field for field in index_fields if field.field_path != '__name__']
    name_fields = [field for field in index_fields if field.field_path == '__name__']
    if len(non_name) > 1:
        return True
    if len(non_name) != 1 or len(name_fields) != 1:
        return False
    ordered = non_name[0]
    name = name_fields[0]
    if ordered.order is None or name.order is None:
        return False
    return ordered.order != name.order


def _query_spec_index_requirements() -> tuple[FirestoreIndexRequirement, ...]:
    """One composite index per signature, even when two serving queries share it."""
    seen = set(_INDEX_ONLY_REQUIREMENT_SIGNATURES)
    requirements: list[FirestoreIndexRequirement] = []
    for spec in QUERY_SPECS:
        if not _index_fields_need_composite_manifest(spec.index_fields):
            continue
        signature = spec.index_requirement.signature
        if signature in seen:
            continue
        seen.add(signature)
        requirements.append(spec.index_requirement)
    return tuple(requirements)


INDEX_REQUIREMENTS = (
    *INDEX_ONLY_REQUIREMENTS,
    *_query_spec_index_requirements(),
)


# Firestore auto-indexes every field of every document in both directions unless a field is
# explicitly exempted. For large text fields that no query ever filters or orders on, that index
# is pure storage cost: measured on `screen_activity`, single-field index bytes were roughly three
# times the document bytes, and the `ocrText` index alone was the majority of the collection.
# `ocrText` is only ever read back and rendered; semantic search runs on Pinecone vectors, not on
# Firestore. Exempting a field only removes single-field indexes — composite indexes declared
# above are unaffected, so a field named in a composite index can still appear here.
FIELD_INDEXING_EXEMPTIONS: tuple[tuple[str, str], ...] = (
    ('screen_activity', 'ocrText'),
    ('screen_activity', 'windowTitle'),
    ('screen_activity', 'deviceName'),
    ('screen_activity', 'clientDeviceId'),
)


def firebase_index_manifest() -> dict[str, list[dict[str, Any]]]:
    """Return Firebase's canonical composite-index manifest deterministically."""

    signatures: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    indexes: list[dict[str, Any]] = []
    for requirement in INDEX_REQUIREMENTS:
        if requirement.signature in signatures:
            raise ValueError(f'duplicate Firestore index requirement: {requirement.identifier}')
        signatures.add(requirement.signature)
        indexes.append(requirement.to_manifest())
    field_overrides = [
        {
            'collectionGroup': collection_group,
            'fieldPath': field_path,
            'ttl': False,
            'indexes': [],
        }
        for collection_group, field_path in FIELD_INDEXING_EXEMPTIONS
    ]
    return {'indexes': indexes, 'fieldOverrides': field_overrides}
