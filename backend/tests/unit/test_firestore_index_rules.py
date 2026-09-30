from dataclasses import replace
from itertools import permutations

import pytest

from tests.support.firestore_index_rules import ASC, DESC, ARRAY, candidate_index, is_served, required_index
from tests.support.firestore_shape_recorder import Aggregation, QueryFilter, QueryShape


def shape(filters=(), orders=(), aggregation=None, scope='COLLECTION', tree=None):
    return QueryShape(
        collection_group='conversations',
        scope=scope,
        filters=tuple(QueryFilter(field, op, 1) for field, op in filters),
        orders=tuple(orders),
        aggregations=(
            (Aggregation(aggregation, 'created_at' if aggregation in {'sum', 'avg'} else None),) if aggregation else ()
        ),
        filter_tree=tree,
    )


def entry(fields, scope='COLLECTION'):
    return {
        'collectionGroup': 'conversations',
        'queryScope': scope,
        'fields': [{'fieldPath': field, 'arrayConfig' if mode == ARRAY else 'order': mode} for field, mode in fields],
    }


@pytest.mark.parametrize(
    'filters,orders,aggregation,expected',
    [
        (
            [('discarded', '=='), ('created_at', '>='), ('created_at', '<=')],
            [],
            'count',
            [('discarded', ASC), ('created_at', ASC), ('__name__', ASC)],
        ),
        (
            [('starred', '=='), ('status', 'in'), ('discarded', '=='), ('created_at', '>='), ('created_at', '<=')],
            [],
            'count',
            [('discarded', ASC), ('starred', ASC), ('status', ASC), ('created_at', ASC), ('__name__', ASC)],
        ),
        (
            [('source', '=='), ('status', 'in'), ('created_at', '>='), ('created_at', '<=')],
            [],
            'count',
            [('source', ASC), ('status', ASC), ('created_at', ASC), ('__name__', ASC)],
        ),
        (
            [('folder_id', '=='), ('discarded', '==')],
            [('created_at', DESC)],
            None,
            [('discarded', ASC), ('folder_id', ASC), ('created_at', DESC), ('__name__', DESC)],
        ),
    ],
)
def test_production_suggested_indexes(filters, orders, aggregation, expected):
    assert required_index(shape(filters, orders, aggregation)).fields == tuple(expected)


@pytest.mark.parametrize(
    'operator', ['==', 'in', '<', '<=', '>', '>=', '!=', 'not_in', 'array_contains', 'array_contains_any']
)
@pytest.mark.parametrize('aggregation', [None, 'count'])
def test_automatic_single_field_indexes(operator, aggregation):
    query = shape([('created_at', operator)], aggregation=aggregation)
    assert required_index(query) is None
    assert is_served(query, {})


def test_full_equality_prefix_permutations_and_modes_serve_range_query():
    query = shape([('a', '=='), ('b', 'in'), ('c', '=='), ('created_at', '>')])
    for prefix in permutations([('a', ASC), ('b', DESC), ('c', ASC)]):
        assert is_served(query, {'indexes': [entry([*prefix, ('created_at', ASC), ('__name__', ASC)])]})
    assert not is_served(
        query, {'indexes': [entry([('a', ASC), ('created_at', ASC), ('b', ASC), ('c', ASC), ('__name__', ASC)])]}
    )


def test_wrong_direction_missing_equality_extra_prefix_or_suffix_and_scope_are_rejected():
    query = shape([('discarded', '=='), ('created_at', '>')], aggregation='count')
    good = [('discarded', ASC), ('created_at', ASC), ('__name__', ASC)]
    for bad in [
        [('discarded', ASC), ('created_at', DESC), ('__name__', DESC)],
        [('created_at', ASC), ('__name__', ASC)],
        [('other', ASC), *good],
        [*good[:-1], ('other', ASC), good[-1]],
        [*good, ('other', ASC)],
        [*good[:-1], ('__name__', DESC)],
    ]:
        assert not is_served(query, {'indexes': [entry(bad)]})
    assert not is_served(query, {'indexes': [entry(good, scope='COLLECTION_GROUP')]})
    assert is_served(query, {'indexes': [entry(good[:-1])]})


@pytest.mark.parametrize('kind', ['count', 'sum', 'avg'])
def test_aggregation_range_implicit_ascending(kind):
    query = shape([('discarded', '=='), ('created_at', '>')], aggregation=kind)
    assert required_index(query).fields == (('discarded', ASC), ('created_at', ASC), ('__name__', ASC))


def test_multiple_ranges_append_lexicographically_in_last_order_direction():
    query = shape([('z', '>'), ('a', '<'), ('discarded', '==')])
    assert required_index(query).fields == (('discarded', ASC), ('a', ASC), ('z', ASC), ('__name__', ASC))
    query = shape([('z', '>'), ('a', '<'), ('discarded', '==')], [('z', DESC)])
    assert required_index(query).fields == (('discarded', ASC), ('z', DESC), ('a', DESC), ('__name__', DESC))


def test_array_mode_not_directional_and_document_name_order_is_respected():
    query = shape([('tags', 'array_contains_any'), ('discarded', '==')], [('created_at', DESC), ('__name__', ASC)])
    expected = [('tags', ARRAY), ('discarded', DESC), ('created_at', DESC), ('__name__', ASC)]
    assert is_served(query, {'indexes': [entry(expected)]})
    assert not is_served(
        query, {'indexes': [entry([(field, ASC if mode == ARRAY else mode) for field, mode in expected])]}
    )


def test_equality_and_array_merging_and_or_are_explicitly_uncertain():
    for filters in [[('a', '=='), ('b', '==')], [('a', 'in'), ('b', '==')], [('a', 'array_contains'), ('b', '==')]]:
        spec = required_index(shape(filters))
        assert spec.uncertain and 'merging' in spec.reason
    query = shape([('a', '=='), ('b', '>')], tree={'op': 'OR', 'filters': []})
    assert required_index(query).uncertain
    assert not is_served(query, {'indexes': [entry(candidate_index(query).fields)]})


def test_aggregation_fields_are_not_dropped():
    query = QueryShape(
        collection_group='conversations',
        filters=(QueryFilter('created_at', '>', 1),),
        aggregations=(Aggregation('sum', 'tokens'), Aggregation('avg', 'tokens')),
    )
    spec = required_index(query)
    assert spec.fields == (('created_at', ASC), ('tokens', ASC), ('__name__', ASC))
    assert spec.uncertain and 'aggregation-only' in spec.reason
    assert not is_served(query, {})


def test_collection_group_single_field_requires_opt_in_or_declared_index():
    query = shape([('status', '==')], scope='COLLECTION_GROUP')
    assert required_index(query) is not None
    assert not required_index(query).composite
    assert not is_served(query, {})
    assert is_served(
        query,
        {
            'fieldOverrides': [
                {
                    'collectionGroup': 'conversations',
                    'fieldPath': 'status',
                    'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': ASC}],
                }
            ]
        },
    )
    assert is_served(query, {'indexes': [entry([('status', ASC), ('__name__', ASC)], scope='COLLECTION_GROUP')]})
    assert is_served(shape(scope='COLLECTION_GROUP'), {})


def test_single_field_exemptions_wildcard_parent_and_specific_override():
    query = shape([('metadata.time', '>')])
    base = [{'collectionGroup': 'conversations', 'fieldPath': '*', 'indexes': []}]
    assert not is_served(query, {'fieldOverrides': base})
    assert not is_served(
        query, {'fieldOverrides': [{'collectionGroup': 'conversations', 'fieldPath': 'metadata', 'indexes': []}]}
    )
    assert is_served(
        query,
        {
            'fieldOverrides': [
                *base,
                {
                    'collectionGroup': 'conversations',
                    'fieldPath': 'metadata.time',
                    'indexes': [{'queryScope': 'COLLECTION', 'order': ASC}],
                },
            ]
        },
    )
    assert is_served(
        query, {'fieldOverrides': [{'collectionGroup': 'conversations', 'fieldPath': 'metadata.time', 'ttl': True}]}
    )


def test_in_field_explicit_order_is_directional_not_unordered_equality():
    query = shape([('status', 'in'), ('discarded', '==')], [('status', DESC), ('created_at', ASC)])
    assert candidate_index(query).fields == (
        ('discarded', ASC),
        ('status', DESC),
        ('created_at', ASC),
        ('__name__', ASC),
    )
    assert not is_served(
        query, {'indexes': [entry([('status', DESC), ('discarded', ASC), ('created_at', ASC), ('__name__', ASC)])]}
    )


def test_limit_to_last_uses_reversed_wire_order():
    query = replace(shape([('discarded', '==')], [('created_at', DESC)]), limit_to_last=True)
    assert required_index(query).fields == (('discarded', ASC), ('created_at', ASC), ('__name__', ASC))


def test_document_name_only_descending_is_not_assumed_automatic():
    query = shape([], [('__name__', DESC)])
    spec = required_index(query)
    assert spec is not None and spec.uncertain
    assert 'document-name-only descending' in spec.reason
    assert not is_served(query, {})


def test_explicit_name_direction_requires_matching_single_field_name_direction():
    query = shape([], [('created_at', DESC), ('__name__', ASC)])
    assert required_index(query) is not None
    assert not is_served(query, {})
    assert is_served(query, {'indexes': [entry([('created_at', DESC), ('__name__', ASC)])]})
