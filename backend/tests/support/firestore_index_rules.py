"""Conservative Standard-edition index requirements for recorded Firestore queries."""

from dataclasses import dataclass, replace
from typing import Any, Mapping

from tests.support.firestore_shape_recorder import QueryShape

ASC = 'ASCENDING'
DESC = 'DESCENDING'
ARRAY = 'CONTAINS'
RANGE_OPERATORS = frozenset({'<', '<=', '>', '>=', '!=', 'not_in'})
EQUALITY_OPERATORS = frozenset({'==', 'in'})
ARRAY_OPERATORS = frozenset({'array_contains', 'array_contains_any'})
MERGING_REASON = 'equality/array index merging may serve this query without the full candidate index'


@dataclass(frozen=True)
class IndexSpec:
    collection_group: str
    scope: str
    fields: tuple[tuple[str, str], ...]
    equality_fields: tuple[str, ...] = ()
    uncertain: bool = False
    reason: str = ''
    composite: bool = True
    validity_uncertain: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'collectionGroup': self.collection_group,
            'queryScope': self.scope,
            'fields': [
                {'fieldPath': field, 'arrayConfig' if mode == ARRAY else 'order': mode} for field, mode in self.fields
            ],
            'equality_fields': list(self.equality_fields),
            'uncertain': self.uncertain,
            'reason': self.reason,
            'composite': self.composite,
        }


def _has_or(tree: Any) -> bool:
    return isinstance(tree, dict) and (
        tree.get('op') == 'OR' or any(_has_or(child) for child in tree.get('filters', ()))
    )


def candidate_index(shape: QueryShape) -> IndexSpec:
    """Build the full candidate, including single-field indexes needed by group queries.

    References: Firebase index-overview (modes, merging, group scope, aggregation
    fields), REST StructuredQuery.orderBy (lexicographic implicit ordering), and
    firebase-js-sdk TargetIndexMatcher (unordered equality segments). Matching is
    deliberately full-index-only: ``is_served`` separately models the
    evidence-backed merging rule.
    """
    equalities: set[str] = set()
    arrays: set[str] = set()
    ranges: set[str] = set()
    reasons = []
    validity_reasons = []
    for predicate in shape.filters:
        operator = predicate.operator.replace('-', '_')
        if operator in EQUALITY_OPERATORS:
            equalities.add(predicate.field)
        elif operator in ARRAY_OPERATORS:
            arrays.add(predicate.field)
        elif operator in RANGE_OPERATORS:
            ranges.add(predicate.field)
        else:
            equalities.add(predicate.field)
            reasons.append(f'unsupported filter operator: {operator}')
            validity_reasons.append(f'unsupported filter operator: {operator}')
    equalities.discard('__name__')
    explicitly_ordered = {field for field, _ in shape.orders}
    equalities.difference_update(
        predicate.field
        for predicate in shape.filters
        if predicate.operator == 'in' and predicate.field in explicitly_ordered
    )
    if _has_or(shape.filter_tree):
        reasons.append('OR branches require per-disjunction oracle validation; candidate is the union of fields')
    if len(arrays) > 1 or arrays & (equalities | ranges):
        reason = 'multiple array fields or mixed array/scalar predicates require query-validity validation'
        reasons.append(reason)
        validity_reasons.append(reason)
    ordered = [field for field, _ in shape.orders]
    if len(ordered) != len(set(ordered)) or ('__name__' in ordered and ordered[-1] != '__name__'):
        reason = 'duplicate order fields or a non-terminal explicit __name__ order require query-validity validation'
        reasons.append(reason)
        validity_reasons.append(reason)
    orders = [
        (field, DESC if mode == ASC else ASC) if shape.limit_to_last else (field, mode) for field, mode in shape.orders
    ]
    direction = orders[-1][1] if orders else ASC
    name_direction = next((mode for field, mode in orders if field == '__name__'), direction)
    present = {field for field, _ in orders}
    orders.extend((field, direction) for field in sorted(ranges - present - {'__name__'}))
    if '__name__' not in present:
        orders.append(('__name__', direction))
    ordered_fields = {field for field, _ in orders}
    aggregate_fields = {aggregation.field for aggregation in shape.aggregations if aggregation.field is not None}
    if aggregate_fields - (equalities | arrays | ranges | ordered_fields):
        reasons.append('aggregation-only field ordering needs real-Firestore oracle validation')
    if not ranges and len(equalities | arrays) > 1:
        reasons.append(MERGING_REASON)
    fields = [(field, ARRAY if field in arrays else ASC) for field in sorted(equalities | arrays)]
    used = set(equalities | arrays)
    for field, mode in orders:
        if field != '__name__' and field not in used:
            fields.append((field, mode))
            used.add(field)
    for field in sorted(aggregate_fields - used - {'__name__'}):
        fields.append((field, ASC))
        used.add(field)
    fields.append(('__name__', name_direction))
    if not used and name_direction == DESC:
        reasons.append('document-name-only descending service needs real-Firestore oracle validation')
    return IndexSpec(
        collection_group=shape.collection_group,
        scope=shape.scope,
        fields=tuple(fields),
        equality_fields=tuple(sorted(equalities | arrays)),
        uncertain=bool(reasons),
        reason='; '.join(dict.fromkeys(reasons)),
        composite=len(used) > 1,
        validity_uncertain=bool(validity_reasons),
    )


def _automatic_modes(spec: IndexSpec) -> set[str]:
    scalar = [(field, mode) for field, mode in spec.fields if field != '__name__']
    if not scalar:
        return {ASC, DESC}
    field, mode = scalar[0]
    if mode == ARRAY:
        return {ARRAY} if spec.fields[-1][1] == ASC else set()
    if field in spec.equality_fields:
        # Equality segments are unordered: either scalar direction serves them
        # (firebase-js-sdk TargetIndexMatcher treats them direction-agnostically;
        # the composite matcher below accepts ASC or DESC for the same reason).
        return {ASC, DESC}
    return {mode} if mode == spec.fields[-1][1] else set()


def required_index(shape: QueryShape) -> IndexSpec | None:
    spec = candidate_index(shape)
    if spec.uncertain or spec.composite:
        return spec
    if shape.scope == 'COLLECTION' and _automatic_modes(spec):
        return None
    if spec.fields == (('__name__', ASC),) or spec.fields == (('__name__', DESC),):
        return None
    return spec


def _normalized_fields(entry: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    fields = tuple((field['fieldPath'], field.get('order') or field.get('arrayConfig')) for field in entry['fields'])
    if fields and not any(field == '__name__' for field, _ in fields):
        direction = next((mode for _, mode in reversed(fields) if mode != ARRAY), ASC)
        fields += (('__name__', direction),)
    return fields


def matches_index(spec: IndexSpec, entry: Mapping[str, Any]) -> bool:
    """Require an identical suffix and the same equality-prefix set, never extra fields."""
    if entry.get('collectionGroup') != spec.collection_group or entry.get('queryScope', 'COLLECTION') != spec.scope:
        return False
    declared = _normalized_fields(entry)
    if len(declared) != len(spec.fields) or len({field for field, _ in declared}) != len(declared):
        return False
    prefix_size = len(spec.equality_fields)
    required_prefix = dict(spec.fields[:prefix_size])
    actual_prefix = dict(declared[:prefix_size])
    if actual_prefix.keys() != required_prefix.keys():
        return False
    for field, mode in required_prefix.items():
        if mode == ARRAY:
            if actual_prefix[field] != ARRAY:
                return False
        elif actual_prefix[field] not in {ASC, DESC}:
            return False
    return declared[prefix_size:] == spec.fields[prefix_size:]


def _single_field_modes(collection: str, field: str, scope: str, manifest: Mapping[str, Any]) -> set[str]:
    modes = {ASC, DESC, ARRAY} if scope == 'COLLECTION' else set()
    overrides = [
        entry
        for entry in manifest.get('fieldOverrides', ())
        if entry['collectionGroup'] == collection
        and (entry['fieldPath'] == '*' or entry['fieldPath'] == field or field.startswith(entry['fieldPath'] + '.'))
        and 'indexes' in entry
    ]
    if overrides:
        override = max(overrides, key=lambda entry: len(entry['fieldPath']) if entry['fieldPath'] != '*' else 0)
        modes = {
            index.get('order') or index.get('arrayConfig')
            for index in override['indexes']
            if index.get('queryScope', 'COLLECTION') == scope
        }
    return modes


def _merging_prefixes(
    spec: IndexSpec, manifest: Mapping[str, Any]
) -> tuple[dict[str, str], tuple[tuple[str, str], ...], list[set[str]]]:
    """Collect eligible equality-prefix field sets for index merging.

    A composite participates when it shares the candidate's collection and
    scope, carries no duplicate or extra prefix fields, ends with the exact
    common suffix (``__name__`` direction included), and its prefix assigns
    every member an equality field: ARRAY modes must match an array equality,
    scalar fields may be ASC or DESC. A ``__name__``-ASC-only suffix can also
    be served by automatic single-field indexes, so each equality field whose
    enabled single-field modes cover its equality mode contributes a
    singleton prefix.
    """
    eq = dict(spec.fields[: len(spec.equality_fields)])
    suffix = spec.fields[len(eq) :]
    prefixes = []
    for entry in manifest.get('indexes', ()):
        if entry.get('collectionGroup') != spec.collection_group or entry.get('queryScope', 'COLLECTION') != spec.scope:
            continue
        fields = _normalized_fields(entry)
        if len(fields) <= len(suffix) or len(dict(fields)) != len(fields) or fields[-len(suffix) :] != suffix:
            continue
        prefix = fields[: len(fields) - len(suffix)]
        if all(
            field in eq and (mode == ARRAY if eq[field] == ARRAY else mode in {ASC, DESC}) for field, mode in prefix
        ):
            prefixes.append({field for field, _ in prefix})
    if suffix == (('__name__', ASC),):
        for field, mode in eq.items():
            if _single_field_modes(spec.collection_group, field, spec.scope, manifest) & (
                {ARRAY} if mode == ARRAY else {ASC, DESC}
            ):
                prefixes.append({field})
    return eq, suffix, prefixes


def is_merged(shape: QueryShape, manifest: Mapping[str, Any]) -> bool:
    """Prove service by merging eligible equality prefixes over a shared suffix.

    Merging is only inferred for validity-certain AND queries without
    ``!=``/``not_in``, at most one range field, count-only aggregations, and
    well-formed ``in`` operands; array equalities require the automatic
    ``('__name__', ASCENDING)``-only suffix. With a longer suffix and exactly
    one multi-value ``in`` field, that field must anchor a single prefix whose
    union with all prefixes free of it still covers every equality; zero or
    more than one multi-value ``in`` fields use the plain union of all
    eligible prefixes.
    """
    spec = candidate_index(shape)
    eq, suffix, prefixes = _merging_prefixes(spec, manifest)
    if not eq or spec.validity_uncertain or _has_or(shape.filter_tree):
        return False
    if any(predicate.operator in {'!=', 'not_in'} for predicate in shape.filters):
        return False
    ranges = {predicate.field for predicate in shape.filters if predicate.operator in {'<', '<=', '>', '>='}}
    if len(ranges) > 1 or any(aggregation.kind != 'count' for aggregation in shape.aggregations):
        return False
    if any(mode == ARRAY for mode in eq.values()) and suffix != (('__name__', ASC),):
        return False
    in_filters = [predicate for predicate in shape.filters if predicate.operator == 'in']
    if any(not isinstance(predicate.value, (list, tuple)) or not predicate.value for predicate in in_filters):
        return False
    multi_in = {predicate.field for predicate in in_filters if len(predicate.value) > 1}
    if len(suffix) > 1 and len(multi_in) == 1:
        plain = set().union(*(prefix for prefix in prefixes if not prefix & multi_in))
        return any(prefix | plain >= eq.keys() for prefix in prefixes if prefix & multi_in)
    return set().union(*prefixes) >= eq.keys()


def resolved_candidate_index(shape: QueryShape, manifest: Mapping[str, Any]) -> IndexSpec:
    """Candidate spec with the generic merging caveat dropped once merging is proven."""
    spec = candidate_index(shape)
    if spec.scope != 'COLLECTION' or not is_merged(shape, manifest):
        return spec
    remaining = [reason for reason in spec.reason.split('; ') if reason and reason != MERGING_REASON]
    return replace(spec, uncertain=bool(remaining), reason='; '.join(remaining))


def is_served(shape: QueryShape, manifest: Mapping[str, Any]) -> bool:
    """Prove service by one complete declared index, index merging, or an enabled single-field index.

    This is only the serving proof: declaration metadata (``required_index``,
    ``candidate_index``) is unaffected, and unresolved uncertainty is carried
    separately by ``resolved_candidate_index``.
    OR service is not asserted without the oracle.
    A validity-uncertain shape (possibly-invalid query) is never served: a
    declared index cannot establish that the query itself is valid, so it must
    stay in the uncertainty ledger until the real-Firestore oracle exists.
    """
    spec = candidate_index(shape)
    if _has_or(shape.filter_tree):
        return False
    if spec.validity_uncertain:
        return False
    if any(matches_index(spec, entry) for entry in manifest.get('indexes', ())):
        return True
    if is_merged(shape, manifest):
        return True
    if spec.composite:
        return False
    scalar = [(field, mode) for field, mode in spec.fields if field != '__name__']
    if not scalar:
        return spec.fields[-1][1] == ASC
    field, _ = scalar[0]
    return bool(_automatic_modes(spec) & _single_field_modes(shape.collection_group, field, shape.scope, manifest))
