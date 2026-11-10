"""Owning writes retire indexed debt atomically when they durably refuse repair."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import FirstSummaryPolicy
from tests.support.lifecycle_state_table import (
    FIELD_BUILDERS,
    SUMMARY_MANUAL_CLEAR_WRITERS,
    SUMMARY_REFUSAL_WRITERS,
    Writer,
)
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


@pytest.mark.parametrize('writer', SUMMARY_MANUAL_CLEAR_WRITERS)
def test_every_manual_clear_owner_is_in_reviewed_due_inventory(writer):
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
@pytest.mark.parametrize('completed', [None, 150])
def test_already_enriched_return_retires_legacy_due(owners, rich, discarded, completed):
    row = {**debt(), 'summary_output_present': True, 'structured': {'overview': 'Banked'}}
    if completed is not None:
        row['summary_completed_at'] = completed
    write = {'status': 'completed', 'summary_output_present': rich, 'discarded': discarded}
    assert delivery.merge_result(row, write, 'synthetic') is None
    assert write['summary_due_at'] is None
    assert write.get('summary_completed_at') == completed
    if not rich and not discarded:
        assert write['structured']['overview'] == 'Banked'
        assert write['summary_output_present'] is True


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
    assert delivery.refusal(store.rows[path]) is None
    assert store.rows[path]['summary_due_at'] == 100 + delivery.deadline_seconds()


@pytest.mark.parametrize('field', ['user_title', 'user_overview'])
@pytest.mark.parametrize('restore', [False, True])
@pytest.mark.parametrize('existing_due', [None, 0, 211])
def test_manual_field_removal_rearms_original_deadline_without_moving_due(
    owners, monkeypatch, field, restore, existing_due
):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', '120')
    store = StrictFirestore()
    path = ('users', 'synthetic', 'conversations', 'target')
    row = {
        **debt(),
        **{key: None for key in owners.chat_edits.FIELDS['conversation'] if key != 'structured'},
        field: 'Manual',
        'summary_due_at': existing_due,
        'first_summary_policy': FirstSummaryPolicy(first_summary_deadline_seconds=60).to_dict(),
    }
    store.rows[path] = deepcopy(row)
    before = owners.chat_edits.snapshot('synthetic', 'conversation', 'target', firestore_client=store)
    if restore:
        owners.chat_edits.restore(
            'synthetic', 'conversation', 'target', before, {**before, field: None}, firestore_client=store
        )
    else:
        owners.chat_edits.apply_update(
            'synthetic', 'conversation', 'target', before, {field: None, 'summary_due_at': None}, firestore_client=store
        )
    after = store.rows[path]
    assert delivery.refusal(after) is None
    assert after['summary_due_at'] == (160 if existing_due is None else existing_due)
    assert after['summary_first_pending_at'] == 100


@pytest.mark.parametrize('restore', [False, True])
@pytest.mark.parametrize(
    'refusal_fields',
    [
        {'deleted': True},
        {'discarded': True},
        {'status': 'processing'},
        {'deferred': True},
        {'user_overview': ''},
        {'summary_completed_at': 150},
        {'summary_output_present': True},
        {'summary_title_provenance': 'generated'},
        {'data_protection_level': 'private'},
        {
            'structured': {'title_provenance': 'server_minimum'},
            'relevance_decision': {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'content_below_floor'},
        },
        {'summary_blocked_reason': delivery.EMPTY_BLOCKED_REASON},
        {'summary_blocked_reason': delivery.EMPTY_LIFETIME_BLOCKED_REASON},
        {'finalization_job_id': 'owned'},
        {'finalization_status': 'blocked_byok'},
    ],
)
def test_manual_field_removal_does_not_rearm_refused_row(owners, restore, refusal_fields):
    store = StrictFirestore()
    path = ('users', 'synthetic', 'conversations', 'target')
    row = {
        **debt(),
        **{key: None for key in owners.chat_edits.FIELDS['conversation'] if key != 'structured'},
        'user_title': 'Manual',
        'summary_due_at': None,
        **refusal_fields,
    }
    store.rows[path] = deepcopy(row)
    before = owners.chat_edits.snapshot('synthetic', 'conversation', 'target', firestore_client=store)
    if restore:
        owners.chat_edits.restore(
            'synthetic', 'conversation', 'target', before, {**before, 'user_title': None}, firestore_client=store
        )
    elif row.get('deleted') or row.get('is_locked'):
        with pytest.raises(PermissionError):
            owners.chat_edits.apply_update(
                'synthetic', 'conversation', 'target', before, {'user_title': None}, firestore_client=store
            )
    else:
        owners.chat_edits.apply_update(
            'synthetic', 'conversation', 'target', before, {'user_title': None}, firestore_client=store
        )
    assert delivery.refusal(store.rows[path]) is not None
    assert store.rows[path]['summary_due_at'] is None


@pytest.mark.parametrize('accepted', [None, True, float('nan'), float('inf'), '100'])
def test_manual_clear_cannot_invent_an_unknown_acceptance(accepted):
    row = {**debt(), 'summary_due_at': None, 'summary_first_pending_at': accepted}
    assert delivery.rearm_after_refusal_clear(row, row) is None


def test_manual_clear_uses_current_deadline_only_without_snapshot(monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', '90')
    row = {**debt(), 'summary_due_at': None}
    assert delivery.rearm_after_refusal_clear(row, row) == 190


@pytest.mark.parametrize('field', ['title', 'overview'])
def test_chat_tools_reject_empty_manual_removal(owners, monkeypatch, field):
    read = Mock(side_effect=AssertionError('Blank edits must fail before any read or write'))
    monkeypatch.setattr(owners.tools.conversations, 'get_conversation', read)
    result = owners.tools.update_conversation.func(
        'target', 'Confirmed correction', **{field: '  '}, config={'configurable': {'user_id': 'synthetic'}}
    )
    assert f'invalid_{field}' in result
    read.assert_not_called()


def test_sync_discard_restore_preserves_manual_fields_and_refusal(owners, monkeypatch):
    row = {**debt(), 'discarded': True, 'user_title': 'Manual', 'user_overview': 'Manual', 'summary_due_at': None}
    path = ('users', 'synthetic', 'conversations', 'target')
    client = StrictFirestore({path: row})
    monkeypatch.setattr(owners.conversations, 'db', client)
    monkeypatch.setattr(owners.conversations, 'invalidate_people_stats_cache', lambda *args: None)
    monkeypatch.setattr(owners.conversations, '_sync_conversation_search_index', lambda *args: None)
    result = owners.conversations.restore_conversation_from_discarded('synthetic', 'target', return_snapshot=True)
    patch = client.transactions[-1].updates[-1][1]
    assert not {'user_title', 'user_overview', 'summary_due_at'}.intersection(patch)
    assert result['user_title'] == result['user_overview'] == 'Manual'
    assert delivery.refusal(result) == 'manual'
    assert result['summary_due_at'] is None


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


@pytest.mark.parametrize(
    'owner',
    [{'summary_blocked_reason': 'blocked_byok'}, {'finalization_status': 'queued'}, {'finalization_status': 'leased'}],
)
def test_refusal_clear_does_not_compete_with_transient_owner(owner):
    row = {**debt(), 'summary_due_at': None, **owner}
    assert delivery.rearm_after_refusal_clear(row, row) is None


def test_unchanged_offline_title_does_not_issue_a_write(owners):
    row = {**debt(), 'user_title': 'Minimum'}
    projected, patch = owners.mutations._apply_operation(row, {'type': 'set_title', 'title': 'Minimum'})
    assert patch == {}
    assert projected['summary_due_at'] == row['summary_due_at']
