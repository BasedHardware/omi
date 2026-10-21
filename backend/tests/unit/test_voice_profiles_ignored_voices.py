from datetime import datetime, timedelta, timezone

import pytest
from google.cloud.firestore_v1.field_path import FieldPath

from database import conversations as conversations_db
from database import voice_profiles as db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.speaker_tag_prompts.keys import ignored_voice_key
from utils.speaker_tag_prompts.selection import select_prompts

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


@pytest.mark.parametrize('conversation_id', ['x' * 1460, 'x' * 1500, 'é' * 750, '\\' * 750, '`' * 750])
def test_maximum_document_ids_keep_bounded_marker_keys_and_restore(conversation_id):
    store = StrictFirestore()
    db.record_ignored_voice('u', conversation_id, 3, NOW, firestore_client=store)
    db.record_ignored_voice('u', conversation_id, 3, NOW + timedelta(minutes=1), firestore_client=store)
    markers = store.rows[STATE]['ignored_voices']
    assert len(markers) == 1
    key, entry = next(iter(markers.items()))
    assert len(key.encode('utf-8')) <= 1500
    assert len(FieldPath('ignored_voices', key, 'assignment_generation').to_api_repr().encode('utf-8')) <= 1500
    assert key == ignored_voice_key(conversation_id, 3)
    assert entry['conversation_id'] == conversation_id
    assert entry['speaker_id'] == 3
    assert db.ignored_voice_keys(store.rows[STATE]) == {key}
    assert db.remove_ignored_voice('u', conversation_id, 3, [], firestore_client=store)
    assert store.rows[STATE]['ignored_voices'] == {}


def test_ignored_voice_key_preserves_existing_keys_at_field_byte_limit():
    conversation_id = 'x' * 1459
    assert ignored_voice_key(conversation_id, 3) == f'{conversation_id}:3'


def test_restore_matches_original_entry_when_legacy_key_needs_new_encoding():
    conversation_id = 'x' * 1465
    legacy_key = f'{conversation_id}:3'
    assert len(FieldPath('ignored_voices', legacy_key, 'conversation_id').to_api_repr().encode('utf-8')) == 1500
    assert ignored_voice_key(conversation_id, 3) != legacy_key
    store = StrictFirestore()
    store.rows[STATE] = {
        'ignored_voices': {legacy_key: {'conversation_id': conversation_id, 'speaker_id': 3, 'ignored_at': NOW}}
    }
    assert db.remove_ignored_voice('u', conversation_id, 3, [], firestore_client=store)
    assert store.rows[STATE]['ignored_voices'] == {}


@pytest.mark.parametrize('owner_has_voice', [False, True])
def test_legacy_long_marker_suppresses_naming_and_owner_prompts_without_receipt(owner_has_voice):
    conversation_id = 'x' * 1465
    state = {
        'ignored_voices': {
            f'{conversation_id}:1': {'conversation_id': conversation_id, 'speaker_id': 1, 'ignored_at': NOW}
        }
    }
    conversation = {
        'id': conversation_id,
        'status': 'completed',
        'started_at': NOW,
        'audio_files': [{'chunk_timestamps': [NOW.timestamp()], 'duration': 10}],
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 1, 'is_user': False, 'start': 0, 'end': 6, 'text': 'Synthetic speech'}
        ],
    }
    options = {
        'now': NOW,
        'owner_has_voice': owner_has_voice,
        'named_allowed': not owner_has_voice,
        'answered': set(),
        'people': {},
        'owner_evidence': lambda current, runs: (runs[0], 0.5) if runs else None,
    }
    baseline = select_prompts([conversation], **options)
    assert len(baseline) == 1
    assert baseline[0].kind == ('owner_check' if owner_has_voice else 'identify')
    assert not select_prompts([conversation], ignored=db.ignored_voice_keys(state), **options)


def test_remove_ignored_voice_forgets_its_answers_only():
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 1, NOW, firestore_client=store)
    store.rows[STATE]['answered'] = {'p1': NOW, 'keep': NOW}
    assert db.remove_ignored_voice('u', 'c1', 1, ['p1'], firestore_client=store) is True
    assert store.rows[STATE]['ignored_voices'] == {} and store.rows[STATE]['answered'] == {'keep': NOW}
    assert db.remove_ignored_voice('u', 'c1', 1, ['p1'], firestore_client=store) is False


def test_restore_removes_only_the_ignored_decision_so_prompts_can_return():
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
    assert not select_prompts(
        [store.rows[path]], now=NOW, owner_has_voice=False, named_allowed=True, answered=set(), people={}
    )
    assert db.remove_ignored_voice('u', 'c1', 1, [], firestore_client=store)
    raw = store.rows[path]
    raw['manual_speaker_assignments'] = conversations_db.decode_manual_speaker_assignments(
        'u', raw['manual_speaker_assignments'], bool(raw.get('manual_speaker_assignments_compressed'))
    )
    # An unenrolled free account cannot be offered an owner question. Restoring
    # an ignored voice does restore eligibility for paid naming cards.
    assert not select_prompts([raw], now=NOW, owner_has_voice=False, named_allowed=False, answered=set(), people={})
    prompts = select_prompts([raw], now=NOW, owner_has_voice=False, named_allowed=True, answered=set(), people={})
    assert len(prompts) == 1 and prompts[0].kind == 'identify'


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
