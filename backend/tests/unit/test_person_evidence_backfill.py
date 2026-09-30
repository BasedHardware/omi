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
    preview = backfill_person(store, 'u', 'p1', ['c1', 'c2'], NOW, apply=False)
    assert preview['manual_labels'] == 2
    assert store.rows[PATH]['label_evidence']['manual_labels'] == 1
    applied = backfill_person(store, 'u', 'p1', ['c1', 'c2'], NOW, apply=True)
    assert applied['manual_labels'] == 2 and store.rows[PATH]['label_evidence']['manual_labels'] == 2
    assert backfill_person(store, 'u', 'p1', ['c1', 'c2'], NOW, apply=True) is None
    assert backfill_person(store, 'u', 'missing', ['c1'], NOW, apply=True) is None
