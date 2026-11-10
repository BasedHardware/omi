"""Owning writes retire indexed debt atomically when they durably refuse repair."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.support.lifecycle_state_table import FIELD_BUILDERS, SUMMARY_REFUSAL_WRITERS, Writer
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import summary_delivery as delivery


@pytest.fixture(scope='module')
def owners():
    from database import chat_edits, conversation_mutations, conversations
    from utils.retrieval.tools import edit_tools
    from utils.sync import assignment

    return SimpleNamespace(
        chat_edits=chat_edits,
        mutations=conversation_mutations,
        conversations=conversations,
        tools=edit_tools,
        assignment=assignment,
    )


def debt():
    return dict(
        status='completed',
        summary_title_provenance='server_minimum',
        summary_due_at=220,
        summary_first_pending_at=100,
        structured={'title': 'Minimum'},
    )


def assert_retired(row, patch):
    assert delivery.refusal(row) is None
    assert patch['summary_due_at'] is None
    after = {**row, **patch}
    assert delivery.refusal(after) is not None
    assert after['summary_first_pending_at'] == row['summary_first_pending_at']


@pytest.mark.parametrize('writer', SUMMARY_REFUSAL_WRITERS, ids=lambda writer: f'{writer.module}:{writer.function}')
def test_every_refusal_owner_is_in_reviewed_due_inventory(writer):
    assert writer.function in FIELD_BUILDERS[writer.module]['summary_due_at']


def test_donor_tombstone_retires_debt_in_redirect_payload(owners):
    row = debt()
    patch = owners.assignment._donor_redirect_patch(row, 'survivor')
    assert patch['deleted'] and patch['discarded']
    assert_retired(row, patch)


@pytest.mark.parametrize('title', ['', 'Manual title'])
def test_title_endpoint_retires_debt_without_an_extra_read(owners, monkeypatch, title):
    row = debt()
    ref = Mock()
    ref.get.return_value = SimpleNamespace(exists=True)
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = ref
    monkeypatch.setattr(owners.conversations, 'db', client)
    monkeypatch.setattr(owners.conversations, '_sync_conversation_search_index', lambda *args: None)
    owners.conversations.update_conversation_title.__wrapped__('synthetic', 'target', title)
    ref.get.assert_called_once_with()
    assert_retired(row, ref.update.call_args.args[0])


@pytest.mark.parametrize('title', ['', 'Manual title'])
def test_offline_title_retires_debt_in_same_patch(owners, title):
    row = debt()
    projected, patch = owners.mutations._apply_operation(row, {'type': 'set_title', 'title': title})
    assert_retired(row, patch)
    assert projected['summary_due_at'] is None


@pytest.mark.parametrize('field', ['user_title', 'user_overview'])
@pytest.mark.parametrize('restore', [False, True])
def test_chat_transaction_retires_debt_even_for_empty_manual_value(owners, field, restore):
    store = StrictFirestore()
    path = ('users', 'synthetic', 'conversations', 'target')
    row = debt()
    store.rows[path] = deepcopy(row)
    before = {'structured': row['structured']}
    if restore:
        owners.chat_edits.restore(
            'synthetic', 'conversation', 'target', before, {**before, field: ''}, firestore_client=store
        )
    else:
        owners.chat_edits.apply_update(
            'synthetic', 'conversation', 'target', before, {field: ''}, firestore_client=store
        )
    assert_retired(row, store.rows[path])


def test_correction_note_without_manual_fields_keeps_debt(owners):
    store = StrictFirestore()
    path = ('users', 'synthetic', 'conversations', 'target')
    store.rows[path] = row = debt()
    owners.chat_edits.apply_update(
        'synthetic',
        'conversation',
        'target',
        {'structured': row['structured']},
        {'user_corrections': []},
        firestore_client=store,
    )
    assert store.rows[path]['summary_due_at'] == 220


@pytest.mark.parametrize('field', ['title', 'overview'])
def test_tool_clears_due_in_manual_patch(owners, monkeypatch, field):
    row = debt()
    writes = []
    monkeypatch.setattr(owners.tools.conversations, 'get_conversation', lambda *args: row)
    monkeypatch.setattr(owners.tools.chat_edits, 'snapshot', lambda *args: {'structured': row['structured']})
    monkeypatch.setattr(
        owners.tools.conversations,
        'update_conversation_chat',
        lambda uid, cid, before, patch: writes.append(patch) or patch,
    )
    monkeypatch.setattr(owners.tools, 'record_write', lambda *args: None)
    owners.tools.update_conversation.func(
        'target', 'Confirmed correction', **{field: 'Edited'}, config={'configurable': {'user_id': 'synthetic'}}
    )
    assert_retired(row, writes[0])


@pytest.mark.parametrize('rich,discarded', [(False, False), (True, False), (False, True)])
def test_already_enriched_return_retires_legacy_due(owners, rich, discarded):
    row = {**debt(), 'summary_completed_at': 150, 'summary_output_present': True, 'structured': {'overview': 'Banked'}}
    write = {'status': 'completed', 'summary_output_present': rich, 'discarded': discarded}
    assert delivery.merge_result(row, write, 'synthetic') is None
    assert write['summary_due_at'] is None
    assert write['summary_completed_at'] == 150


@pytest.mark.parametrize('field', ['user_title', 'user_overview'])
def test_manual_chat_write_survives_real_codec_without_reenrolling_debt(owners, monkeypatch, field):
    store = StrictFirestore()
    path = ('users', 'synthetic', 'conversations', 'target')
    row = debt()
    row['structured'].update(title_provenance='server_minimum', overview='')
    row['data_protection_level'] = 'standard'
    # Explicit nulls exercise the real snapshot comparison without asking this
    # strict transaction fake to model Firestore DELETE_FIELD transforms.
    row.update(user_title=None, user_overview=None, user_corrections=[], user_corrections_compressed=False)
    store.rows[path] = deepcopy(row)
    monkeypatch.setattr(owners.conversations, 'get_conversation_raw_snapshot', lambda *args: deepcopy(row))
    monkeypatch.setattr(owners.chat_edits, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(owners.conversations, 'refresh_conversation_after_chat_edit', lambda *args: None)
    expected = {key: row[key] for key in owners.chat_edits.FIELDS['conversation']}
    result = owners.conversations.update_conversation_chat(
        'synthetic', 'target', expected, {field: 'Edited', 'structured': row['structured'], 'summary_due_at': None}
    )
    assert result[field] == 'Edited'
    assert 'summary_due_at' not in result
    assert_retired(row, store.rows[path])
    assert 'summary_output_present' not in store.rows[path]
    owners.chat_edits.restore('synthetic', 'conversation', 'target', result, expected, firestore_client=store)
    assert owners.chat_edits.snapshot('synthetic', 'conversation', 'target', firestore_client=store) == expected


def test_table_and_behavior_cases_cover_same_owners():
    assert set(SUMMARY_REFUSAL_WRITERS) == {
        Writer('utils/sync/assignment.py', '_donor_redirect_patch'),
        Writer('database/conversations.py', 'update_conversation_title'),
        Writer('database/conversation_mutations.py', '_apply_operation'),
        Writer('database/chat_edits.py', 'apply_update.apply'),
        Writer('database/chat_edits.py', 'restore.apply'),
        Writer('utils/retrieval/tools/edit_tools.py', 'update_conversation'),
        Writer('utils/conversations/summary_delivery.py', 'merge_result'),
    }
