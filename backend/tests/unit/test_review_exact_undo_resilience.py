"""Hermetic unit tests for backend/database/review_exact_undo.py resilience."""

from types import SimpleNamespace

import pytest

from database import review_exact_undo


def test_patched_row_handles_none_row_and_non_dict_intermediate_parents():
    assert review_exact_undo.patched_row(None, {'a.b.c': 1}) == {'a': {'b': {'c': 1}}}
    assert review_exact_undo.patched_row({'a': None}, {'a.b': 'ok', '': 'ignored', 123: 'ignored'}) == {
        'a': {'b': 'ok'}
    }
    assert review_exact_undo.patched_row({'a': 'primitive'}, {'a.b.c': True}) == {'a': {'b': {'c': True}}}
    assert review_exact_undo.patched_row({'x': 1}, None) == {'x': 1}


def test_restored_row_handles_none_row_non_dict_parents_and_malformed_states():
    # Restoring present=True when intermediate parent is None replaces parent with dict
    res = review_exact_undo.restored_row({'a': None}, {'a.b': {'present': True, 'value': 42}})
    assert res == {'a': {'b': 42}}

    # Restoring present=False when intermediate parent is None/primitive does not raise AttributeError
    res_absent = review_exact_undo.restored_row({'a': None}, {'a.b': {'present': False}})
    assert res_absent == {'a': None}

    # Malformed state entries are ignored safely while valid present=False pops the key
    res_bad = review_exact_undo.restored_row(
        {'k': 1, 'm': 2},
        {'': {'present': True, 'value': 2}, 'k': 'not-a-dict', 'm': {'present': False}},
    )
    assert res_bad == {'k': 1}


@pytest.mark.parametrize(
    ('initial_row', 'patch', 'expected'),
    [
        (None, {'a': 1}, {'a': 1}),
        ('not-a-dict', {'a.b': 2}, {'a': {'b': 2}}),
        ([1, 2], {'a.b': 3}, {'a': {'b': 3}}),
        ({'a': 5}, {'a.b.c': 6}, {'a': {'b': {'c': 6}}}),
        ({'a': {'x': 1}}, {'a.y': 2}, {'a': {'x': 1, 'y': 2}}),
        ({'a': None}, {'': 1, '   ': 2, 'a.b': 3}, {'a': {'b': 3}}),
    ],
)
def test_patched_row_parametrized_edge_cases(initial_row, patch, expected):
    assert review_exact_undo.patched_row(initial_row, patch) == expected


@pytest.mark.parametrize(
    ('raw_gen', 'expected'),
    [
        (None, 0),
        (True, 0),
        (False, 0),
        (-5, 0),
        (0, 0),
        (4, 4),
        (4.8, 4),
        (float('nan'), 0),
        (float('inf'), 0),
        (' 9 ', 9),
        ('bad', 0),
    ],
)
def test_journal_fences_coerces_malformed_account_generation(raw_gen, expected):
    edit = SimpleNamespace(
        collection='action_items',
        document_id='task_1',
        patch={'completed': True},
    )
    journal = review_exact_undo.journal_fences(
        [edit],
        [(edit, None, {'completed': False})],
        {'task_intelligence_control/state': {'account_generation': raw_gen}},
    )
    assert journal['generation_fences']['task_intelligence_control/state'] == expected
    assert journal['reversal_fences'][0]['before'] == {'completed': {'present': True, 'value': False}}
    assert journal['reversal_fences'][0]['after'] == {'completed': {'present': True, 'value': True}}


def test_validate_generation_handles_malformed_journal_and_none_generation(monkeypatch):
    # Non-dict journal or missing generation_fences is a no-op
    review_exact_undo.validate_generation('u1', None, None)
    review_exact_undo.validate_generation('u1', None, {'generation_fences': None})
    review_exact_undo.validate_generation('u1', None, {'generation_fences': {'invalid_path_no_slash': 1}})

    payload_holder = {'data': {'account_generation': None}}

    class _UserNode:
        def collection(self, name):
            return self

        def document(self, key):
            return self

        def get(self, transaction=None):
            return SimpleNamespace(exists=True, to_dict=lambda: payload_holder['data'])

    monkeypatch.setattr(review_exact_undo.store, 'user', lambda uid: _UserNode())

    # None account_generation coerces to 0 and matches expected 0 without TypeError
    review_exact_undo.validate_generation(
        'u1',
        None,
        {'generation_fences': {'task_intelligence_control/state': 0}},
    )

    # Mismatched generation raises ReviewConflict
    payload_holder['data'] = {'account_generation': 2}
    with pytest.raises(review_exact_undo.store.ReviewConflict):
        review_exact_undo.validate_generation(
            'u1',
            None,
            {'generation_fences': {'task_intelligence_control/state': 1}},
        )


def test_validate_row_handles_malformed_journal_and_detects_conflicts():
    assert review_exact_undo.validate_row(None, 'action_items', 't1', {}, 'after') is False
    assert review_exact_undo.validate_row({'reversal_fences': 'bad'}, 'action_items', 't1', {}, 'after') is False
    assert (
        review_exact_undo.validate_row(
            {'reversal_fences': ['not-a-dict', {'collection': 'other'}]},
            'action_items',
            't1',
            {},
            'after',
        )
        is False
    )

    journal = {
        'reversal_fences': [
            {
                'collection': 'action_items',
                'document_id': 't1',
                'fields': ['completed'],
                'after': {'completed': {'present': True, 'value': True}},
            }
        ]
    }
    assert review_exact_undo.validate_row(journal, 'action_items', 't1', {'completed': True}, 'after') is True

    with pytest.raises(review_exact_undo.store.ReviewConflict):
        review_exact_undo.validate_row(journal, 'action_items', 't1', {'completed': False}, 'after')

    with pytest.raises(review_exact_undo.store.ReviewConflict):
        review_exact_undo.validate_row(journal, 'action_items', 't1', None, 'after')


def test_witness_snapshot_handles_non_dict_raw():
    snap = review_exact_undo.witness_snapshot('u1', 'action_items/t1', 'corrupt-raw')
    assert snap['fields']['description'] == {'present': False}
