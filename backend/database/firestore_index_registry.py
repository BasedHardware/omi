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
    # Admin cost dashboard: server-side SUM aggregations over the gateway
    # accounting ledger (web/admin lib/services/gateway-ledger.ts). Unlike
    # plain equality queries, SUM aggregations need the summed field
    # (estimated_cost_micro_usd) inside a composite index. One index per
    # filter shape, each with and without the BYOK-excluding payer filter.
    FirestoreIndexRequirement(
        'llm_gateway_attempts_date_cost_sum',
        'llm_gateway_attempts',
        'COLLECTION',
        (_asc('date'), _asc('estimated_cost_micro_usd'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'llm_gateway_attempts_date_provider_cost_sum',
        'llm_gateway_attempts',
        'COLLECTION',
        (_asc('date'), _asc('provider'), _asc('estimated_cost_micro_usd'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'llm_gateway_attempts_date_feature_cost_sum',
        'llm_gateway_attempts',
        'COLLECTION',
        (_asc('date'), _asc('feature'), _asc('estimated_cost_micro_usd'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'llm_gateway_attempts_date_payer_cost_sum',
        'llm_gateway_attempts',
        'COLLECTION',
        (_asc('date'), _asc('payer'), _asc('estimated_cost_micro_usd'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'llm_gateway_attempts_date_provider_payer_cost_sum',
        'llm_gateway_attempts',
        'COLLECTION',
        (_asc('date'), _asc('provider'), _asc('payer'), _asc('estimated_cost_micro_usd'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'llm_gateway_attempts_date_feature_payer_cost_sum',
        'llm_gateway_attempts',
        'COLLECTION',
        (_asc('date'), _asc('feature'), _asc('payer'), _asc('estimated_cost_micro_usd'), _asc('__name__')),
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
    # Several conversations.py serving reads filter by `status` alone and sort by
    # `created_at` descending (get_in_progress_conversation, get_action_items,
    # get_last_completed_conversation, and the default `GET /v1/conversations`
    # call with include_discarded=True). Production has this index only because
    # it was created by hand; a fresh self-host 400s with FailedPrecondition the
    # first time any of those paths runs.
    FirestoreIndexRequirement(
        'conversations_status_created',
        'conversations',
        'COLLECTION',
        (_asc('status'), _desc('created_at'), _desc('__name__')),
    ),
    # `get_conversations`/`get_conversations_count`/`get_conversations_without_photos`
    # called with include_discarded=False and a `statuses` filter (no source/category)
    # produce this shape. Same story as above: hand-created in production, never
    # declared here.
    FirestoreIndexRequirement(
        'conversations_discarded_status_created',
        'conversations',
        'COLLECTION',
        (_asc('discarded'), _asc('status'), _desc('created_at'), _desc('__name__')),
    ),
    # `get_memories`' default path (no category/date filters, default
    # sort='scoring_desc') orders by `scoring` then `created_at`, both descending,
    # with zero `where` filters. Firestore still needs a composite for a bare
    # multi-field sort. Hand-created in production, never declared here.
    FirestoreIndexRequirement(
        'memories_scoring_created',
        'memories',
        'COLLECTION',
        (_desc('scoring'), _desc('created_at'), _desc('__name__')),
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
        'screen_activity_keyframe_device_generation_timestamp',
        'screen_activity',
        'COLLECTION',
        (_asc('clientDeviceId'), _asc('accountGeneration'), _desc('timestamp'), _desc('__name__')),
    ),
    FirestoreIndexRequirement(
        'conversation_keyframe_jobs_device_state',
        'conversation_keyframe_jobs',
        'COLLECTION',
        (_asc('device_id'), _asc('state'), _asc('__name__')),
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
        'action_items_completed_created',
        'action_items',
        'COLLECTION',
        (_asc('completed'), _asc('created_at'), _asc('__name__')),
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
    FirestoreIndexRequirement(
        'frame_requests_device_state_created',
        'frame_requests',
        'COLLECTION',
        (_asc('device_id'), _asc('state'), _asc('created_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'frame_requests_device_generation_state_created',
        'frame_requests',
        'COLLECTION',
        (_asc('device_id'), _asc('account_generation'), _asc('state'), _asc('created_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'frame_requests_generation_expiry',
        'frame_requests',
        'COLLECTION',
        (_asc('account_generation'), _asc('state'), _asc('expires_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'frame_requests_state_expiry',
        'frame_requests',
        'COLLECTION',
        (_asc('state'), _asc('expires_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'frame_requests_dedupe_attempt',
        'frame_requests',
        'COLLECTION',
        (
            _asc('device_id'),
            _asc('account_generation'),
            _asc('dedupe_key'),
            _asc('dedupe_window'),
            _desc('attempt_number'),
            _asc('__name__'),
        ),
    ),
    FirestoreIndexRequirement(
        'frame_requests_dedupe_active_attempt',
        'frame_requests',
        'COLLECTION',
        (_asc('device_id'), _asc('account_generation'), _asc('dedupe_key'), _desc('attempt_number'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'frame_requests_conversation_state',
        'frame_requests',
        'COLLECTION',
        (_asc('conversation_id'), _asc('state'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'frame_requests_cleanup_retry',
        'frame_requests',
        'COLLECTION',
        (_asc('state'), _asc('cleanup_state'), _asc('cleanup_next_attempt_at'), _asc('__name__')),
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

RECENT_REJECTED_MEMORY_FEEDBACK_QUERY = FirestoreQuerySpec(
    identifier='memory_items_recent_rejected_feedback',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('status', 'in', 'statuses'),
        FirestoreQueryFilter('source_state', '==', 'source_state'),
        FirestoreQueryFilter('promotion.user_review', '==', 'user_review'),
        FirestoreQueryFilter('updated_at', '>=', 'updated_at'),
    ),
    index_fields=(
        _asc('status'),
        _asc('source_state'),
        _asc('promotion.user_review'),
        _desc('updated_at'),
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

EXPIRY_URGENT_SHORT_TERM_BY_CAPTURE_QUERY = FirestoreQuerySpec(
    identifier='memory_items_expiry_urgent_short_term_by_capture',
    collection_group='memory_items',
    query_scope='COLLECTION_GROUP',
    filters=(
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', 'in', 'processing_states'),
        FirestoreQueryFilter('captured_at', '<=', 'captured_at'),
    ),
    index_fields=(
        _asc('tier'),
        _asc('status'),
        _asc('processing_state'),
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

# Bounded daily-sweep occupant lookups. The sweep must prove the active
# subject/slot cohort without scanning an arbitrary memory collection page.
#
# Every composite index terminates in __name__, and Firestore reports it back
# that way, so a declaration that omits it can never match the live inventory:
# reconciliation reports the index missing forever and then fails re-creating
# it (ALREADY_EXISTS), which takes the Firestore schema workflow -- and the
# development deploy's readiness gate behind it -- down permanently. These
# prefixes exist so the derived specs append their extra predicates *before*
# that terminator rather than after it.
_DAILY_SWEEP_ACTIVE_FACT_PREFIX = (_asc('status'), _asc('kind'), _asc('subject_scope'))
_DAILY_SWEEP_ACTIVE_FACT_ENTITY_PREFIX = _DAILY_SWEEP_ACTIVE_FACT_PREFIX + (_asc('subject_entity_id'),)

DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_active_fact_subject',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('kind', '==', 'kind'),
        FirestoreQueryFilter('subject_scope', '==', 'subject_scope'),
    ),
    index_fields=_DAILY_SWEEP_ACTIVE_FACT_PREFIX + (_asc('__name__'),),
)

DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_active_fact_slot',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY.filters + (FirestoreQueryFilter('slot', '==', 'slot'),),
    index_fields=_DAILY_SWEEP_ACTIVE_FACT_PREFIX + (_asc('slot'), _asc('__name__')),
)

# Entity-scoped variants are required when a candidate names a subject.  The
# entity predicate must be applied before the proof limit; filtering it after a
# three-row page can miss the authoritative occupant and create a duplicate.
DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_active_fact_entity',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY.filters
    + (FirestoreQueryFilter('subject_entity_id', '==', 'subject_entity_id'),),
    index_fields=_DAILY_SWEEP_ACTIVE_FACT_ENTITY_PREFIX + (_asc('__name__'),),
)

DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_active_fact_entity_slot',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY.filters + (FirestoreQueryFilter('slot', '==', 'slot'),),
    index_fields=_DAILY_SWEEP_ACTIVE_FACT_ENTITY_PREFIX + (_asc('slot'), _asc('__name__')),
)

# Unslotted duplicate checks must match the normalized content identity in
# Firestore before
# applying the bounded proof page.  A broad subject query followed by a
# ``limit(3)`` can otherwise hide the matching occupant behind unrelated facts.
DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_active_fact_subject_content',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY.filters
    + (FirestoreQueryFilter('normalized_content_key', '==', 'normalized_content_key'),),
    index_fields=_DAILY_SWEEP_ACTIVE_FACT_PREFIX + (_asc('normalized_content_key'), _asc('__name__')),
)

DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_active_fact_entity_content',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY.filters
    + (FirestoreQueryFilter('normalized_content_key', '==', 'normalized_content_key'),),
    index_fields=_DAILY_SWEEP_ACTIVE_FACT_ENTITY_PREFIX + (_asc('normalized_content_key'), _asc('__name__')),
)

# Onboarding cold-start discovery is a bounded cursor-relative query over the
# users collection. Keep the server-side document-ID range/order for a stable
# page boundary, but do not emit redundant explicit composites: Firestore's
# automatic marker index serves these equality+document-ID scans.
DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_onboarding_completed_users',
    collection_group='users',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('onboarding.completed', '==', 'completed'),
        FirestoreQueryFilter('__name__', '>', 'after_uid'),
    ),
    index_fields=(_asc('onboarding.completed'), _asc('__name__')),
)

DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_onboarding_device_completed_users',
    collection_group='users',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('onboarding.device_onboarding_completed', '==', 'completed'),
        FirestoreQueryFilter('__name__', '>', 'after_uid'),
    ),
    index_fields=(_asc('onboarding.device_onboarding_completed'), _asc('__name__')),
)

# Onboarding transcript extraction has a separate, single-range query over
# conversation metadata. Keep this contract for the source producer; account
# discovery above is intentionally the users collection and must not reuse this
# source query as its fair inventory.
DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY = FirestoreQuerySpec(
    identifier='daily_sweep_onboarding_conversations',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('external_data.onboarding_session_id', '>', 'onboarding_marker'),),
    index_fields=(_asc('external_data.onboarding_session_id'),),
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

EXPIRY_URGENT_SHORT_TERM_BY_STORED_EXPIRY_QUERY = FirestoreQuerySpec(
    identifier='memory_items_expiry_urgent_short_term_by_stored_expiry',
    collection_group='memory_items',
    query_scope='COLLECTION_GROUP',
    filters=(
        FirestoreQueryFilter('tier', '==', 'tier'),
        FirestoreQueryFilter('status', '==', 'status'),
        FirestoreQueryFilter('processing_state', 'in', 'processing_states'),
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

CONVERSATIONS_ACTIVE_ORDERED_QUERY = FirestoreQuerySpec(
    identifier='conversations_discarded_created',
    collection_group='conversations',
    query_scope='COLLECTION',
    # `get_conversations`/`get_conversations_without_photos` called with their
    # defaults (`include_discarded=False`, no `statuses`/`categories`/`folder_id`/
    # `starred` filter) build exactly this shape — it's the default `GET
    # /v1/conversations` list call, i.e. the app's main screen. Production has
    # this index only because it was created by hand at some point; a fresh
    # self-host deploy 400s with FailedPrecondition the first time anyone loads
    # their conversation list.
    filters=(FirestoreQueryFilter('discarded', '==', 'discarded'),),
    index_fields=(_asc('discarded'), _desc('created_at'), _desc('__name__')),
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

ENTITY_TIMELINE_CONVERSATIONS_QUERY = FirestoreQuerySpec(
    identifier='conversations_entity_timeline_completed',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('discarded', '==', 'discarded'),
        FirestoreQueryFilter('status', '==', 'status'),
    ),
    index_fields=(
        _asc('discarded'),
        _asc('status'),
        _desc('created_at'),
        _desc('__name__'),
    ),
)

ENTITY_TIMELINE_MEETINGS_QUERY = FirestoreQuerySpec(
    identifier='meetings_entity_timeline',
    collection_group='meetings',
    query_scope='COLLECTION',
    filters=(),
    index_fields=(
        _desc('start_time'),
        _desc('__name__'),
    ),
)

ENTITY_TIMELINE_SCREEN_ACTIVITY_QUERY = FirestoreQuerySpec(
    identifier='screen_activity_entity_timeline',
    collection_group='screen_activity',
    query_scope='COLLECTION',
    filters=(),
    index_fields=(
        _desc('timestamp'),
        _desc('__name__'),
    ),
)

ACTION_ITEMS_COMPLETION_ID_SCAN_QUERY = FirestoreQuerySpec(
    identifier='action_items_completion_id_scan',
    collection_group='action_items',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('completed', '==', 'completed'),),
    index_fields=(_asc('completed'), _asc('__name__')),
)

ACTION_ITEMS_CANONICAL_COMPLETION_COUNT_QUERY = FirestoreQuerySpec(
    identifier='action_items_canonical_completion_count',
    collection_group='action_items',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('completed', 'in', 'canonical_values'),),
    # Firestore's automatic single-field index serves this aggregation; keeping
    # the query in the registry makes the production shape auditable without
    # adding a redundant composite manifest entry.
    index_fields=(_asc('completed'),),
)

ACTION_ITEMS_COMPLETED_DUE_RANGE_QUERY = FirestoreQuerySpec(
    identifier='action_items_completed_due_range',
    collection_group='action_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('due_at', '>=', 'start'),
        FirestoreQueryFilter('due_at', '<', 'end'),
        FirestoreQueryFilter('completed', '==', 'completed'),
    ),
    index_fields=(_asc('completed'), _asc('due_at'), _asc('__name__')),
)

ACTION_ITEMS_CREATED_RANGE_QUERY = FirestoreQuerySpec(
    identifier='action_items_created_range',
    collection_group='action_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('created_at', '>=', 'start'),
        FirestoreQueryFilter('created_at', '<', 'end'),
    ),
    index_fields=(_asc('created_at'), _asc('__name__')),
)

MEMORIES_CREATED_RANGE_QUERY = FirestoreQuerySpec(
    identifier='memories_created_range',
    collection_group='memories',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('created_at', '>=', 'start'),
        FirestoreQueryFilter('created_at', '<=', 'end'),
    ),
    index_fields=(_asc('created_at'), _asc('__name__')),
)

CANONICAL_MEMORIES_CAPTURED_RANGE_QUERY = FirestoreQuerySpec(
    identifier='canonical_memories_captured_range',
    collection_group='memory_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('captured_at', '>=', 'start'),
        FirestoreQueryFilter('captured_at', '<=', 'end'),
    ),
    index_fields=(_asc('captured_at'), _asc('__name__')),
)

ACTION_ITEMS_COMPLETED_CREATED_RANGE_QUERY = FirestoreQuerySpec(
    identifier='action_items_completed_created_range',
    collection_group='action_items',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('created_at', '>=', 'start'),
        FirestoreQueryFilter('created_at', '<', 'end'),
        FirestoreQueryFilter('completed', '==', 'completed'),
    ),
    index_fields=(_asc('completed'), _asc('created_at'), _asc('__name__')),
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

CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY = FirestoreQuerySpec(
    identifier='chat_first_transient_dead_letter_repair',
    collection_group='chat_first_dead_letters',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('account_generation', '==', 'account_generation'),
        FirestoreQueryFilter('requeue_count', '==', 'requeue_count'),
        FirestoreQueryFilter('dead_letter_reason', 'in', 'dead_letter_reasons'),
    ),
    index_fields=(
        _asc('account_generation'),
        _asc('requeue_count'),
        _asc('dead_letter_reason'),
        _asc('last_fetched_at'),
        _asc('__name__'),
    ),
)

CURRENT_CHAT_SESSION_QUERY = FirestoreQuerySpec(
    identifier='chat_sessions_current_by_app',
    collection_group='chat_sessions',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('plugin_id', '==', 'app_id'),),
    # No `created_at` ordering: Firestore omits documents that lack the ordered
    # field, and a chat session with no timestamp is representable, so ordering
    # in the query would hide a user's existing sessions. The caller reads this
    # filter and picks the newest itself.
    index_fields=(_asc('plugin_id'), _asc('__name__')),
)

CURRENT_CHAT_SESSION_ORDERED_QUERY = FirestoreQuerySpec(
    identifier='chat_sessions_current_by_app_created_at',
    collection_group='chat_sessions',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('plugin_id', '==', 'app_id'),),
    index_fields=(_asc('plugin_id'), _desc('created_at'), _desc('__name__')),
)

# get_app_messages and get_messages' app-scoped branch (no chat_session_id) both
# filter messages by plugin_id and order by created_at descending. Neither built
# this through the registry, so no composite index was ever declared for it and
# a self-host without prod's historically hand-created index 400s with
# FailedPrecondition on GET /v1/messages (chat.py:get_messages).
MESSAGES_BY_APP_ORDERED_QUERY = FirestoreQuerySpec(
    identifier='messages_by_app_created_at',
    collection_group='messages',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('plugin_id', '==', 'app_id'),),
    index_fields=(_asc('plugin_id'), _desc('created_at'), _desc('__name__')),
)

# The daily feedback report scans one UTC day of negative ratings across every
# surface: value == -1 ordered by created_at. Without this composite the job
# 400s with FailedPrecondition on its very first run, which on a nightly cron
# is a failure nobody sees until the report is already missing.
NEGATIVE_FEEDBACK_EVENTS_QUERY = FirestoreQuerySpec(
    identifier='feedback_events_negative_by_created_at',
    collection_group='feedback_events',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('value', '==', 'value'),
        FirestoreQueryFilter('created_at', '>=', 'start_at'),
        FirestoreQueryFilter('created_at', '<', 'end_at'),
    ),
    index_fields=(_asc('value'), _asc('created_at'), _asc('__name__')),
)

MEETING_RECEIPTS_DUE_QUERY = FirestoreQuerySpec(
    identifier='conversation_finalization_jobs_meeting_receipts_due',
    collection_group='conversation_finalization_jobs',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('meeting_treatment_eligible', '==', 'meeting_treatment_eligible'),
        FirestoreQueryFilter('meeting_receipt_intent_id', '==', 'meeting_receipt_intent_id'),
        FirestoreQueryFilter('meeting_receipt_reconcile_after_at', '<=', 'meeting_receipt_reconcile_after_at'),
    ),
    index_fields=(
        _asc('meeting_treatment_eligible'),
        _asc('meeting_receipt_intent_id'),
        _asc('meeting_receipt_reconcile_after_at'),
        _asc('__name__'),
    ),
)

HOURLY_USAGE_PLAN_ATTRIBUTION_QUERY = FirestoreQuerySpec(
    identifier='hourly_usage_plan_attribution_month',
    collection_group='hourly_usage',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('year', '==', 'year'),
        FirestoreQueryFilter('month', '==', 'month'),
    ),
    index_fields=(
        _asc('year'),
        _asc('month'),
        _asc('__name__'),
    ),
)

FINALIZATION_OLDEST_NONTERMINAL_QUERY = FirestoreQuerySpec(
    identifier='conversation_finalization_jobs_oldest_nonterminal',
    collection_group='conversation_finalization_jobs',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('status', '==', 'status'),),
    index_fields=(_asc('status'), _asc('created_at'), _asc('__name__')),
)

FIRST_OPEN_FOLDER_CONVERSATION_COUNT_QUERY = FirestoreQuerySpec(
    identifier='conversations_first_open_folder_active_count',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('folder_id', '==', 'folder_id'),
        FirestoreQueryFilter('discarded', '==', 'discarded'),
    ),
    index_fields=(_asc('folder_id'), _asc('discarded'), _asc('__name__')),
)

CONVERSATION_KEYFRAME_JOBS_DEVICE_STATE_QUERY = FirestoreQuerySpec(
    identifier='conversation_keyframe_jobs_device_state',
    collection_group='conversation_keyframe_jobs',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('device_id', '==', 'device_id'),
        FirestoreQueryFilter('state', '==', 'state'),
    ),
    index_fields=(_asc('device_id'), _asc('state'), _asc('__name__')),
)

SCREEN_ACTIVITY_KEYFRAME_QUERY = FirestoreQuerySpec(
    identifier='screen_activity_keyframe_device_generation_timestamp',
    collection_group='screen_activity',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('clientDeviceId', '==', 'device_id'),
        FirestoreQueryFilter('accountGeneration', '==', 'account_generation'),
        FirestoreQueryFilter('timestamp', '>=', 'started_at'),
        FirestoreQueryFilter('timestamp', '<=', 'finished_at'),
    ),
    index_fields=(_asc('clientDeviceId'), _asc('accountGeneration'), _desc('timestamp'), _desc('__name__')),
)

FRAME_VISION_OUTPUT_EXPIRY_QUERY = FirestoreQuerySpec(
    identifier='frame_vision_receipts_output_expiry',
    collection_group='frame_vision_receipts',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('output_expires_at', '<=', 'now'),),
    # Served by Firestore's automatic same-direction single-field index.
    index_fields=(_asc('output_expires_at'), _asc('__name__')),
)

FRAME_REQUEST_METADATA_EXPIRY_QUERY = FirestoreQuerySpec(
    identifier='frame_requests_terminal_metadata_expiry',
    collection_group='frame_requests',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('state', 'in', 'terminal_states'),
        FirestoreQueryFilter('cleanup_state', 'in', 'cleanup_states'),
        FirestoreQueryFilter('expires_at', '<=', 'now'),
    ),
    index_fields=(
        _asc('state'),
        _asc('cleanup_state'),
        _asc('expires_at'),
        _asc('__name__'),
    ),
)

# get_messages' session-scoped branch filters by chat_session_id instead of
# plugin_id, same created_at descending order. Same missing-declaration story
# as the app-scoped shape, and it 500s independently because a chat session's
# first page of messages hits this branch, not the app-scoped one.
MESSAGES_BY_SESSION_ORDERED_QUERY = FirestoreQuerySpec(
    identifier='messages_by_session_created_at',
    collection_group='messages',
    query_scope='COLLECTION',
    filters=(FirestoreQueryFilter('chat_session_id', '==', 'chat_session_id'),),
    index_fields=(_asc('chat_session_id'), _desc('created_at'), _desc('__name__')),
)

# EXP-001's daily cohort selection: every macOS account whose set-once
# `signup_platform_at` lands in one 24h window 72-96h back. Equality plus a
# range on a different field is a compound serving query, so automatic
# single-field indexes do not cover it however the directions line up.
DAY3_REENGAGEMENT_SIGNUP_COHORT_QUERY = FirestoreQuerySpec(
    identifier='users_signup_platform_signup_at_range',
    collection_group='users',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('signup_platform', '==', 'signup_platform'),
        FirestoreQueryFilter('signup_platform_at', '>=', 'start'),
        FirestoreQueryFilter('signup_platform_at', '<', 'end'),
    ),
    index_fields=(_asc('signup_platform'), _asc('signup_platform_at'), _asc('__name__')),
)

# EXP-001's day-0 output count: real conversations created inside the 24h after
# signup.
#
# `discarded == False` and `status == 'completed'` are not incidental hygiene,
# they are the definition of the signal. A raw `created_at` scan counts the
# `in_progress` stub the desktop listen socket writes on every session start
# and reconnect, so a Mac that is merely still running — launch-at-login, wakes
# from sleep, reconnects — manufactures "conversations" indistinguishable from
# real output. That is the same contamination that made `last_active_at`
# unusable for this experiment, and re-importing it through the value signal
# would hollow out the target cohort exactly as badly. It also matches the
# codebase's own default reader, `get_conversations`, which excludes discarded
# rows unless asked otherwise.
DAY3_REENGAGEMENT_DAY_ZERO_CONVERSATIONS_QUERY = FirestoreQuerySpec(
    identifier='conversations_created_range_day_zero',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('discarded', '==', 'discarded'),
        FirestoreQueryFilter('status', 'in', 'statuses'),
        FirestoreQueryFilter('created_at', '>=', 'start'),
        FirestoreQueryFilter('created_at', '<', 'end'),
    ),
    index_fields=(_asc('discarded'), _asc('status'), _asc('created_at'), _asc('__name__')),
)

# The companion "did they come back after day 0" probe: same definition of a
# real conversation, one open-ended lower bound, `limit(1)`. Served by the same
# composite as the day-0 count (equalities then range), declared separately so
# the coverage checker can match each call site to a spec.
DAY3_REENGAGEMENT_RETURNED_CONVERSATIONS_QUERY = FirestoreQuerySpec(
    identifier='conversations_created_after_day_zero',
    collection_group='conversations',
    query_scope='COLLECTION',
    filters=(
        FirestoreQueryFilter('discarded', '==', 'discarded'),
        FirestoreQueryFilter('status', 'in', 'statuses'),
        FirestoreQueryFilter('created_at', '>=', 'start'),
    ),
    index_fields=(_asc('discarded'), _asc('status'), _asc('created_at'), _asc('__name__')),
)


CONVERSATION_PHOTOS_NAME_RANGE_QUERY = FirestoreQuerySpec(
    identifier='conversation_photos_name_range_export',
    collection_group='photos',
    query_scope='COLLECTION_GROUP',
    filters=(
        FirestoreQueryFilter('__name__', '>=', 'start_key'),
        FirestoreQueryFilter('__name__', '<=', 'end_key'),
    ),
    index_fields=(_asc('__name__'),),
)

QUERY_SPECS = (
    ACTION_ITEMS_CANONICAL_COMPLETION_COUNT_QUERY,
    CONVERSATION_PHOTOS_NAME_RANGE_QUERY,
    ACTION_ITEMS_COMPLETION_ID_SCAN_QUERY,
    ACTION_ITEMS_COMPLETED_DUE_RANGE_QUERY,
    ACTION_ITEMS_CREATED_RANGE_QUERY,
    ACTION_ITEMS_COMPLETED_CREATED_RANGE_QUERY,
    MEMORIES_CREATED_RANGE_QUERY,
    CANONICAL_MEMORIES_CAPTURED_RANGE_QUERY,
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
    RECENT_REJECTED_MEMORY_FEEDBACK_QUERY,
    POLICY_EXPIRED_SHORT_TERM_QUERY,
    EXPIRY_URGENT_SHORT_TERM_BY_CAPTURE_QUERY,
    CANONICAL_GRAPH_READ_QUERY,
    CANONICAL_MEMORY_ATLAS_READ_QUERY,
    UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY,
    DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY,
    DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY,
    DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY,
    UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY,
    CONVERSATION_SOURCE_MEMORY_QUERY,
    SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
    SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
    EXPIRED_SHORT_TERM_LIFECYCLE_QUERY,
    EXPIRY_URGENT_SHORT_TERM_BY_STORED_EXPIRY_QUERY,
    ACTIVE_ATTENTION_OVERRIDE_QUERY,
    LEGACY_CONVERSATION_RECOVERY_QUERY,
    STALE_IN_PROGRESS_CONVERSATIONS_QUERY,
    ENTITY_TIMELINE_CONVERSATIONS_QUERY,
    ENTITY_TIMELINE_MEETINGS_QUERY,
    ENTITY_TIMELINE_SCREEN_ACTIVITY_QUERY,
    CHAT_FIRST_DEFERRALS_DUE_QUERY,
    CHAT_FIRST_DEFERRALS_SUBJECT_QUERY,
    CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY,
    CURRENT_CHAT_SESSION_QUERY,
    CURRENT_CHAT_SESSION_ORDERED_QUERY,
    MEETING_RECEIPTS_DUE_QUERY,
    NEGATIVE_FEEDBACK_EVENTS_QUERY,
    HOURLY_USAGE_PLAN_ATTRIBUTION_QUERY,
    FIRST_OPEN_FOLDER_CONVERSATION_COUNT_QUERY,
    MESSAGES_BY_APP_ORDERED_QUERY,
    MESSAGES_BY_SESSION_ORDERED_QUERY,
    CONVERSATIONS_ACTIVE_ORDERED_QUERY,
    *MCP_CONVERSATION_CARD_QUERY_SPECS.values(),
    FINALIZATION_OLDEST_NONTERMINAL_QUERY,
    CONVERSATION_KEYFRAME_JOBS_DEVICE_STATE_QUERY,
    SCREEN_ACTIVITY_KEYFRAME_QUERY,
    FRAME_VISION_OUTPUT_EXPIRY_QUERY,
    FRAME_REQUEST_METADATA_EXPIRY_QUERY,
    DAY3_REENGAGEMENT_SIGNUP_COHORT_QUERY,
    DAY3_REENGAGEMENT_DAY_ZERO_CONVERSATIONS_QUERY,
    DAY3_REENGAGEMENT_RETURNED_CONVERSATIONS_QUERY,
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
    # Equality plus a document-ID range is served by Firestore's automatic
    # single-field marker index for these two onboarding scans. Keep the
    # server-side cursor contract above, but do not provision redundant
    # collection composites for it.
    redundant_onboarding_indexes = frozenset(
        {
            DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY.identifier,
            DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY.identifier,
        }
    )
    requirements: list[FirestoreIndexRequirement] = []
    for spec in QUERY_SPECS:
        if spec.identifier in redundant_onboarding_indexes:
            continue
        # A document-id range paired with a field equality is a compound
        # serving query even when both index fields have the same direction;
        # automatic single-field indexes do not provide this cursor contract
        # consistently across Firestore emulator/server versions.
        document_id_range = any(
            query_filter.field_path == '__name__' and query_filter.operator not in ('==', 'in')
            for query_filter in spec.filters
        )
        document_id_only_range = (
            document_id_range
            and bool(spec.filters)
            and all(query_filter.field_path == '__name__' for query_filter in spec.filters)
            and len(spec.index_fields) == 1
            and spec.index_fields[0].field_path == '__name__'
            and spec.index_fields[0].order in {'ASCENDING', 'DESCENDING'}
        )
        if document_id_only_range:
            # Firestore serves collection-group ranges on the document key from
            # its built-in key index. A one-field __name__ composite is not a
            # valid Firestore composite definition (composites require at least
            # two fields); keep the query registered for coverage without
            # turning it into an impossible provisioning requirement.
            continue
        if not _index_fields_need_composite_manifest(spec.index_fields) and not document_id_range:
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
# explicitly exempted. For text fields that no query ever filters or orders on, that index is pure
# storage cost: measured on prod `screen_activity` (964,964 documents, mean 1,052 B), the four
# originally declared fields carried roughly 2.75x the document bytes in index entries, matching
# the earlier "about three times" estimate.
#
# Only the two text fields are exempted, and the split is deliberate. `ocrText` (mean 899 B, capped
# at 1,000 characters on write) is ~71% of that index cost and `windowTitle` ~10%; both are only
# ever read back and rendered, since semantic search runs on Pinecone vectors rather than Firestore.
# `deviceName` (11 B) and `clientDeviceId` (14 B) are together ~19% of an already small number --
# under ten cents a month at current volume -- and are the one plausible future filter here:
# utils/memory/device_scope_filter.py already scopes by device in Python, and pushing that down to
# a Firestore filter would fail with FAILED_PRECONDITION against a disabled index. Re-enabling has
# no scripted path (the reconcile workflow is disable-only) and forces a full collection-group
# backfill, so they stay indexed.
#
# Exempting a field only removes single-field indexes — composite indexes declared above are
# unaffected, so a field named in a composite index can still appear here.
FIELD_INDEXING_EXEMPTIONS: tuple[tuple[str, str], ...] = (
    ('screen_activity', 'ocrText'),
    ('screen_activity', 'windowTitle'),
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
