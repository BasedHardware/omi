"""Group-scoped notes refresh budget and evidence fingerprint ledger."""

from database import capture_group_notes as notes_state
from google.cloud import firestore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'capture-group-notes-state-user'
GROUP_ID = 'group-state-test'
PRIMARY_ID = 'primary'


def conversation_path(cid):
    return ('users', UID, 'conversations', cid)


def test_reservation_deduplicates_evidence_and_caps_refresh_attempts(monkeypatch):
    fake = StrictFirestore()
    monkeypatch.setattr(notes_state, 'get_firestore_client', lambda: fake)
    fake.rows[conversation_path(PRIMARY_ID)] = {
        'id': PRIMARY_ID,
        'status': 'completed',
        'capture_group': {
            'id': GROUP_ID,
            'primary_id': PRIMARY_ID,
            'revision': 4,
        },
    }
    member_fingerprints = {'desktop-1': 'evidence-a'}

    first = notes_state.claim_refresh(
        UID,
        GROUP_ID,
        PRIMARY_ID,
        4,
        member_fingerprints,
        max_refreshes=2,
    )
    assert first is not None
    assert (
        notes_state.claim_refresh(
            UID,
            GROUP_ID,
            PRIMARY_ID,
            4,
            member_fingerprints,
            max_refreshes=2,
        )
        is None
    )  # active reservation

    state_document = notes_state.state_ref(UID, GROUP_ID, firestore_client=fake)

    @firestore.transactional
    def commit(transaction):
        update = notes_state.read_success_write(
            transaction,
            UID,
            GROUP_ID,
            first['id'],
            firestore_client=fake,
        )
        assert update is not None
        document, data = update
        transaction.set(document, data)

    commit(fake.transaction())
    saved = state_document.get().to_dict()
    assert saved['refresh_count'] == 1
    assert saved['seen_evidence_fingerprints'] == ['evidence-a']
    assert saved['member_fingerprints'] == member_fingerprints
    assert saved['in_progress'] is None

    assert (
        notes_state.claim_refresh(
            UID,
            GROUP_ID,
            PRIMARY_ID,
            4,
            member_fingerprints,
            max_refreshes=2,
        )
        is None
    )  # same fingerprint is already summarized

    second = notes_state.claim_refresh(
        UID,
        GROUP_ID,
        PRIMARY_ID,
        4,
        {'desktop-2': 'evidence-b'},
        max_refreshes=2,
    )
    assert second is not None
    assert notes_state.release_refresh(UID, GROUP_ID, second['id'], firestore_client=fake)
    assert (
        notes_state.claim_refresh(
            UID,
            GROUP_ID,
            PRIMARY_ID,
            4,
            {'desktop-3': 'evidence-c'},
            max_refreshes=2,
        )
        is None
    )  # failed attempts consume the hard per-group budget


def test_stale_group_revision_cannot_reserve_a_refresh(monkeypatch):
    fake = StrictFirestore()
    monkeypatch.setattr(notes_state, 'get_firestore_client', lambda: fake)
    fake.rows[conversation_path(PRIMARY_ID)] = {
        'id': PRIMARY_ID,
        'status': 'completed',
        'capture_group': {'id': GROUP_ID, 'primary_id': PRIMARY_ID, 'revision': 5},
    }
    assert (
        notes_state.claim_refresh(
            UID,
            GROUP_ID,
            PRIMARY_ID,
            4,
            {'desktop': 'evidence'},
            max_refreshes=3,
        )
        is None
    )
    assert notes_state.get_state(UID, GROUP_ID, firestore_client=fake) == {}
