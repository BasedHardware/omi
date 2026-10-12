"""Shared edit tools retain domain authority, scope and exact inverse snapshots."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from utils.retrieval.tools import edit_tools
from utils.retrieval.tools import action_item_tools
from utils.messaging import undo
from utils.conversations.meeting_notes_wiring import confirmed_corrections_context
from database import chat_edits

CONFIG = {'configurable': {'user_id': 'owner', 'chat_session_id': 'session'}}


@pytest.fixture
def receipts(monkeypatch):
    calls = []
    monkeypatch.setattr(edit_tools, 'record_write', lambda *args: calls.append(args))
    monkeypatch.setattr(action_item_tools, 'record_write', lambda *args: calls.append(args) or '')
    return calls


def test_conversation_correction_keeps_transcript_and_durable_note(monkeypatch, receipts):
    row = {'structured': {'title': 'Old', 'overview': 'Old overview'}, 'transcript_segments': [{'text': 'Original'}]}
    writes = []
    monkeypatch.setattr(
        edit_tools.conversations, 'get_conversation', lambda uid, target: row if uid == 'owner' else None
    )
    monkeypatch.setattr(edit_tools.chat_edits, 'snapshot', lambda *args: dict(structured=row['structured']))
    monkeypatch.setattr(
        edit_tools.conversations,
        'update_conversation_chat',
        lambda uid, target, before, patch: writes.append(patch) or {'structured': patch['structured']},
    )
    assert 'config' not in edit_tools.update_conversation.tool_call_schema.model_fields
    result = edit_tools.update_conversation.invoke(
        {
            'conversation_id': 'conversation',
            'correction': 'User confirmed the film was The Substance',
            'title': 'The Substance movie night',
        },
        config=CONFIG,
    )
    assert result == 'Title → The Substance movie night'
    assert 'transcript_segments' not in writes[0]
    assert writes[0]['user_corrections'][0]['note'].endswith('The Substance')
    assert writes[0]['structured']['overview'] == 'Old overview'
    assert receipts[0][1:3] == ('conversation', 'conversation')
    context = confirmed_corrections_context(SimpleNamespace(user_corrections=writes[0]['user_corrections']))
    assert 'The Substance' in context


def test_rename_reuses_mcp_with_exact_alias_snapshot(monkeypatch, receipts):
    calls = []
    monkeypatch.setattr(edit_tools.users, 'get_person', lambda uid, target: {'name': 'Old'})
    snapshots = iter([{'name': 'Old', 'aliases': ['Alias']}, {'name': 'New', 'aliases': ['Alias', 'Old']}])
    monkeypatch.setattr(edit_tools.chat_edits, 'snapshot', lambda *args: next(snapshots))
    monkeypatch.setattr(
        edit_tools.mcp_people,
        'rename_person',
        lambda uid, args, **kwargs: calls.append((uid, args))
        or kwargs['expected_chat_state'].update(after={'name': 'New', 'aliases': ['Alias', 'Old']})
        or {'person': {'name': 'New'}},
    )
    assert edit_tools.rename_person.func('person', 'New', config=CONFIG) == 'Name → New'
    assert calls == [('owner', {'person_id': 'person', 'name': 'New'})]
    assert receipts[0][3]['_snapshot']['aliases'] == ['Alias']


@pytest.mark.parametrize(
    'name,args', [('update_conversation', ('foreign', 'Confirmed', 'Title')), ('rename_person', ('foreign', 'New'))]
)
def test_foreign_target_never_mutates(monkeypatch, receipts, name, args):
    seen = []
    monkeypatch.setattr(edit_tools.conversations, 'get_conversation', lambda uid, target: seen.append(uid) or None)
    monkeypatch.setattr(edit_tools.users, 'get_person', lambda uid, target: seen.append(uid) or None)
    assert 'not found' in getattr(edit_tools, name).func(*args, config=CONFIG)
    assert seen == ['owner']
    assert not receipts


@pytest.mark.parametrize('verb', ['edit_memory', 'delete_memory'])
def test_memory_tools_scope_to_owner_and_use_service(monkeypatch, receipts, verb):
    reads, writes = [], []
    before = SimpleNamespace(
        uid='owner', promotion={}, model_dump=lambda **kwargs: {'memory_id': 'memory', 'content': 'Old'}
    )
    after = SimpleNamespace(content='New', model_dump=lambda **kwargs: {'memory_id': 'memory', 'content': 'New'})
    monkeypatch.setattr(edit_tools, 'get_data_plane_firestore_client', lambda: 'db')
    monkeypatch.setattr(
        edit_tools,
        'read_canonical_memory_item',
        lambda uid, target, **kwargs: reads.append((uid, target)) or (before if len(reads) == 1 else after),
    )

    class Service:
        def __init__(self, **kwargs):
            assert kwargs == {'db_client': 'db'}

        def update_external_memory_content(self, uid, target, content, **kwargs):
            writes.append((uid, target, content))
            return SimpleNamespace(id='memory')

        def remove_chat_memory(self, uid, target):
            writes.append((uid, target))
            return after

    monkeypatch.setattr(edit_tools, 'MemoryService', Service)
    tool = getattr(edit_tools, verb)
    result = tool.func('memory', 'New', config=CONFIG) if verb == 'edit_memory' else tool.func('memory', config=CONFIG)
    assert result.startswith('Memory')
    assert all(uid == 'owner' for uid, _ in reads)
    assert writes[0][0] == 'owner'
    assert receipts[0][1] == ('memory_edit' if verb == 'edit_memory' else 'memory_deleted')


@pytest.mark.parametrize('verb', ['edit_memory', 'delete_memory'])
def test_foreign_memory_never_writes(monkeypatch, receipts, verb):
    monkeypatch.setattr(edit_tools, 'get_data_plane_firestore_client', lambda: 'db')
    monkeypatch.setattr(edit_tools, 'read_canonical_memory_item', lambda uid, target, **kwargs: None)
    tool = getattr(edit_tools, verb)
    result = (
        tool.func('foreign', 'New', config=CONFIG) if verb == 'edit_memory' else tool.func('foreign', config=CONFIG)
    )
    assert 'not found' in result and not receipts


@pytest.mark.parametrize(
    'patch,action',
    [
        ({'completed': True}, 'completed'),
        ({'completed': False}, 'uncompleted'),
        ({'delete': True}, 'deleted'),
        ({'clear_due_date': True}, 'updated'),
        ({'due_at': '2099-10-11T12:00:00+07:00'}, 'updated'),
    ],
)
def test_task_mutations_and_receipt_actions(monkeypatch, receipts, patch, action):
    row = {'id': 'task', 'description': 'Task', 'completed': action == 'uncompleted', 'due_at': None}
    previous = dict(row)
    snapshots = []
    monkeypatch.setattr(action_item_tools.action_items_db, 'get_action_item', lambda *args: dict(row))
    monkeypatch.setattr(
        action_item_tools.action_items_db,
        'update_action_item',
        lambda uid, target, values, **kwargs: row.update(values)
        or kwargs['expected_chat_state'].update(after=chat_edits.encode(dict(row)))
        or True,
    )
    monkeypatch.setattr(chat_edits, 'snapshot', lambda *args: chat_edits.encode(dict(row)))
    monkeypatch.setattr(action_item_tools, 'send_action_item_completed_notification', lambda *args: None)
    monkeypatch.setattr(action_item_tools, 'sync_action_item_reminder', lambda *args, **kwargs: None)
    result = action_item_tools.update_action_item_tool.func('task', config=CONFIG, **patch)
    assert 'Successfully updated' in result
    receipt = undo.action_receipt('a' * 32, *receipts[0][1:])
    assert receipt.content_block['type'] == 'editReceipt'
    assert receipt.content_block['action'] == action
    assert receipts[0][3]['_snapshot']['completed'] == previous['completed']


@pytest.mark.parametrize('kind', ['conversation', 'person', 'task'])
def test_inverse_uses_exact_snapshot_not_reconstruction(monkeypatch, kind):
    calls = []
    monkeypatch.setattr(chat_edits, 'restore', lambda *args: calls.append(args))
    from database import conversations, action_items
    from utils import notifications

    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *args: None)
    monkeypatch.setattr(conversations, 'refresh_conversation_after_chat_edit', lambda *args: None)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda *args: None)
    monkeypatch.setattr(action_items, 'get_action_item', lambda *args: {})
    monkeypatch.setattr(notifications, 'sync_action_item_reminder', lambda *args, **kwargs: None)
    previous, expected = {'field': 'before'}, {'field': 'after'}
    undo.apply_inverse(
        'owner',
        dict(
            kind=kind,
            object_id='target',
            before=edit_tools.envelope(previous, 'Before'),
            after=edit_tools.envelope(expected, 'After'),
        ),
    )
    assert calls == [('owner', kind, 'target', expected, previous)]


def test_snapshot_codec_preserves_timestamps_and_bytes():
    row = {'updated_at': datetime.now(timezone.utc), 'encoded': b'\x00\xff', 'values': [None, {'flag': False}]}
    assert chat_edits.decode(chat_edits.encode(row)) == row


def test_shared_catalog_identical_tools_and_guardrail():
    from utils.retrieval.agentic import CORE_TOOLS
    from utils.retrieval.chat_mount import chat_mount, EDIT_GUARDRAIL

    names = {tool.name for tool in CORE_TOOLS}
    assert {'update_conversation', 'rename_person', 'edit_memory', 'delete_memory', 'update_action_item_tool'} <= names
    assert EDIT_GUARDRAIL in chat_mount([]).skills


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_durable_correction_notes_roundtrip_with_conversation_protection(level):
    notes = [{'note': 'User confirmed the film was The Substance', 'at': '2026-10-11T00:00:00+00:00'}]
    encoded = edit_tools.conversations.encode_conversation_for_write('owner', {'user_corrections': notes}, level)
    assert encoded['user_corrections_compressed'] is True
    assert not isinstance(encoded['user_corrections'], list)
    assert 'The Substance' not in str(encoded['user_corrections'])
    decoded = edit_tools.conversations.prepare_conversation_for_read(encoded, 'owner')
    assert decoded['user_corrections'] == notes


def test_conversation_patch_uses_the_snapshot_version(monkeypatch, receipts):
    monkeypatch.setattr(
        edit_tools.conversations,
        'get_conversation',
        lambda *args: {'structured': {'title': 'Old', 'overview': 'Stale'}},
    )
    fresh = {
        'structured': {'title': 'Old', 'overview': 'Concurrent summary'},
        'user_corrections': [{'note': 'Already confirmed'}],
    }
    monkeypatch.setattr(chat_edits, 'snapshot', lambda *args: fresh)
    writes = []
    monkeypatch.setattr(
        edit_tools.conversations,
        'update_conversation_chat',
        lambda uid, target, before, patch: writes.append((before, patch)) or patch,
    )
    edit_tools.update_conversation.func('target', 'User confirmed new title', 'New', config=CONFIG)
    assert writes[0][0] == fresh
    assert writes[0][1]['structured']['overview'] == 'Concurrent summary'
    assert writes[0][1]['user_corrections'][0]['note'] == 'Already confirmed'


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_repeated_correction_preserves_prior_protected_notes(monkeypatch, receipts, level):
    notes = [{'note': 'Earlier confirmed correction', 'at': '2026-10-11T00:00:00+00:00'}]
    raw = edit_tools.conversations.encode_conversation_for_write(
        'owner', {'structured': {'title': 'Old'}, 'user_corrections': notes}, level
    )
    monkeypatch.setattr(edit_tools.conversations, 'get_conversation', lambda *args: {'structured': {'title': 'Old'}})
    monkeypatch.setattr(chat_edits, 'snapshot', lambda *args: chat_edits.encode(raw))
    writes = []
    monkeypatch.setattr(
        edit_tools.conversations,
        'update_conversation_chat',
        lambda uid, target, before, patch: writes.append(patch) or patch,
    )
    edit_tools.update_conversation.func('target', 'New confirmed correction', 'New', config=CONFIG)
    assert writes[0]['user_corrections'][0] == notes[0]
    assert writes[0]['user_corrections'][1]['note'] == 'New confirmed correction'
