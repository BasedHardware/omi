"""Native visibility receipts are written atomically with usable notes."""

from datetime import timedelta

import pytest

from database import conversations as db, conversations_v3_leases as leases, conversations_v3_processing as writers
from tests.unit.test_conversation_lifecycle_contract import lifecycle_store  # noqa: F401
from tests.unit.test_conversations_v3_native_manual_planner import NOW, entry, group, line, recording
from tests.unit.test_conversations_v3_transactions import strict  # noqa: F401
from utils.conversations import lifecycle
from utils.conversations.v3 import planner, policy

UID = 'synthetic'
RAW = ('users', UID, 'conversations', 'r')
END = NOW + timedelta(seconds=15)


def rows():
    source = recording('r', 0, 15)
    (window,) = planner.windows([group([line('r', 0, 15)])], [[entry(1)]])
    derived = planner.build(UID, window, {'r': source})
    assert policy.native_manual_notes_receipt(derived)
    return source, derived


@pytest.mark.parametrize('overview', ['Actual notes', ''])
def test_on_open_notes_stamp_visibility_only_with_a_body(strict, overview):
    source, derived = rows()
    strict.rows[RAW] = source
    path = ('users', UID, 'conversations', derived['id'])
    strict.rows[path] = derived
    token = leases.acquire(UID, 'summary-' + derived['id'], firestore_client=strict)
    writers.store_summary(
        UID,
        derived['id'],
        token,
        1,
        {'title': 'Title', 'overview': overview},
        END,
        firestore_client=strict,
    )
    assert (strict.rows[path].get(policy.NATIVE_MANUAL_NOTES_VISIBILITY) is not None) == bool(overview)


@pytest.mark.parametrize('overview', ['Actual notes', ''])
@pytest.mark.parametrize('terminal_family', [False, True])
def test_background_notes_stamp_visibility_before_worker_settle(
    lifecycle_store, monkeypatch, overview, terminal_family
):
    source, derived = rows()
    lifecycle_store.put_conversation(UID, 'r', **source)
    lifecycle_store.put_conversation(UID, derived['id'], **derived)
    monkeypatch.setattr(db.pipeline_ledger, 'record_summary', lambda *args, **kwargs: None)
    monkeypatch.setattr(db, '_terminal_family_serving', lambda uid: terminal_family)
    assert lifecycle.persist_processed_conversation(
        UID,
        {
            'id': derived['id'],
            'status': 'completed',
            'sync_content_revision': derived['sync_content_revision'],
            'structured': {'title': 'Title', 'overview': overview},
            'data_protection_level': 'standard',
        },
    )
    saved = lifecycle_store.conversation(UID, derived['id'])
    assert not saved.get('v3_notes_written')
    key = policy.NATIVE_MANUAL_NOTES_VISIBILITY
    # This fake records Firestore field paths verbatim in the update/CAS route.
    if terminal_family and overview:
        assert saved[f'{key}.conversation_id'] == derived['id']
        assert saved[f'{key}.recording_id'] == 'r'
    elif overview:
        assert saved[key] == policy.native_manual_notes_receipt(derived)
    else:
        assert not any(field == key or field.startswith(f'{key}.') for field in saved)
