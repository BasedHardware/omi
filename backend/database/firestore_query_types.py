"""Value types shared by the Firestore query and index registry."""

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
class FieldIndexRequirement:
    """One additive collection-group single-field index requirement.

    ``collection_group_modes`` are the COLLECTION_GROUP modes the field must
    serve. The generated override also carries the COLLECTION ASCENDING,
    DESCENDING, and CONTAINS defaults so a patch never narrows inherited
    single-field indexing below the automatic defaults.
    """

    identifier: str
    collection_group: str
    field_path: str
    collection_group_modes: tuple[str, ...]

    def to_manifest(self) -> dict[str, Any]:
        indexes: list[dict[str, str]] = [
            {'queryScope': 'COLLECTION', 'order': 'ASCENDING'},
            {'queryScope': 'COLLECTION', 'order': 'DESCENDING'},
            {'queryScope': 'COLLECTION', 'arrayConfig': 'CONTAINS'},
        ]
        for mode in self.collection_group_modes:
            if mode == 'CONTAINS':
                indexes.append({'queryScope': 'COLLECTION_GROUP', 'arrayConfig': 'CONTAINS'})
            else:
                indexes.append({'queryScope': 'COLLECTION_GROUP', 'order': mode})
        return {
            'collectionGroup': self.collection_group,
            'fieldPath': self.field_path,
            'ttl': False,
            'indexes': indexes,
        }


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
