"""Adversarial checks for the development-only exact retrieval candidate."""

from copy import deepcopy
from dataclasses import replace
import math

import pytest

from testing.pinecone_exact_candidate import CandidateRejected, ExactFixtureOwnerIndex, ReadAuthority

OWNER = 'exact-candidate-owner'


def record(item, cosine):
    return {
        'id': f'{OWNER}-ai-{item}',
        'values': [cosine, math.sqrt(1 - cosine * cosine)],
        'metadata': {'uid': OWNER, 'action_item_id': item},
    }


def candidate(rows=None, **kwargs):
    rows = rows if rows is not None else [record('a', 0.8), record('b', 0.2)]
    authority = ReadAuthority('memories-backend-dev', OWNER, 'ns4', 17, 'fixture-token')
    arguments = dict(
        authority=authority,
        read_authority=lambda: authority,
        manifest=rows,
        fetched=deepcopy(rows),
        provider_namespace='ns4',
        write_lsn=7,
        indexed_lsn=7,
        dimension=2,
    )
    arguments.update(kwargs)
    return ExactFixtureOwnerIndex(**arguments)


def query(index, **kwargs):
    arguments = dict(namespace='ns4', vector=[1.0, 0.0], top_k=10, filter={'uid': OWNER}, include_metadata=True)
    arguments.update(kwargs)
    return index.query(**arguments)['matches']


def test_exact_scores_keep_distinct_task_ids_and_threshold_boundaries():
    rows = [
        record('below-search', 0.299946874),
        record('above-search', 0.30013625507732045),
        record('below-dedup', 0.599999),
        record('above-dedup', 0.600001),
        record('tie-z', 0.8),
        record('tie-a', 0.8),
    ]
    for _ in range(3):
        source = query(candidate(rows))
        target = query(candidate(list(reversed(rows))))
        assert source == target
        assert [m['metadata']['action_item_id'] for m in source if m['score'] >= 0.3] == [
            'tie-a',
            'tie-z',
            'above-dedup',
            'below-dedup',
            'above-search',
        ]
        assert [m['metadata']['action_item_id'] for m in source if m['score'] >= 0.6] == [
            'tie-a',
            'tie-z',
            'above-dedup',
        ]


def test_manifest_and_returned_records_cannot_mutate_snapshot():
    rows = [record('a', 0.8)]
    index = candidate(rows)
    rows[0]['values'][0] = -1
    rows[0]['metadata']['action_item_id'] = 'replaced'
    first = query(index, include_values=True)
    first[0]['metadata']['action_item_id'] = 'altered'
    first[0]['values'][0] = -1
    assert query(index)[0]['metadata']['action_item_id'] == 'a'
    assert query(index)[0]['score'] == pytest.approx(0.8)


@pytest.mark.parametrize(
    'change',
    [
        {'revision': 18},
        {'migration_token': 'new'},
        {'namespace': 'other'},
        {'uid': 'other'},
        {'index_name': 'other'},
        {'pending_count': 1},
        {'uncertain_count': 1},
        {'route_exists': False},
        {'deletion_blocked': True},
    ],
)
def test_guard_rejects_changes_before_or_during_scoring(change):
    for during in (False, True):
        index = candidate()
        original = index.authority
        states = iter([original, replace(original, **change)] if during else [replace(original, **change)])
        index.read_authority = lambda: next(states)
        with pytest.raises(CandidateRejected):
            query(index)


@pytest.mark.parametrize(
    'change',
    [
        {'pending_count': 1},
        {'uncertain_count': 1},
        {'route_exists': False},
        {'deletion_blocked': True},
        {'index_name': 'memories-backend'},
        {'uid': 'real-user'},
    ],
)
def test_unsafe_initial_authority_never_admitted(change):
    authority = replace(ReadAuthority('memories-backend-dev', OWNER, 'ns4', 17), **change)
    with pytest.raises(CandidateRejected):
        candidate(authority=authority, read_authority=lambda: authority)


@pytest.mark.parametrize(
    'kwargs',
    [
        {'provider_namespace': 'other'},
        {'write_lsn': 8},
        {'write_lsn': 0},
        {'indexed_lsn': None},
        {'write_lsn': True},
        {'dimension': 0},
    ],
)
def test_freshness_and_bounds(kwargs):
    with pytest.raises(CandidateRejected):
        candidate(**kwargs)


def test_valid_freshness_cannot_admit_an_unrelated_namespace():
    authority = ReadAuthority('memories-backend-dev', OWNER, 'ns2', 17)
    with pytest.raises(CandidateRejected):
        candidate(authority=authority, read_authority=lambda: authority, provider_namespace='ns2')


def test_manifest_requires_all_records_and_exact_payloads():
    rows = [record('a', 0.8), record('b', 0.2)]
    altered = deepcopy(rows)
    altered[0]['values'] = [0.81, 0.5]
    metadata = deepcopy(rows)
    metadata[0]['metadata']['action_item_id'] = 'wrong'
    foreign = deepcopy(rows)
    foreign[0]['metadata']['uid'] = 'other'
    for fetched in (rows[:1], rows + [record('c', 0.1)], rows + rows[:1], altered, metadata, foreign):
        with pytest.raises(CandidateRejected):
            candidate(rows, fetched=fetched)


@pytest.mark.parametrize('values', [[0, 0], [float('nan'), 1], [float('inf'), 1], [1], [True, 1]])
def test_invalid_vectors_are_rejected(values):
    with pytest.raises(CandidateRejected):
        query(candidate(), vector=values)
    row = record('a', 0.8)
    row['values'] = values
    with pytest.raises(CandidateRejected):
        candidate([row])


@pytest.mark.parametrize(
    'kwargs',
    [
        {'filter': {'uid': 'other'}},
        {'filter': {'uid': OWNER, 'completed': False}},
        {'filter': {'$or': [{'uid': OWNER}, {'uid': 'other'}]}},
        {'namespace': 'ns2'},
        {'top_k': 0},
        {'top_k': True},
        {'top_k': 129},
        {'sparse_vector': {}},
        {'include_values': 'true'},
    ],
)
def test_unsupported_queries_do_not_silently_approximate(kwargs):
    with pytest.raises(CandidateRejected):
        query(candidate(), **kwargs)


def test_empty_and_oversized_manifests():
    assert query(candidate([])) == []
    with pytest.raises(CandidateRejected):
        candidate([record(str(i), 0.5) for i in range(129)])


def test_normalization_handles_large_finite_coordinates():
    row = record('a', 0.8)
    row['values'] = [1e300, 1e300]
    assert query(candidate([row]), vector=[1e300, 1e300])[0]['score'] == pytest.approx(1.0)
