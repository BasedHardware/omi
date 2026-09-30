from datetime import datetime, timedelta, timezone

from database import conversations as conversations_db
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


def test_restore_removes_only_the_ignored_decision_so_prompts_can_return():
    from utils.speaker_tag_prompts.selection import select_prompts

    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c1')
    store.rows[path] = {
        'id': 'c1',
        'status': 'completed',
        'started_at': NOW,
        'audio_files': [{'chunk_timestamps': [NOW.timestamp()], 'duration': 10}],
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 1, 'start': 0, 'end': 6, 'text': 'synthetic speech', 'is_user': False}
        ],
        'manual_speaker_assignments': {
            'generation': 1,
            'speakers': {'1': {'generation': 1, 'person_id': None, 'is_user': False}},
        },
    }
    db.record_ignored_voice('u', 'c1', 1, NOW, firestore_client=store)
    store.rows[STATE]['ignored_voices']['c1:1']['assignment_generation'] = 1
    assert db.remove_ignored_voice('u', 'c1', 1, [], firestore_client=store)
    raw = store.rows[path]
    raw['manual_speaker_assignments'] = conversations_db.decode_manual_speaker_assignments(
        'u', raw['manual_speaker_assignments'], bool(raw.get('manual_speaker_assignments_compressed'))
    )
    assert select_prompts([raw], now=NOW, owner_has_voice=False, named_allowed=False, answered=set(), people={})


def test_restore_cannot_replace_a_newer_label_or_another_users_marker():
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=1, firestore_client=store)
    decision = {'generation': 2, 'person_id': 'p1', 'is_user': False}
    path = ('users', 'u', 'conversations', 'c1')
    store.rows[path] = {'manual_speaker_assignments': {'generation': 2, 'speakers': {'1': decision}}}
    assert not db.remove_ignored_voice('other', 'c1', 1, [], firestore_client=store)
    assert db.ignored_voice_keys(store.rows[STATE]) == {'c1:1'}
    assert db.remove_ignored_voice('u', 'c1', 1, [], firestore_client=store)
    assert store.rows[path]['manual_speaker_assignments']['speakers']['1'] == decision
