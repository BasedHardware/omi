"""Synthetic notes and real codecs/transactions; no provider or customer reads."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import google.auth.credentials  # noqa: F401
import pytest
from models.summary_speaker_labels import SpeakerCandidate, SpeakerLabeledExtraction
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import stub_modules
from utils.conversations.meeting_participants import MeetingRoster, RosterEntry
from utils.conversations.summary_speaker_labels import select_candidates

START = datetime(2026, 10, 5, tzinfo=timezone.utc)


@pytest.fixture(scope='module', autouse=True)
def imports():
    with stub_modules({}):
        import database.summary_speaker_labels
        import utils.llm.conversation_processing
        import utils.speaker_identification

        yield


def entry(name, kind='human', person_id=None):
    return RosterEntry(name, None, None, kind, 'macos_calendar', person_id)


def roster():
    return MeetingRoster((entry('David', 'owner'), entry('Eddie Thai')), 'Intro', False)


def segment(sid='s1', key=2, text='My name is Eddie Thai.'):
    return dict(id=sid, speaker=f'SPEAKER_{key:02}', speaker_id=key, text=text, is_user=False, start=0.0, end=4.0)


def candidate(name='Eddie Thai', key=2, sid='s1', **kwargs):
    return SpeakerCandidate(
        name=name,
        bindings=[
            dict(speaker_id=key, confidence='high', evidence_segment_ids=[sid], evidence_kind='self_introduction')
        ],
        **kwargs,
    )


def select(candidates=None, segments=None, receipt=None, allow_named=True):
    return select_candidates(
        candidates or [candidate()], segments or [segment()], receipt or {}, roster(), allow_named=allow_named
    )


def test_selection_entitlement_and_free_owner():
    assert select()
    assert not select(allow_named=False)
    assert select(
        [candidate('David', 0, 's0', is_owner=True)], [segment('s0', 0, 'My name is David.')], allow_named=False
    )


def test_full_name_intro_must_be_contiguous_and_not_completed_by_another_mention():
    assert not select(segments=[segment(text='My name is Eddie. Thai was mentioned earlier.')])
    assert not select(segments=[segment(text='My name is Eddie Other.')])


@pytest.mark.parametrize(
    'decision',
    [
        dict(person_id='manual'),
        dict(is_user=True),
        dict(rejection={'kind': 'not_me'}),
        dict(person_id=None, is_user=False),
    ],
)
@pytest.mark.parametrize('section', ['speakers', 'segments'])
def test_manual_positive_negative_and_unassign_reserve_key(decision, section):
    key = '2' if section == 'speakers' else 's1'
    assert not select(receipt={section: {key: decision}})


@pytest.mark.parametrize(
    'field,value',
    [
        ('person_id', 'existing'),
        ('is_user', True),
        ('speaker_label_source', 'manual'),
        ('speaker_label_source', 'auto'),
    ],
)
def test_existing_assignments_reserved(field, value):
    assert not select(segments=[{**segment(), field: value}])


def test_conflict_declines_even_low_confidence_claim():
    other = candidate('Maya Chen')
    other.bindings[0].confidence = 'low'
    assert not select([candidate(), other])


@pytest.mark.parametrize('confidence', ['high', 'medium', 'low'])
def test_missing_evidence_never_grants_a_contextual_label(confidence):
    c = candidate()
    c.bindings[0].confidence = confidence
    c.bindings[0].evidence_kind = 'contextual'
    c.bindings[0].evidence_segment_ids = []
    assert not select([c])


def test_multiple_keys_need_independent_evidence_and_decline_whole_participant():
    c = candidate()
    c.bindings.append(candidate(key=3, sid='s3').bindings[0])
    assert len(select([c], [segment(), segment('s3', 3)])) == 2
    c.bindings[1].evidence_segment_ids = ['s1']
    assert not select([c], [segment(), segment('s3', 3)])


def test_reused_key_scopes_mixed_voice_and_fabricated_evidence_decline():
    assert not select(segments=[{**segment(), 'speaker_id_scope': 'a'}, {**segment('s3'), 'speaker_id_scope': 'b'}])
    assert not select(segments=[segment(), segment('s3', text='My name is Maya Chen.')])
    assert not select([candidate(sid='invented')])
    assert not select([candidate('Boardy', is_ai_agent=True)])
    assert not select([candidate('David', is_owner=False)])


def test_roster_context_can_bind_without_literal_intro_but_no_roster_bijection():
    c = candidate()
    c.bindings[0].evidence_kind = 'contextual'
    assert select([c], [segment(text='I can send the introductions we discussed.')])
    assert not select_candidates(
        [candidate('Avery Quinn')], [segment(text='Avery was mentioned.')], {}, roster(), allow_named=True
    )


@pytest.mark.parametrize('bad', [None, 'wrong', [{}], [{'speaker_id': '2'}]])
def test_malformed_bindings_do_not_drop_note_or_participant(bad):
    parsed = SpeakerLabeledExtraction.model_validate(
        dict(
            title='Intro',
            participants=[dict(name='Eddie Thai', source='roster', speaker_bindings=bad)],
            owner={'name': 123},
        )
    )
    note = parsed.to_structured()
    assert note.title == 'Intro' and note.participants[0].name == 'Eddie Thai'
    assert not note._summary_speaker_candidates[0].bindings
    assert 'speaker_bindings' not in note.model_dump_json()
    assert 'owner' not in note.model_dump()


def make_note():
    p = dict(name='Eddie Thai', source='roster', speaker_bindings=[b.model_dump() for b in candidate().bindings])
    note = SpeakerLabeledExtraction.model_validate(
        dict(title='Intro', overview='Eddie would send introductions.', participants=[p])
    ).to_structured()
    note._summary_speaker_roster = roster()
    return note


@pytest.fixture
def world(monkeypatch):
    from database import conversations as db
    from database import summary_speaker_labels as stage
    from database import _client
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreCollection
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument, StrictFirestoreSnapshot

    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    note = make_note()
    conv = SimpleNamespace(
        id='c', discarded=False, structured=note, transcript_segments=[TranscriptSegment.model_validate(segment())]
    )
    store.rows[path] = db.encode_conversation_for_write(
        'u',
        dict(
            id='c',
            structured=note.model_dump(),
            status='completed',
            transcript_segments=[segment()],
            data_protection_level='standard',
        ),
    )

    def limit(collection, count):
        def stream(*, transaction):
            transaction._assert_read_allowed()
            snapshots = []
            for p, value in store.rows.items():
                if p[:-1] == collection._path:
                    snap = StrictFirestoreSnapshot(value)
                    snap.id = p[-1]
                    snap.reference = StrictFirestoreDocument(store, p)
                    snapshots.append(snap)
            return iter(snapshots[:count])

        return SimpleNamespace(stream=stream)

    monkeypatch.setattr(StrictFirestoreCollection, 'limit', limit, raising=False)
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda _: True)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda _: None)
    monkeypatch.setenv('SUMMARY_SPEAKER_LABELS_ENABLED', 'on')
    return stage, db, store, path, conv


def test_transaction_creates_people_and_labels_idempotently_with_provenance(world):
    stage, db, store, path, conv = world
    assert stage.apply_summary_speaker_labels('u', conv) == 1
    stored = db.decode_transcript_segments_verified('u', store.rows[path]['transcript_segments'], True)[0]
    assert stored['speaker_match_source'] == 'summary_inferred'
    assert stored['speaker_label_source'] == 'auto'
    assert stored['summary_speaker_evidence']['evidence_segment_ids'] == ['s1']
    people = [v for p, v in store.rows.items() if p[-2] == 'people']
    assert len(people) == 1 and people[0]['name'] == 'Eddie Thai'
    assert not people[0]['speech_samples'] and 'speaker_embedding' not in people[0]
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows[path]['structured']['title'] == 'Intro'


@pytest.mark.parametrize('mode', ['normalized', 'alias', 'link'])
def test_existing_people_resolved_without_duplicate(world, mode):
    stage, _, store, _, conv = world
    person = dict(name='  EDDIE   THAI  ', aliases=[])
    if mode == 'alias':
        person.update(name='Edward Thai', aliases=['Eddie Thai'])
    if mode == 'link':
        person['name'] = 'Edward Thai'
        conv.structured._summary_speaker_roster = MeetingRoster(
            (entry('David', 'owner'), entry('Eddie Thai', person_id='p1')), 'Intro', False
        )
    store.rows[('users', 'u', 'people', 'p1')] = person
    assert stage.apply_summary_speaker_labels('u', conv) == 1
    assert conv.transcript_segments[0].person_id == 'p1'
    assert len([p for p in store.rows if p[-2] == 'people']) == 1


@pytest.mark.parametrize(
    'field,value', [('deleted', True), ('is_locked', True), ('discarded', True), ('status', 'processing')]
)
def test_lifecycle_fence(world, field, value):
    stage, _, store, path, conv = world
    store.rows[path][field] = value
    before = deepcopy(store.rows)
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows == before


def test_current_manual_receipt_and_stale_transcript_fence(world):
    stage, db, store, path, conv = world
    store.rows[path]['manual_speaker_assignments'] = {'segments': {'s1': {'rejection': {'kind': 'not_person'}}}}
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    store.rows[path].pop('manual_speaker_assignments')
    store.rows[path].update(db.encode_conversation_for_write('u', {'transcript_segments': [segment(text='new text')]}))
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert not [p for p in store.rows if p[-2] == 'people']


def test_disabled_and_free_never_read_catalog(world, monkeypatch):
    stage, _, store, _, conv = world
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection

    monkeypatch.setattr(StrictFirestoreCollection, 'limit', lambda *args: pytest.fail('catalog read'))
    monkeypatch.delenv('SUMMARY_SPEAKER_LABELS_ENABLED')
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    monkeypatch.setenv('SUMMARY_SPEAKER_LABELS_ENABLED', 'on')
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda _: False)
    assert stage.apply_summary_speaker_labels('u', conv) == 0


def test_codec_and_entitlement_errors_preserve_note_and_labels(world, monkeypatch):
    stage, db, store, _, conv = world
    before = deepcopy(store.rows)
    monkeypatch.setattr(db, 'encode_conversation_for_write', lambda *args: (_ for _ in ()).throw(ValueError('codec')))
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows == before
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda _: (_ for _ in ()).throw(ValueError('plan')))
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows == before


def test_ambiguous_people_and_catalog_overflow_decline(world):
    stage, _, store, _, conv = world
    for index in range(2):
        store.rows[('users', 'u', 'people', str(index))] = dict(name='Eddie Thai')
    before = deepcopy(store.rows)
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows == before

    for index in range(stage.CATALOG_LIMIT + 1):
        store.rows[('users', 'u', 'people', str(index))] = dict(name=f'Person {index}')
    before = deepcopy(store.rows)
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows == before


def test_malformed_stored_segment_declines_before_any_write(world):
    stage, db, store, path, conv = world
    store.rows[path].update(
        db.encode_conversation_for_write('u', {'transcript_segments': [{**segment(), 'start': 'malformed'}]})
    )
    before = deepcopy(store.rows)
    assert stage.apply_summary_speaker_labels('u', conv) == 0
    assert store.rows == before


def test_free_owner_is_labeled_without_person_creation(world, monkeypatch):
    stage, db, store, path, conv = world
    c = candidate('David', 0, 's0', is_owner=True)
    conv.structured._summary_speaker_candidates = [c]
    conv.transcript_segments = [TranscriptSegment.model_validate(segment('s0', 0, 'My name is David.'))]
    store.rows[path].update(
        db.encode_conversation_for_write(
            'u', {'transcript_segments': [s.model_dump() for s in conv.transcript_segments]}
        )
    )
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda _: pytest.fail('owner entitlement read'))
    assert stage.apply_summary_speaker_labels('u', conv) == 1
    assert conv.transcript_segments[0].is_user
    assert not [p for p in store.rows if p[-2] == 'people']


def test_manual_correction_clears_inferred_evidence():
    from utils.manual_speaker_assignments import apply_manual_assignments

    inferred = {
        **segment(),
        'person_id': 'p',
        'speaker_match_source': 'summary_inferred',
        'summary_speaker_evidence': {'confidence': 'high'},
    }
    corrected = apply_manual_assignments(
        [inferred], {'speakers': {'2': {'person_id': 'manual', 'is_user': False, 'generation': 1}}}
    )[0]
    assert corrected['person_id'] == 'manual'
    assert corrected['speaker_match_source'] is None
    assert 'summary_speaker_evidence' not in corrected


def test_inferred_labels_do_not_authorize_voice_training():
    from utils.speaker_learning_policy import authorized_teaching_segments

    inferred = {
        **segment(),
        'person_id': 'p',
        'speaker_match_source': 'summary_inferred',
        'speaker_label_source': 'auto',
    }
    assert authorized_teaching_segments({'transcript_segments': [inferred]}, 'p') == []


def test_owner_wording_prompt_keeps_third_person_without_gender_inference():
    from utils.llm.meeting_notes_rich_prompts import _RICH_MEETING_RULES

    assert 'Keep notes in the third person' in _RICH_MEETING_RULES
    assert 'once per sentence' in _RICH_MEETING_RULES
    assert 'David would welcome a meeting' in _RICH_MEETING_RULES
    assert 'do not use "they" for the owner immediately after naming them' in _RICH_MEETING_RULES
    assert 'Never infer anyone\'s gender' in _RICH_MEETING_RULES
