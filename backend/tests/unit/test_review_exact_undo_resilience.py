"""Hermetic regression tests for review_exact_undo malformed-payload handling.

Each case mirrors a payload that previously raised ``TypeError``/``AttributeError``/
``ValueError`` out of a reversible soft-cleanup fence, which aborted the whole undo
transaction instead of recording an unusable fence.
"""

import math

import pytest

from database import review_exact_undo as undo
from database.review_store import ReviewConflict

TARGET = 'task_intelligence_control/state'


class _Edit:
    def __init__(self, collection, document_id, patch):
        self.collection = collection
        self.document_id = document_id
        self.patch = patch


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, data):
        self._data = data

    def get(self, transaction=None):
        return _Snapshot(self._data)


class _Collection:
    def __init__(self, data):
        self._data = data

    def document(self, key):
        return _Document((self._data or {}).get(key))


class _User:
    def __init__(self, data):
        self._data = data

    def collection(self, name):
        return _Collection((self._data or {}).get(name))


@pytest.fixture
def fake_store(monkeypatch):
    """Point ``store.user`` at an in-memory document tree."""
    state: dict = {}
    monkeypatch.setattr(undo.store, 'user', lambda uid: _User(state))
    return state


def _fences(records, rows=()):
    return undo.journal_fences([], list(rows), records)


def _generation_for(payload):
    return _fences({TARGET: payload})['generation_fences'][TARGET]


# ------------------------------------------------------------------ patched_row


def test_patched_row_replaces_none_intermediate_with_dict():
    # ``{'promotion': None}`` used to make ``setdefault`` return ``None`` and the
    # following assignment raise ``TypeError: 'NoneType' object does not support
    # item assignment``.
    assert undo.patched_row({'promotion': None}, {'promotion.id': 5}) == {'promotion': {'id': 5}}


def test_patched_row_replaces_scalar_intermediate_with_dict():
    assert undo.patched_row({'promotion': 'text'}, {'promotion.id': 5}) == {'promotion': {'id': 5}}


def test_patched_row_merges_existing_nested_dict():
    assert undo.patched_row({'a': {'b': 1}}, {'a.b': 2}) == {'a': {'b': 2}}


def test_patched_row_tolerates_non_mapping_row():
    assert undo.patched_row(None, {'x': 1}) == {'x': 1}


def test_patched_row_tolerates_non_mapping_patch():
    assert undo.patched_row({'x': 1}, None) == {'x': 1}


def test_patched_row_skips_malformed_paths():
    assert undo.patched_row({'x': 1}, {'': 2, None: 3}) == {'x': 1}


def test_patched_row_does_not_mutate_source():
    source = {'a': {'b': 1}}
    result = undo.patched_row(source, {'a.b': 9})
    assert source == {'a': {'b': 1}}
    assert result == {'a': {'b': 9}}


# ---------------------------------------------------------------- restored_row


def test_restored_row_drops_through_none_parent():
    # Removal through a ``None`` parent used to raise
    # ``AttributeError: 'NoneType' object has no attribute 'pop'``.
    assert undo.restored_row({'promotion': None}, {'promotion.id': {'present': False}}) == {'promotion': {}}


def test_restored_row_removes_nested_field():
    assert undo.restored_row({'a': {'b': 1}}, {'a.b': {'present': False}}) == {'a': {}}


def test_restored_row_restores_value():
    assert undo.restored_row({'a': 1}, {'a': {'present': True, 'value': 9}}) == {'a': 9}


def test_restored_row_tolerates_non_mapping_row():
    assert undo.restored_row(None, {}) == {}


def test_restored_row_skips_malformed_state():
    assert undo.restored_row({'a': 1}, {'a': None}) == {'a': 1}


def test_restored_row_treats_missing_present_flag_as_removal():
    assert undo.restored_row({'a': 1}, {'a': {'value': 2}}) == {}


# --------------------------------------------------------------- journal_fences


@pytest.mark.parametrize(
    'payload',
    [
        {'account_generation': None},
        {'account_generation': 'NaN'},
        {'account_generation': math.nan},
        {'account_generation': math.inf},
        {'account_generation': -math.inf},
        {'account_generation': True},
        {'account_generation': -5},
        {'account_generation': ['unexpected']},
        None,
        'not-a-mapping',
    ],
)
def test_journal_fences_coerces_unusable_generation_to_zero(payload):
    # ``int((raw or {}).get('account_generation', 0))`` used to raise
    # ``TypeError`` on ``None``/``bool`` and ``ValueError`` on ``NaN``/``inf``.
    assert _generation_for(payload) == 0


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        ({'account_generation': ' 42 '}, 42),
        ({'account_generation': 4.0}, 4),
        ({'account_generation': '7'}, 7),
        ({'account_generation': 0}, 0),
    ],
)
def test_journal_fences_keeps_usable_generation(payload, expected):
    assert _generation_for(payload) == expected


def test_journal_fences_tolerates_missing_expected_records():
    assert _fences(None)['generation_fences'] == {}


def test_journal_fences_tolerates_none_row_payload():
    rows = [(_Edit('action_items', 'a1', {'owner': 'u'}), None, None)]
    fence = _fences({}, rows)['reversal_fences'][0]
    assert fence['before'] == {'owner': {'present': False}}
    assert fence['after'] == {'owner': {'present': True, 'value': 'u'}}


def test_journal_fences_tolerates_non_mapping_patch():
    rows = [(_Edit('action_items', 'a1', None), None, {'x': 1})]
    fence = _fences({}, rows)['reversal_fences'][0]
    assert fence['fields'] == []


# ----------------------------------------------------------- validate_generation


def test_validate_generation_skips_path_without_separator(fake_store):
    # ``path.split('/', 1)`` used to raise ``ValueError: not enough values to
    # unpack`` for a fence key without a collection separator.
    undo.validate_generation('u', None, {'generation_fences': {'no-slash': 3}})


def test_validate_generation_skips_non_string_path(fake_store):
    undo.validate_generation('u', None, {'generation_fences': {None: 3}})


def test_validate_generation_returns_none_for_malformed_journal(fake_store):
    undo.validate_generation('u', None, None)


def test_validate_generation_treats_none_generation_as_zero(fake_store):
    fake_store['task_intelligence_control'] = {'state': {'account_generation': None}}
    undo.validate_generation('u', None, {'generation_fences': {TARGET: None}})


def test_validate_generation_accepts_matching_generation(fake_store):
    fake_store['task_intelligence_control'] = {'state': {'account_generation': 3}}
    undo.validate_generation('u', None, {'generation_fences': {TARGET: 3}})


def test_validate_generation_raises_on_mismatch(fake_store):
    fake_store['task_intelligence_control'] = {'state': {'account_generation': 7}}
    with pytest.raises(ReviewConflict):
        undo.validate_generation('u', None, {'generation_fences': {TARGET: 3}})


# ------------------------------------------------------------------ validate_row

_ROW_JOURNAL = {
    'reversal_fences': [
        {
            'collection': 'action_items',
            'document_id': 'a1',
            'fields': ['owner'],
            'before': {'owner': {'present': False}},
        }
    ]
}


def test_validate_row_returns_false_for_non_mapping_journal():
    assert undo.validate_row(None, 'action_items', 'a1', {}, 'before') is False


def test_validate_row_returns_false_for_non_list_fences():
    assert undo.validate_row({'reversal_fences': 'broken'}, 'action_items', 'a1', {}, 'before') is False


def test_validate_row_skips_malformed_fence_entries():
    journal = {'reversal_fences': ['junk', {'collection': 'other'}]}
    assert undo.validate_row(journal, 'action_items', 'a1', {}, 'before') is False


def test_validate_row_raises_without_expected_key():
    with pytest.raises(ReviewConflict):
        undo.validate_row(_ROW_JOURNAL, 'action_items', 'a1', {}, 'nope')


def test_validate_row_matches_recorded_state():
    assert undo.validate_row(_ROW_JOURNAL, 'action_items', 'a1', {}, 'before') is True


def test_validate_row_rejects_newer_edit():
    with pytest.raises(ReviewConflict):
        undo.validate_row(_ROW_JOURNAL, 'action_items', 'a1', {'owner': 'newer'}, 'before')


def test_validate_row_rejects_missing_current_row():
    with pytest.raises(ReviewConflict):
        undo.validate_row(_ROW_JOURNAL, 'action_items', 'a1', None, 'before')


def test_validate_row_tolerates_non_list_fields():
    journal = {'reversal_fences': [{'collection': 'x', 'document_id': 'y', 'fields': 'broken', 'before': {}}]}
    assert undo.validate_row(journal, 'x', 'y', {}, 'before') is True


# --------------------------------------------------------------- witness_snapshot


def test_witness_snapshot_tolerates_missing_path():
    result = undo.witness_snapshot('u', None, None)
    assert sorted(result['fields']) == ['name', 'redirect_entity_id']


def test_witness_snapshot_tolerates_non_mapping_raw():
    result = undo.witness_snapshot('u', 'action_items/a1', None)
    assert result['fields']['owner'] == {'present': False}


def test_witness_snapshot_tolerates_scalar_path():
    assert undo.witness_snapshot('u', 'weird', 'not-a-mapping')


def test_witness_snapshot_keeps_conversation_fingerprint():
    result = undo.witness_snapshot('u', 'conversations/c1', None)
    assert 'speech' in result
