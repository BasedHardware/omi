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
        'memory_outbox_status_available',
        'memory_outbox',
        'COLLECTION',
        (_asc('status'), _asc('available_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'memory_outbox_event_status_lease',
        'memory_outbox',
        'COLLECTION',
        (_asc('event_type'), _asc('status'), _asc('lease_expires_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'screen_activity_app_timestamp',
        'screen_activity',
        'COLLECTION',
        (_asc('appName'), _asc('timestamp'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'candidates_generation_created',
        'candidates',
        'COLLECTION',
        (_asc('account_generation'), _desc('created_at'), _desc('__name__')),
    ),
    FirestoreIndexRequirement(
        'candidates_status_generation_created',
        'candidates',
        'COLLECTION',
        (_asc('status'), _asc('account_generation'), _desc('created_at'), _desc('__name__')),
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
    index_fields=(_asc('account_generation'), _asc('expires_at')),
)

QUERY_SPECS = (ACTIVE_ATTENTION_OVERRIDE_QUERY,)
INDEX_REQUIREMENTS = (*INDEX_ONLY_REQUIREMENTS, *(spec.index_requirement for spec in QUERY_SPECS))


def firebase_index_manifest() -> dict[str, list[dict[str, Any]]]:
    """Return Firebase's canonical composite-index manifest deterministically."""

    signatures: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    indexes: list[dict[str, Any]] = []
    for requirement in INDEX_REQUIREMENTS:
        if requirement.signature in signatures:
            raise ValueError(f'duplicate Firestore index requirement: {requirement.identifier}')
        signatures.add(requirement.signature)
        indexes.append(requirement.to_manifest())
    return {'indexes': indexes, 'fieldOverrides': []}
