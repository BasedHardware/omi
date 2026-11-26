"""Native visibility receipts are written atomically with usable notes."""

from datetime import timedelta

import pytest

from database import conversations as db, conversations_v3_leases as leases, conversations_v3_processing as writers
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
    if not overview:
        derived.update(
            structured={'overview': 'Previous notes'},
            summary_covers_through=END,
            v3_notes_written=True,
            v3_native_manual_notes_visibility=policy.native_manual_notes_receipt(derived),
        )
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
    saved = strict.rows[path]
    assert (saved.get(policy.NATIVE_MANUAL_NOTES_VISIBILITY) is not None) == bool(overview)
    if not overview:
        assert not saved['v3_notes_written'] and saved['summary_covers_through'] is None


@pytest.mark.parametrize('overview', ['Actual notes', ''])
def test_background_notes_stamp_visibility_before_worker_settle(strict, monkeypatch, overview):
    source, derived = rows()
    path = ('users', UID, 'conversations', derived['id'])
    strict.rows[RAW] = source
    if not overview:
        derived.update(
            structured={'overview': 'Previous notes'},
            summary_covers_through=END,
            v3_notes_written=True,
            v3_native_manual_notes_visibility=policy.native_manual_notes_receipt(derived),
        )
    strict.rows[path] = derived
    monkeypatch.setattr(db, 'db', strict)
    monkeypatch.setattr(db.pipeline_ledger, 'record_summary', lambda *args, **kwargs: None)
    monkeypatch.setattr(db.terminal_settled, 'serving', lambda uid: True)
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
    saved = strict.rows[path]
    assert not saved.get('v3_notes_written')
    key = policy.NATIVE_MANUAL_NOTES_VISIBILITY
    assert saved['structured']['overview'] == overview
    assert saved.get(key) == (policy.native_manual_notes_receipt(derived) if overview else None)
    if not overview:
        assert saved['summary_covers_through'] is None
        source['record_upload_revision'] += 1
        (natural_window,) = planner.windows([group([line('r', 0, 15)], native=False)], [[entry(1)]])
        projected = planner.build(UID, natural_window, {'r': source}, saved)
        assert projected['home_hidden_reason'] == 'below_word_minimum'
