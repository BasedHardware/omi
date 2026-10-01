import json
from dataclasses import replace
from itertools import permutations
from pathlib import Path

import pytest

from database.firestore_index_registry import firebase_index_manifest
from scripts.firestore_index_oracle import equivalent_suggestion
from tests.support.firestore_index_rules import (
    ASC,
    DESC,
    ARRAY,
    MERGING_REASON,
    candidate_index,
    is_merged,
    is_served,
    required_index,
    resolved_candidate_index,
)
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


def test_collection_group_descending_single_field_also_serves_equality():
    """Equality is unordered: a DESCENDING-only group override must not be a false gap."""
    query = shape([('status', '==')], scope='COLLECTION_GROUP')
    assert is_served(
        query,
        {
            'fieldOverrides': [
                {
                    'collectionGroup': 'conversations',
                    'fieldPath': 'status',
                    'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': DESC}],
                }
            ]
        },
    )


def test_validity_uncertain_shape_stays_unserved_even_with_matching_manifest_index():
    """A declared index cannot prove an invalid query is valid.

    Two ``array_contains`` fields are validity-uncertain; the generated
    candidate index (with a manifest entry matching it exactly) must not flip
    the shape to served, or the uncertainty ledger would silently lose it.
    """
    query = shape([('tags', 'array_contains'), ('labels', 'array_contains')])
    spec = candidate_index(query)
    assert spec.uncertain
    assert spec.validity_uncertain
    assert not is_served(query, {'indexes': [entry(spec.fields)]})


def test_unsupported_operator_stays_unserved_even_with_matching_manifest_index():
    """An operator the analyzer cannot classify keeps the shape out of served."""
    query = shape([('status', 'regex')])
    spec = candidate_index(query)
    assert spec.validity_uncertain
    assert not is_served(query, {'indexes': [entry(spec.fields)]})


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


_DISABLED_SINGLES = [{'collectionGroup': 'conversations', 'fieldPath': '*', 'indexes': []}]


def _manifest(indexes, overrides=_DISABLED_SINGLES):
    return {'indexes': indexes, 'fieldOverrides': overrides}


def test_merging_combines_composite_equality_prefixes_over_shared_suffix():
    query = shape([('a', '=='), ('b', '=='), ('c', '==')])
    manifest = _manifest([entry([('a', ASC), ('b', ASC), ('__name__', ASC)]), entry([('c', ASC), ('__name__', ASC)])])
    assert is_merged(query, manifest)
    assert is_served(query, manifest)
    assert not is_merged(query, _manifest([entry([('a', ASC), ('b', ASC), ('__name__', ASC)])]))


def test_merging_equality_prefix_direction_and_permutation_are_free():
    query = shape([('a', '=='), ('b', '=='), ('c', '=='), ('created_at', '>')])
    suffix = [('created_at', ASC), ('__name__', ASC)]
    for prefix in permutations([('a', ASC), ('b', DESC)]):
        manifest = _manifest([entry([*prefix, *suffix]), entry([('c', DESC), *suffix])])
        assert is_served(query, manifest)


def test_merging_rejects_mismatched_suffix_name_scope_collection_and_extra_fields():
    query = shape([('a', '=='), ('b', '=='), ('created_at', '>')])
    manifest = _manifest([entry([('a', ASC), ('b', ASC), ('created_at', ASC), ('__name__', ASC)])])
    assert is_served(query, manifest)
    for bad in [
        [('a', ASC), ('b', ASC), ('created_at', DESC), ('__name__', DESC)],
        [('a', ASC), ('b', ASC), ('created_at', ASC), ('__name__', DESC)],
        [('a', ASC), ('b', ASC), ('__name__', ASC)],
        [('a', ASC), ('extra', ASC), ('b', ASC), ('created_at', ASC), ('__name__', ASC)],
        [('a', ASC), ('a', DESC), ('b', ASC), ('created_at', ASC), ('__name__', ASC)],
        [('a', ASC), ('created_at', ASC), ('__name__', ASC)],
    ]:
        assert not is_served(query, _manifest([entry(bad)])), bad
    wrong_scope = entry([('a', ASC), ('b', ASC), ('created_at', ASC), ('__name__', ASC)], scope='COLLECTION_GROUP')
    assert not is_served(query, _manifest([wrong_scope]))
    other = dict(wrong_scope, queryScope='COLLECTION', collectionGroup='other')
    assert not is_served(query, _manifest([other]))


def test_merging_automatic_single_field_indexes_cover_equalities():
    query = shape([('a', '=='), ('b', '==')])
    assert is_served(query, {})
    assert not is_served(query, _manifest([]))
    assert is_served(
        query,
        {
            'indexes': [],
            'fieldOverrides': [
                {
                    'collectionGroup': 'conversations',
                    'fieldPath': '*',
                    'indexes': [{'queryScope': 'COLLECTION', 'order': ASC}],
                }
            ],
        },
    )
    assert not is_served(
        query,
        {'indexes': [], 'fieldOverrides': [{'collectionGroup': 'conversations', 'fieldPath': 'a', 'indexes': []}]},
    )
    grouped = shape([('a', '=='), ('b', '==')], scope='COLLECTION_GROUP')
    assert not is_merged(grouped, {})
    group_override = {
        'indexes': [],
        'fieldOverrides': [
            {
                'collectionGroup': 'conversations',
                'fieldPath': '*',
                'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': ASC}],
            }
        ],
    }
    assert is_merged(grouped, group_override)
    assert is_served(grouped, group_override)


def test_merging_requires_array_suffix_name_ascending_only():
    query = shape([('tags', 'array_contains'), ('a', '==')])
    assert is_served(query, {})
    ordered = shape([('tags', 'array_contains'), ('a', '==')], [('created_at', ASC)])
    manifest = _manifest(
        [
            entry([('tags', ARRAY), ('created_at', ASC), ('__name__', ASC)]),
            entry([('a', ASC), ('created_at', ASC), ('__name__', ASC)]),
        ]
    )
    assert not is_merged(ordered, manifest)
    assert not is_served(ordered, manifest)


def test_merging_never_inferred_for_uncertain_or_or_not_in_multi_range_or_aggregate():
    covered = [entry([('a', ASC), ('b', ASC), ('__name__', ASC)])]
    manifest = _manifest(covered)
    or_shape = shape([('a', '=='), ('b', '==')], tree={'op': 'OR', 'filters': []})
    assert not is_merged(or_shape, manifest)
    assert not is_merged(shape([('a', '!='), ('b', '==')]), manifest)
    assert not is_merged(shape([('a', 'not_in'), ('b', '==')]), manifest)
    ranged = _manifest(
        [
            entry([('a', ASC), ('x', ASC), ('y', ASC), ('__name__', ASC)]),
            entry([('b', ASC), ('x', ASC), ('y', ASC), ('__name__', ASC)]),
        ]
    )
    multi_range = QueryShape(
        collection_group='conversations',
        filters=(
            QueryFilter('a', '==', 1),
            QueryFilter('b', '==', 1),
            QueryFilter('x', '>', 1),
            QueryFilter('y', '>', 1),
        ),
    )
    assert not is_merged(multi_range, ranged)
    for kind in ('sum', 'avg'):
        assert not is_merged(shape([('a', '=='), ('b', '==')], aggregation=kind), manifest)
    assert not is_merged(shape([('a', 'regex'), ('b', '==')]), manifest)
    assert not is_merged(shape([('tags', 'array_contains'), ('labels', 'array_contains')]), _manifest([]))


def test_merging_rejects_malformed_in_operands():
    manifest = _manifest([entry([('a', ASC), ('b', ASC), ('__name__', ASC)])])
    assert not is_merged(shape([('a', 'in'), ('b', '==')]), manifest)
    scalar_in = QueryShape(
        collection_group='conversations', filters=(QueryFilter('a', 'in', 1), QueryFilter('b', '==', 1))
    )
    assert not is_merged(scalar_in, manifest)
    empty_in = QueryShape(
        collection_group='conversations', filters=(QueryFilter('a', 'in', []), QueryFilter('b', '==', 1))
    )
    assert not is_merged(empty_in, manifest)


def test_merging_single_multi_in_requires_anchor_covering_every_equality():
    query = QueryShape(
        collection_group='conversations',
        filters=(
            QueryFilter('a', '==', 1),
            QueryFilter('b', '==', 1),
            QueryFilter('status', 'in', ['x', 'y']),
        ),
        orders=(('created_at', DESC),),
    )
    suffix = [('created_at', DESC), ('__name__', DESC)]
    anchored = _manifest(
        [
            entry([('status', ASC), ('a', ASC), *suffix]),
            entry([('b', ASC), *suffix]),
        ]
    )
    assert is_merged(query, anchored)
    assert is_served(query, anchored)
    split_anchor = _manifest(
        [
            entry([('status', ASC), ('a', ASC), *suffix]),
            entry([('status', ASC), ('b', ASC), *suffix]),
        ]
    )
    assert not is_merged(query, split_anchor)
    assert not is_served(query, split_anchor)
    singleton = QueryShape(
        collection_group='conversations',
        filters=(
            QueryFilter('a', '==', 1),
            QueryFilter('b', '==', 1),
            QueryFilter('status', 'in', ['x']),
        ),
        orders=(('created_at', DESC),),
    )
    assert is_merged(singleton, split_anchor)
    covering_anchor = _manifest([entry([('status', ASC), ('a', ASC), ('b', ASC), *suffix])])
    assert is_merged(query, covering_anchor)


def test_merging_singleton_or_multiple_multi_in_use_plain_union():
    suffix = [('created_at', DESC), ('__name__', DESC)]
    singleton = QueryShape(
        collection_group='conversations',
        filters=(QueryFilter('a', '==', 1), QueryFilter('status', 'in', ['x'])),
        orders=(('created_at', DESC),),
    )
    manifest = _manifest([entry([('a', ASC), *suffix]), entry([('status', ASC), *suffix])])
    assert is_merged(singleton, manifest)
    double_multi = QueryShape(
        collection_group='conversations',
        filters=(
            QueryFilter('a', '==', 1),
            QueryFilter('status', 'in', ['x', 'y']),
            QueryFilter('kind', 'in', ['p', 'q']),
        ),
        orders=(('created_at', DESC),),
    )
    union_manifest = _manifest(
        [
            entry([('status', ASC), *suffix]),
            entry([('kind', ASC), *suffix]),
            entry([('a', ASC), *suffix]),
        ]
    )
    assert is_merged(double_multi, union_manifest)
    unanchored = _manifest(
        [
            entry([('status', ASC), ('a', ASC), *suffix]),
            entry([('kind', ASC), ('a', ASC), *suffix]),
        ]
    )
    assert is_merged(double_multi, unanchored)


def test_resolved_candidate_index_clears_only_proven_merging_reason():
    query = shape([('a', '=='), ('b', '==')])
    spec = candidate_index(query)
    assert spec.uncertain and spec.reason == MERGING_REASON
    resolved = resolved_candidate_index(query, {})
    assert resolved.fields == spec.fields
    assert resolved.equality_fields == spec.equality_fields
    assert resolved.composite == spec.composite
    assert resolved.uncertain is False
    assert resolved.reason == ''
    blocked = resolved_candidate_index(query, _manifest([]))
    assert blocked.uncertain and blocked.reason == MERGING_REASON


def test_resolved_candidate_index_preserves_other_uncertainty_reasons():
    grouped = shape([('a', '=='), ('b', '==')], scope='COLLECTION_GROUP')
    group_manifest = {
        'indexes': [entry([('a', ASC), ('b', ASC), ('__name__', ASC)], scope='COLLECTION_GROUP')],
        'fieldOverrides': [],
    }
    resolved = resolved_candidate_index(grouped, group_manifest)
    assert resolved.uncertain and resolved.reason == MERGING_REASON
    name_desc = shape([], [('__name__', DESC)])
    resolved = resolved_candidate_index(name_desc, {})
    assert resolved.uncertain and 'document-name-only descending' in resolved.reason
    invalid = shape([('tags', 'array_contains'), ('labels', 'array_contains')])
    resolved = resolved_candidate_index(invalid, _manifest([]))
    assert resolved.uncertain
    assert 'query-validity' in resolved.reason
    assert resolved.reason == candidate_index(invalid).reason
    or_shape = shape([('a', '=='), ('b', '==')], tree={'op': 'OR', 'filters': []})
    resolved = resolved_candidate_index(or_shape, {})
    assert resolved.uncertain and 'OR branches' in resolved.reason


def _signature_value(leaf):
    if 'disjunction_size' in leaf:
        return list(range(1, leaf['disjunction_size'] + 1))
    if leaf.get('unary') == 'null':
        return None
    return 1


def _shape_from_signature(signature):
    def build(node):
        if 'filters' in node:
            return {'op': node['op'], 'filters': [build(child) for child in node['filters']]}
        return {'field': node['field'], 'operator': node['operator'], 'value': _signature_value(node)}

    def flatten(node):
        if node is None:
            return []
        if 'filters' in node:
            return [leaf for child in node['filters'] for leaf in flatten(child)]
        return [QueryFilter(node['field'], node['operator'], node['value'])]

    tree = build(signature['filters']) if signature.get('filters') else None
    return QueryShape(
        collection_group=signature['collection'],
        scope=signature['scope'],
        filters=tuple(flatten(tree)),
        orders=tuple((order['field'], order['direction']) for order in signature['orders']),
        aggregations=tuple(Aggregation(item['kind'], item['field']) for item in signature['aggregations']),
        limit_to_last=signature['limit_to_last'],
        filter_tree=tree,
    )


MERGING_FIXTURE = json.loads(
    (Path(__file__).resolve().parent / 'fixtures' / 'firestore_index_merging.json').read_text()
)


@pytest.mark.parametrize('case', MERGING_FIXTURE['cases'], ids=[case['label'] for case in MERGING_FIXTURE['cases']])
def test_merging_fixture_replay(case):
    shape = _shape_from_signature(case['signature'])
    manifest = {
        'indexes': [MERGING_FIXTURE['indexes'][index_id] for index_id in case['index_ids']],
        'fieldOverrides': case['fieldOverrides'],
    }
    observed_served = case['observed'] == 'served'
    assert is_served(shape, manifest) == observed_served
    if not observed_served:
        assert equivalent_suggestion(required_index(shape), case['suggested_index'])
    spec = candidate_index(shape)
    resolved = resolved_candidate_index(shape, manifest)
    assert resolved.fields == spec.fields
    assert resolved.equality_fields == spec.equality_fields


def _generated_manifest():
    return firebase_index_manifest()


@pytest.mark.parametrize(
    'collection,field',
    [
        ('conversations', 'id'),
        ('conversations', 'source'),
        ('conversations', 'status'),
        ('fair_use_events', 'case_ref'),
        ('fcm_tokens', 'app_version'),
        ('fcm_tokens', 'token'),
        ('llm_usage', 'date'),
        ('processing_memories', 'created_at'),
        ('candidate_integration_outbox', 'status'),
        ('chat_first_proactive_intents', 'delivery_state'),
        ('memory_outbox', 'status'),
        ('projection_repairs', 'status'),
        ('task_recurrence_inbox', 'status'),
    ],
)
def test_declared_field_requirement_serves_collection_group_single_field_shapes(collection, field):
    query = QueryShape(
        collection_group=collection,
        scope='COLLECTION_GROUP',
        filters=(QueryFilter(field, '==', 'x'),),
    )
    assert is_served(query, _generated_manifest())


def test_declared_contains_requirement_serves_collection_group_array_shapes():
    query = QueryShape(
        collection_group='memories',
        scope='COLLECTION_GROUP',
        filters=(QueryFilter('tags', 'array_contains', 'x'),),
    )
    assert is_served(query, _generated_manifest())


def test_collection_group_single_field_not_served_by_mismatched_scope_or_field():
    manifest = _generated_manifest()
    assert not is_served(
        QueryShape(
            collection_group='conversations',
            scope='COLLECTION_GROUP',
            filters=(QueryFilter('unrelated_field', '==', 'x'),),
        ),
        manifest,
    )
    collection_only = {
        'indexes': [],
        'fieldOverrides': [
            {
                'collectionGroup': 'memory_outbox',
                'fieldPath': 'status',
                'indexes': [{'queryScope': 'COLLECTION', 'order': ASC}],
            }
        ],
    }
    assert not is_served(
        QueryShape(
            collection_group='memory_outbox',
            scope='COLLECTION_GROUP',
            filters=(QueryFilter('status', '==', 'x'),),
        ),
        collection_only,
    )
