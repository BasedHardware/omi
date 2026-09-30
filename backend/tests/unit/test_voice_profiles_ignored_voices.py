from datetime import datetime, timedelta, timezone

from database import voice_profiles as db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
STATE = ('users', 'u', db._STATE_COLLECTION, db._STATE_DOCUMENT)


def test_record_ignored_voice_creates_state_and_keeps_newest_first():
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 1, NOW, firestore_client=store)
    db.record_ignored_voice('u', 'c2', 2, NOW + timedelta(minutes=1), firestore_client=store)
    db.record_ignored_voice('u', 'c1', 1, NOW + timedelta(minutes=2), firestore_client=store)
    state = store.rows[STATE]
    assert [(e['conversation_id'], e['speaker_id']) for e in db.ignored_voices(state)] == [('c1', 1), ('c2', 2)]
    assert db.ignored_voice_keys(state) == {'c1:1', 'c2:2'}


def test_ignored_voices_are_bounded(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(db, 'IGNORED_VOICES_LIMIT', 2)
    for index in range(3):
        db.record_ignored_voice('u', f'c{index}', 0, NOW + timedelta(minutes=index), firestore_client=store)
    assert db.ignored_voice_keys(store.rows[STATE]) == {'c1:0', 'c2:0'}


def test_remove_ignored_voice_forgets_its_answers_only():
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 1, NOW, firestore_client=store)
    store.rows[STATE]['answered'] = {'p1': NOW, 'keep': NOW}
    assert db.remove_ignored_voice('u', 'c1', 1, ['p1'], firestore_client=store) is True
    assert store.rows[STATE]['ignored_voices'] == {} and store.rows[STATE]['answered'] == {'keep': NOW}
    assert db.remove_ignored_voice('u', 'c1', 1, ['p1'], firestore_client=store) is False
