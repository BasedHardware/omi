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


def test_restore_drops_generation_matched_segment_scoped_exclusions():
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=1, firestore_client=store)
    path = ('users', 'u', 'conversations', 'c1')
    # Live-sheet bulk exclusion shape: no speakers decision, only segments.
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 1,
            'segments': {
                's1': {'generation': 1, 'person_id': None, 'is_user': False, 'speaker_id': 1},
                's2': {'generation': 1, 'person_id': None, 'is_user': False, 'speaker_id': 1},
                'keep': {'generation': 1, 'person_id': None, 'is_user': False, 'speaker_id': 2},
            },
        }
    }
    assert db.remove_ignored_voice('u', 'c1', 1, [], firestore_client=store)
    raw = store.rows[path]
    receipt = conversations_db.decode_manual_speaker_assignments(
        'u', raw['manual_speaker_assignments'], bool(raw.get('manual_speaker_assignments_compressed'))
    )
    assert set(receipt['segments']) == {'keep'}
    assert receipt['generation'] == 2
    assert db.ignored_voice_keys(store.rows[STATE]) == set()


def test_restore_removes_stacked_generation_exclusions_no_newer_than_the_marker():
    """A restore must clear every not_a_person decision at/below the marker.

    One voice can stack exclusions across generations — a whole-voice
    exclusion (gen 1) later narrowed by a selected-segment exclusion (gen 3,
    the marker's generation). Clearing only the exact-generation entries
    leaves the older whole-voice decision winning: the voice stays excluded
    and prompt-suppressed while its sole marker (and Settings restore
    affordance) is gone. Genuinely newer decisions (gen > marker) survive.
    """
    store = StrictFirestore()
    # The marker remembers only the newest exclusion generation (3).
    db.record_ignored_voice('u', 'c1', 4, NOW, assignment_generation=3, firestore_client=store)
    path = ('users', 'u', 'conversations', 'c1')
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 3,
            'speakers': {
                # Stacked older whole-voice exclusion the restore must drop.
                '4': {
                    'generation': 1,
                    'person_id': None,
                    'is_user': False,
                    'rejection': {'kind': 'not_a_person', 'person_id': None},
                },
            },
            'segments': {
                # Newer selected-segment exclusion the marker was recorded for.
                's1': {
                    'generation': 3,
                    'person_id': None,
                    'is_user': False,
                    'speaker_id': 4,
                    'rejection': {'kind': 'not_a_person', 'person_id': None},
                },
                # A genuinely newer exclusion from another surface: survives.
                's2': {
                    'generation': 5,
                    'person_id': None,
                    'is_user': False,
                    'speaker_id': 4,
                    'rejection': {'kind': 'not_a_person', 'person_id': None},
                },
                # Another voice's exclusion: untouched.
                's3': {
                    'generation': 3,
                    'person_id': None,
                    'is_user': False,
                    'speaker_id': 9,
                    'rejection': {'kind': 'not_a_person', 'person_id': None},
                },
            },
        }
    }
    assert db.remove_ignored_voice('u', 'c1', 4, [], firestore_client=store)
    raw = store.rows[path]
    receipt = conversations_db.decode_manual_speaker_assignments(
        'u', raw['manual_speaker_assignments'], bool(raw.get('manual_speaker_assignments_compressed'))
    )
    # The stacked older whole-voice exclusion and the marker-generation
    # selected-segment exclusion are gone; the newer and other-voice entries
    # survive untouched.
    assert 'speakers' not in receipt or '4' not in (receipt.get('speakers') or {})
    assert set(receipt.get('segments') or {}) == {'s2', 's3'}
    assert receipt['generation'] == 4
    assert db.ignored_voice_keys(store.rows[STATE]) == set()


def test_restore_keeps_a_newer_not_me_answer_intact():
    """The broader sweep must not eat an explicit older-kind answer.

    A not_me answer at a generation <= the marker's is a different decision
    the user made (not the exclusion being restored): it survives the sweep,
    so restore stays scoped to not_a_person decisions only.
    """
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 4, NOW, assignment_generation=3, firestore_client=store)
    path = ('users', 'u', 'conversations', 'c1')
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 3,
            'speakers': {
                '4': {
                    'generation': 3,
                    'person_id': None,
                    'is_user': False,
                    'rejection': {'kind': 'not_me', 'person_id': None},
                },
            },
            'segments': {
                's1': {
                    'generation': 3,
                    'person_id': None,
                    'is_user': False,
                    'speaker_id': 4,
                    'rejection': {'kind': 'not_a_person', 'person_id': None},
                },
            },
        }
    }
    assert db.remove_ignored_voice('u', 'c1', 4, [], firestore_client=store)
    raw = store.rows[path]
    receipt = conversations_db.decode_manual_speaker_assignments(
        'u', raw['manual_speaker_assignments'], bool(raw.get('manual_speaker_assignments_compressed'))
    )
    # The not_me whole-voice answer survives; only the not_a_person segment
    # exclusion was dropped.
    assert receipt['speakers']['4']['rejection']['kind'] == 'not_me'
    assert set(receipt.get('segments') or {}) == set()


def test_positive_assignment_supersedes_marker():
    store = StrictFirestore()
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=1, firestore_client=store)
    db.record_ignored_voice('u', 'c2', 2, NOW, assignment_generation=1, firestore_client=store)
    assert db.clear_ignored_voices('u', 'c1', [1], firestore_client=store) == 1
    assert db.ignored_voice_keys(store.rows[STATE]) == {'c2:2'}
    assert db.clear_ignored_voices('u', 'c1', [1], firestore_client=store) == 0
    assert db.clear_ignored_voices('u', 'c1', [], firestore_client=store) == 0


def test_stale_generation_marker_is_not_recorded_after_a_newer_positive():
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c1')
    # A newer whole-voice positive (generation 3) already replaced the exclusion
    # whose in-flight request is about to record its generation-1 marker.
    store.rows[path] = {
        'manual_speaker_assignments': {'generation': 3, 'speakers': {'1': {'generation': 3, 'person_id': 'p1'}}}
    }
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=1, firestore_client=store)
    # The stale generation was fenced out entirely — no marker, no state doc.
    assert db.ignored_voice_keys(store.rows.get(STATE) or {'ignored_voices': {}}) == set()
    # A range-only newer entry does not unseat the exclusion: record stands.
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 3,
            'segments': {'s1': {'generation': 3, 'person_id': 'p1', 'segment_only': True, 'speaker_id': 1}},
        }
    }
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=1, firestore_client=store)
    assert db.ignored_voice_keys(store.rows[STATE]) == {'c1:1'}
    # No fence applies without an assignment generation (legacy tag prompts).
    db.record_ignored_voice('u', 'c3', 2, NOW, firestore_client=store)
    assert 'c3:2' in db.ignored_voice_keys(store.rows[STATE])


def test_stale_generation_marker_is_not_recorded_after_a_newer_not_me():
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c1')
    # The supported is_user=false answer commits a whole-voice not_me rejection
    # at generation 3; a delayed generation-1 exclusion write must not recreate
    # its marker — the ignored-voice list would suppress and list a voice whose
    # winning decision is no longer not_a_person.
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 3,
            'speakers': {'1': {'generation': 3, 'person_id': None, 'is_user': False, 'rejection': {'kind': 'not_me'}}},
        }
    }
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=1, firestore_client=store)
    assert db.ignored_voice_keys(store.rows.get(STATE) or {'ignored_voices': {}}) == set()
    # A newer whole-voice not_a_person at a newer generation is the exclusion
    # itself re-confirmed: the older in-flight write stays fenced, but a fresh
    # record at the newest generation stands.
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 4,
            'speakers': {
                '1': {'generation': 4, 'person_id': None, 'is_user': False, 'rejection': {'kind': 'not_a_person'}}
            },
        }
    }
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=4, firestore_client=store)
    assert db.ignored_voice_keys(store.rows[STATE]) == {'c1:1'}


def test_delayed_clear_cannot_remove_a_newer_decisions_marker():
    store = StrictFirestore()
    # Generation 3 positive committed, then a generation 4 re-exclusion
    # recorded its marker. The generation 3 request's delayed clear must not
    # remove the newer marker — the voice would silently leave Settings >
    # Ignored Voices and could no longer be restored from there.
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=4, firestore_client=store)
    assert db.clear_ignored_voices('u', 'c1', [1], assignment_generation=3, firestore_client=store) == 0
    assert db.ignored_voice_keys(store.rows[STATE]) == {'c1:1'}
    # The same-generation positive retirement still clears it.
    assert db.clear_ignored_voices('u', 'c1', [1], assignment_generation=4, firestore_client=store) == 1
    assert db.ignored_voice_keys(store.rows.get(STATE) or {'ignored_voices': {}}) == set()
    # A legacy marker without a generation fence stays clearable by any positive.
    db.record_ignored_voice('u', 'c2', 2, NOW, firestore_client=store)
    assert db.clear_ignored_voices('u', 'c2', [2], assignment_generation=9, firestore_client=store) == 1


def test_delayed_older_exclusion_cannot_overwrite_a_newer_exclusions_marker():
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c1')
    # Two exclusions for the same voice commit at generations N=1 and N+1=2;
    # the generation-2 write records its marker first. The delayed generation-1
    # request must not overwrite it: restoring from Settings matches the
    # marker's generation against the receipt, so a generation-1 marker would
    # drop only generation-1 entries while the generation-2 rejection stays
    # active but can no longer be restored.
    store.rows[path] = {
        'manual_speaker_assignments': {
            'generation': 2,
            'speakers': {
                '1': {'generation': 2, 'person_id': None, 'is_user': False, 'rejection': {'kind': 'not_a_person'}}
            },
        }
    }
    db.record_ignored_voice('u', 'c1', 1, NOW, assignment_generation=2, firestore_client=store)
    db.record_ignored_voice('u', 'c1', 1, NOW + timedelta(minutes=1), assignment_generation=1, firestore_client=store)
    markers = db.ignored_voices(store.rows[STATE])
    assert len(markers) == 1
    assert markers[0]['assignment_generation'] == 2


def test_importing_speaker_identification_first_does_not_break_collection():
    # The generation fence reads the receipt through database.conversations,
    # which must stay a lazy import: utils.speaker_identification imports
    # voice_profiles at module level, and a module-level conversations import
    # here once produced a partially initialized package that failed CI test
    # collection (ImportError: cannot import name 'conversations_collection').
    import subprocess
    import sys

    probe = 'import utils.speaker_identification; import database.voice_profiles; print("ok")'
    result = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=__file__.rsplit('/tests/', 1)[0],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'
