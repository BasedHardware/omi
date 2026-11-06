"""Unit tests for the dream dirty-signal resilience fixes.

Verifies:
- ``after_write`` binds defaults before indexing so omitted default arguments and
  short signatures can no longer raise ``KeyError``/``IndexError`` after a write.
- ``after_write`` drops ``None``, booleans, blank ids and path-traversal ids instead
  of forwarding them into the queue payload.
- ``notify`` rejects unusable uids (blank, separators, traversal, control characters,
  over-long) and malformed refs before touching ``mark_dirty``.
- Fan-out is deduplicated and capped, and a store failure is still contained.
"""

from unittest.mock import MagicMock

import pytest

import database.dream_dirty as dream_dirty


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'normal')
    dream_dirty.dream_writing.set(False)
    dream_dirty.canary_writing.set(False)
    yield
    dream_dirty.dream_writing.set(False)
    dream_dirty.canary_writing.set(False)


@pytest.fixture
def mark_dirty(monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(dream_dirty, 'mark_dirty', mock)
    return mock


def _calls(mock):
    return [(c.args[0], c.args[1]) for c in mock.call_args_list]


# --- after_write argument binding -------------------------------------------------


def test_after_write_notifies_for_dict_payload(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', {'id': 'conv-1'})
    assert _calls(mark_dirty) == [('user-1', [('conversations', 'conv-1')])]


def test_after_write_notifies_every_row_of_a_list(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', [{'id': 'conv-1'}, {'id': 'conv-2'}])
    assert _calls(mark_dirty) == [('user-1', [('conversations', 'conv-1'), ('conversations', 'conv-2')])]


def test_after_write_applies_defaults_when_second_argument_is_omitted(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data={'id': 'default-conv'}):
        return True

    save('user-1')
    assert _calls(mark_dirty) == [('user-1', [('conversations', 'default-conv')])]


def test_after_write_tolerates_a_single_parameter_signature(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid):
        return True

    assert save('user-1') is True
    assert mark_dirty.call_args_list == []


def test_after_write_tolerates_a_varargs_signature(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(*args, **kwargs):
        return 'written'

    assert save('user-1', {'id': 'conv-1'}) == 'written'
    assert mark_dirty.call_args_list == []


def test_after_write_is_silent_when_mode_is_off(monkeypatch, mark_dirty):
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'off')

    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', {'id': 'conv-1'})
    assert mark_dirty.call_args_list == []


def test_after_write_is_silent_inside_a_dream_write(mark_dirty):
    dream_dirty.dream_writing.set(True)

    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', {'id': 'conv-1'})
    assert mark_dirty.call_args_list == []


def test_after_write_is_silent_when_the_write_reports_false(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return False

    save('user-1', {'id': 'conv-1'})
    assert mark_dirty.call_args_list == []


def test_after_write_uses_the_returned_id_for_action_items(mark_dirty):
    @dream_dirty.after_write('action_items')
    def save(uid, data):
        return 'task-9'

    save('user-1', {'content': 'no id here'})
    assert _calls(mark_dirty) == [('user-1', [('action_items', 'task-9')])]


def test_after_write_filters_unusable_action_item_ids(mark_dirty):
    @dream_dirty.after_write('action_items')
    def save(uid, data):
        return [None, True, '   ', '../../etc/passwd', 'task-1']

    save('user-1', {'content': 'no id here'})
    assert _calls(mark_dirty) == [('user-1', [('action_items', 'task-1')])]


def test_after_write_uses_the_returned_id_for_memory_items(mark_dirty):
    @dream_dirty.after_write('memory_items')
    def save(uid, data):
        return 'memory-3'

    save('user-1', {'content': 'no id here'})
    assert _calls(mark_dirty) == [('user-1', [('memory_items', 'memory-3')])]


def test_after_write_treats_a_string_payload_as_the_id(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', 'conv-7')
    assert _calls(mark_dirty) == [('user-1', [('conversations', 'conv-7')])]


def test_after_write_deduplicates_ids(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', [{'id': 'conv-1'}, {'id': 'conv-1'}, {'id': ' conv-1 '}])
    assert _calls(mark_dirty) == [('user-1', [('conversations', 'conv-1')])]


def test_after_write_caps_the_fan_out(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('user-1', [{'id': f'conv-{i}'} for i in range(150)])
    refs = mark_dirty.call_args_list[0].args[1]
    assert len(refs) == dream_dirty._MAX_REFS


def test_after_write_drops_an_unusable_uid(mark_dirty):
    @dream_dirty.after_write('conversations')
    def save(uid, data):
        return True

    save('   ', {'id': 'conv-1'})
    assert mark_dirty.call_args_list == []


# --- notify -----------------------------------------------------------------------


@pytest.mark.parametrize(
    'uid',
    ['', '   ', None, True, 42, 'a/b', 'a\\b', '..', 'a..b', '.', '__x__', 'x\x00y', 'x\x1fy', 'u' * 129],
)
def test_notify_rejects_unusable_uids(mark_dirty, uid):
    dream_dirty.notify(uid, [('conversations', 'conv-1')])
    assert mark_dirty.call_args_list == []


def test_notify_rejects_non_pair_refs(mark_dirty):
    dream_dirty.notify('user-1', ['conversations', ('conversations',), ('a', 'b', 'c'), None])
    assert mark_dirty.call_args_list == []


def test_notify_rejects_blank_or_unsafe_ref_tokens(mark_dirty):
    dream_dirty.notify('user-1', [('  ', 'conv-1'), ('conversations', '   '), ('conversations', '../x')])
    assert mark_dirty.call_args_list == []


def test_notify_drops_only_the_bad_refs(mark_dirty):
    dream_dirty.notify('user-1', [('conversations', 'conv-1'), ('conversations', ''), ('conversations', 'conv-2')])
    assert _calls(mark_dirty) == [('user-1', [('conversations', 'conv-1'), ('conversations', 'conv-2')])]


def test_notify_passes_the_canary_flag(mark_dirty):
    dream_dirty.canary_writing.set(True)
    dream_dirty.notify('user-1', [('dream_canary', 'conv-1')])
    (call,) = mark_dirty.call_args_list
    assert call.kwargs == {'canary': True}
    assert call.args == ('user-1', [('dream_canary', 'conv-1')])


def test_notify_is_silent_without_refs(mark_dirty):
    dream_dirty.notify('user-1', [])
    assert mark_dirty.call_args_list == []


def test_notify_contains_a_store_failure(monkeypatch):
    boom = MagicMock(side_effect=RuntimeError('redis down'))
    monkeypatch.setattr(dream_dirty, 'mark_dirty', boom)
    fallback = MagicMock()
    monkeypatch.setattr(dream_dirty, 'record_fallback', fallback)

    dream_dirty.notify('user-1', [('conversations', 'conv-1')])

    assert boom.call_args_list
    assert fallback.call_args_list

def test_after_write_coerces_numeric_row_ids(mark_dirty):
    """Numeric primary keys must still enqueue, exactly like ``str(row['id'])`` on main."""
    from database import dream_dirty

    @dream_dirty.after_write('conversations')
    def upsert(uid, row):
        return {'ok': True}

    upsert('uid-1', {'id': 123})

    mark_dirty.assert_called_once_with('uid-1', [('conversations', '123')])
