from datetime import datetime, timezone

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.person_evidence_backfill import backfill_person, receipt_conversations_by_person

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
PATH = ('users', 'u', 'people', 'p1')


def test_receipts_map_people_to_their_conversations():
    rows = [
        ('c1', {'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p1'}, '2': {'is_user': True}}}}),
        ('c2', {'manual_speaker_assignments': {'segments': {'a': {'person_id': 'p1'}, 'b': {'person_id': 'p2'}}}}),
        ('c3', {'deleted': True, 'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p1'}}}}),
        ('c4', {}),
    ]
    assert receipt_conversations_by_person(rows, lambda data: data['manual_speaker_assignments']) == {
        'p1': ['c1', 'c2'],
        'p2': ['c2'],
    }


def test_backfill_dry_run_writes_nothing_and_apply_is_idempotent():
    store = StrictFirestore()
    store.rows[PATH] = {
        'id': 'p1',
        'name': 'Maya',
        'label_evidence': {'counted': ['manual_labels:c1'], 'manual_labels': 1},
    }
    for cid in ('c1', 'c2'):
        store.rows[('users', 'u', 'conversations', cid)] = {
            'manual_speaker_assignments': {'generation': 1, 'speakers': {'1': {'person_id': 'p1', 'generation': 1}}},
            'transcript_segments': [{'id': 's1', 'speaker_id': 1, 'person_id': 'p1', 'is_user': False}],
        }
    preview = backfill_person(store, 'u', 'p1', ['c1', 'c2'], NOW, apply=False)
    assert preview['manual_labels'] == 2
    assert store.rows[PATH]['label_evidence']['manual_labels'] == 1
    applied = backfill_person(store, 'u', 'p1', ['c1', 'c2'], NOW, apply=True)
    assert applied['manual_labels'] == 2 and store.rows[PATH]['label_evidence']['manual_labels'] == 2
    assert backfill_person(store, 'u', 'p1', ['c1', 'c2'], NOW, apply=True) is None
    assert backfill_person(store, 'u', 'missing', ['c1'], NOW, apply=True) is None


def test_backfill_rechecks_relabels_and_scopes_every_read_to_uid():
    store = StrictFirestore()
    store.rows[PATH] = {'id': 'p1', 'name': 'Maya'}
    store.rows[('users', 'other', 'conversations', 'foreign')] = {
        'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p1'}}}
    }
    store.rows[('users', 'u', 'conversations', 'relabeled')] = {
        'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p2'}}},
        'transcript_segments': [{'id': 's1', 'speaker_id': 1, 'person_id': 'p2'}],
    }
    assert backfill_person(store, 'u', 'p1', ['foreign', 'relabeled'], NOW, apply=True) is None
    assert 'label_evidence' not in store.rows[PATH]


def test_live_card_evidence_is_not_counted_again_by_backfill(monkeypatch):
    from database import conversations as db

    store = StrictFirestore()
    store.rows[PATH] = {'id': 'p1', 'name': 'Maya'}
    store.rows[('users', 'u', 'conversations', 'c1')] = {
        'transcript_segments': [{'id': 's1', 'speaker_id': 1, 'person_id': None, 'is_user': False}]
    }
    db.assign_conversation_speaker(
        'u', 'c1', person_id='p1', speaker_id=1, evidence_source='card', firestore_client=store
    )
    assert backfill_person(store, 'u', 'p1', ['c1'], NOW, apply=True) is None
    assert store.rows[PATH]['label_evidence']['card_picks'] == 1
    assert store.rows[PATH]['label_evidence'].get('manual_labels', 0) == 0


def test_script_pagination_uses_a_valid_firestore_cursor(monkeypatch):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud.firestore import Client, Query
    from types import SimpleNamespace
    from scripts import backfill_person_label_evidence as script

    client = Client(project='synthetic-test', credentials=AnonymousCredentials())
    calls = []

    def stream(query):
        wire = query._to_protobuf()  # Validate the real SDK cursor without performing RPCs.
        calls.append(wire)
        if len(calls) == 1:
            return iter([SimpleNamespace(id='c2', to_dict=lambda: {})])
        return iter([])

    monkeypatch.setattr(Query, 'stream', stream)
    assert list(script._pages(client, 'u', 'c1')) == [[('c2', {})]]
    assert len(calls) == 2
    assert calls[0].start_at.values[0].reference_value.endswith('/users/u/conversations/c1')
    assert calls[1].start_at.values[0].reference_value.endswith('/users/u/conversations/c2')


def test_script_is_dry_run_by_default_and_does_not_advance_checkpoint(monkeypatch, tmp_path):
    from scripts import backfill_person_label_evidence as script

    store = StrictFirestore()
    store.rows[PATH] = {'id': 'p1', 'name': 'Maya'}
    store.rows[('users', 'u', 'conversations', 'c1')] = {
        'manual_speaker_assignments': {'generation': 1, 'speakers': {'1': {'person_id': 'p1', 'generation': 1}}},
        'transcript_segments': [{'id': 's1', 'speaker_id': 1}],
    }
    checkpoint = tmp_path / 'checkpoint'
    monkeypatch.setattr(script, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(script, '_pages', lambda *args: [[('c1', store.rows[('users', 'u', 'conversations', 'c1')])]])
    assert script.main(['--uid', 'u', '--checkpoint', str(checkpoint)]) == 0
    assert 'label_evidence' not in store.rows[PATH]
    assert not checkpoint.exists()
    assert script.main(['--uid', 'u', '--checkpoint', str(checkpoint), '--apply']) == 0
    assert store.rows[PATH]['label_evidence']['manual_labels'] == 1
    assert checkpoint.read_text() == 'c1'
