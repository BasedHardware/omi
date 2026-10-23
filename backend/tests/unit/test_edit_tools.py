"""Hermetic guards for the chat edit tools.

These tests never touch Firestore, MCP handlers or a real LangChain runnable
config. They pin the defensive contract of ``utils.retrieval.tools.edit_tools``:
a ``None`` ``configurable`` or a ``None`` string argument must produce a clean
permission error / validation message instead of an ``AttributeError``.

``.func`` is used where a ``None`` must be forced through the guard: LangChain's
generated argument schema would otherwise coerce or reject the value before the
tool body runs, which is exactly the layer these tests want to bypass.
"""

import json

import pytest

from utils.retrieval.tools import edit_tools

OWNER = 'test-owner'


def _stub_ref(monkeypatch, resolved='ref-1'):
    """Replace ref resolution so no turn state or Firestore read is needed."""
    calls = []

    def fake_resolve(configurable, collection, record_id, *, parameter, default_to_attachment=False):
        calls.append(
            {
                'configurable': configurable,
                'collection': collection,
                'record_id': record_id,
                'parameter': parameter,
            }
        )
        return resolved, None

    monkeypatch.setattr(edit_tools, 'resolve_edit_ref', fake_resolve)
    return calls


def _error_code(result):
    return json.loads(result)['error']['code']


def test_owner_reads_nested_configurable():
    assert edit_tools.owner({'configurable': {'user_id': OWNER}}) == OWNER


def test_owner_reads_top_level_user_id_when_configurable_is_none():
    assert edit_tools.owner({'configurable': None, 'user_id': OWNER}) == OWNER


def test_owner_reads_top_level_user_id_when_configurable_missing():
    assert edit_tools.owner({'user_id': OWNER}) == OWNER


@pytest.mark.parametrize(
    'config',
    [
        None,
        {},
        {'configurable': None},
        {'configurable': {}},
        {'configurable': None, 'user_id': ''},
        {'configurable': 'not-a-mapping', 'user_id': None},
    ],
)
def test_owner_raises_permission_error_instead_of_attribute_error(config):
    with pytest.raises(PermissionError, match='Authenticated owner required'):
        edit_tools.owner(config)


def test_owner_tolerates_non_mapping_config():
    with pytest.raises(PermissionError):
        edit_tools.owner('not-a-config')


def test_update_conversation_rejects_none_correction(monkeypatch):
    _stub_ref(monkeypatch)
    result = edit_tools.update_conversation.func(
        conversation_id='c1', correction=None, title='Corrected', config={'configurable': {'user_id': OWNER}}
    )
    assert _error_code(result) == 'invalid_correction'


def test_update_conversation_passes_mapping_not_none_to_ref_resolution(monkeypatch):
    calls = _stub_ref(monkeypatch)
    edit_tools.update_conversation.func(
        conversation_id='c1', correction=None, title='Corrected', config={'configurable': None, 'user_id': OWNER}
    )
    assert calls[0]['configurable'] == {}


def test_update_conversation_rejects_blank_correction(monkeypatch):
    _stub_ref(monkeypatch)
    result = edit_tools.update_conversation.func(
        conversation_id='c1', correction='   ', title='Corrected', config={'configurable': {'user_id': OWNER}}
    )
    assert _error_code(result) == 'invalid_correction'


def test_update_conversation_requires_a_title_or_overview(monkeypatch):
    _stub_ref(monkeypatch)
    result = edit_tools.update_conversation.func(
        conversation_id='c1', correction='Confirmed by the user', config={'configurable': {'user_id': OWNER}}
    )
    assert _error_code(result) == 'invalid_correction'


def test_update_conversation_none_configurable_raises_permission_error():
    with pytest.raises(PermissionError):
        edit_tools.update_conversation.func(correction='Confirmed', title='Corrected', config={'configurable': None})


def test_rename_person_rejects_blank_name(monkeypatch):
    calls = _stub_ref(monkeypatch)
    for blank in (None, '', '   '):
        result = edit_tools.rename_person.func(
            person_id='p1', name=blank, config={'configurable': {'user_id': OWNER}}
        )
        assert result == 'Error: name must contain 1 to 300 characters.'
    assert calls == []


def test_rename_person_rejects_overlong_name(monkeypatch):
    _stub_ref(monkeypatch)
    result = edit_tools.rename_person.func(
        person_id='p1', name='n' * 301, config={'configurable': {'user_id': OWNER}}
    )
    assert result == 'Error: name must contain 1 to 300 characters.'


def test_edit_memory_rejects_none_content(monkeypatch):
    _stub_ref(monkeypatch)
    result = edit_tools.edit_memory.func(
        memory_id='m1', content=None, config={'configurable': {'user_id': OWNER}}
    )
    assert result == 'Error: memory content must contain 1 to 20000 characters.'


def test_edit_memory_rejects_blank_and_overlong_content(monkeypatch):
    _stub_ref(monkeypatch)
    for bad in ('', '   ', 'x' * 20001):
        result = edit_tools.edit_memory.func(
            memory_id='m1', content=bad, config={'configurable': {'user_id': OWNER}}
        )
        assert result == 'Error: memory content must contain 1 to 20000 characters.'


def test_edit_memory_none_configurable_raises_permission_error():
    with pytest.raises(PermissionError):
        edit_tools.edit_memory.func(memory_id='m1', content='ok', config={'configurable': None})


def test_delete_memory_none_configurable_raises_permission_error():
    with pytest.raises(PermissionError):
        edit_tools.delete_memory.func(memory_id='m1', config={'configurable': None})


def test_delete_memory_accepts_top_level_user_id(monkeypatch):
    """Owner resolution must succeed before the store is consulted."""
    seen = {}

    class _Store:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(edit_tools, 'get_data_plane_firestore_client', lambda: _Store())
    monkeypatch.setattr(
        edit_tools,
        'read_canonical_memory_item',
        lambda uid, memory_id, db_client=None: seen.update(uid=uid, memory_id=memory_id) or None,
    )
    result = edit_tools.delete_memory.func(
        memory_id='m1', config={'configurable': None, 'user_id': OWNER}
    )
    assert result == 'Error: memory not found.'
    assert seen == {'uid': OWNER, 'memory_id': 'm1'}


def test_tools_tolerate_none_configurable_through_langchain_invoke(monkeypatch):
    """End-to-end through ``invoke``: a ``None`` configurable is not a crash."""
    _stub_ref(monkeypatch)
    result = edit_tools.update_conversation.invoke(
        {'conversation_id': 'c1', 'correction': '', 'title': 'Corrected'},
        config={'configurable': None, 'user_id': OWNER},
    )
    assert _error_code(result) == 'invalid_correction'
