"""Synthetic notes identity fixtures; no provider, account, or biometric IO."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database.notes_identity import claim_late_evidence, identifier_retraction, person_id_for, stage_notes_identity
from database.person_aliases import dismiss_person_transaction
from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.structured import Participant, Structured
from models.structured_extraction import RichStructuredExtraction
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.meeting_context_pack import (
    _gather_people_facts,
    MeetingContextPack,
    render_meeting_context_pack,
)
from utils.conversations.meeting_participants import normalize_meeting_participants
from utils.llm.meeting_notes_validation import validate_rich_meeting_notes
from utils.speaker_learning_policy import authorized_teaching_segments

UID = 'synthetic-notes-owner'
CID = 'synthetic-notes-conversation'
NAME = 'Morgan Reed'
EMAIL = 'cloudberry42@gmail.com'  # synthetic, intentionally unrelated to the name
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def roster(attendees=()):
    calendar = CalendarMeetingContext(
        calendar_event_id='synthetic-event',
        title='Synthetic intro',
        participants=list(attendees),
        start_time=NOW,
        duration_minutes=30,
        calendar_source='google',
    )
    return normalize_meeting_participants(
        calendar, 'desktop', 'Casey Owner', ['owner@example.invalid'], [], exact_people_match=True
    )


@pytest.mark.parametrize('evidence', ['frame', 'screen_moment', 'calendar_attendee'])
def test_model_screen_name_and_unrelated_freemail_survive(evidence):
    context = roster([MeetingParticipant(email=EMAIL)] if evidence == 'calendar_attendee' else [])
    result = validate_rich_meeting_notes(
        Structured(participants=[Participant(name=NAME, email=EMAIL, source='screen')]),
        transcript_body='Hello. Let us discuss the project.',
        roster=context,
        has_background_context=evidence == 'screen_moment',
        background_body='SCREEN MOMENTS\nCalendar card' if evidence == 'screen_moment' else '',
        has_identity_evidence=True,
    )
    assert [(p.name, p.email, p.source) for p in result.participants] == [(NAME, EMAIL, 'screen')]


def test_owner_identity_does_not_depend_on_model_is_user_bit():
    output = RichStructuredExtraction.model_validate(
        {
            'participants': [
                {'name': 'Casey Owner', 'email': 'owner@example.invalid', 'source': 'screen', 'is_user': False},
                {
                    'name': NAME,
                    'email': EMAIL,
                    'source': 'screen',
                    'is_user': True,
                    'alias': 'Mo',
                    'speaker_bindings': [2],
                },
            ]
        }
    ).to_structured()
    validate_rich_meeting_notes(
        output, transcript_body='hello', roster=roster(), has_background_context=False, has_identity_evidence=True
    )
    assert [p.name for p in output.participants] == [NAME]
    assert output.participants[0].alias == 'Mo'
    assert output.participants[0].speaker_bindings == [2]


def fixture(existing_people=None, participant=None, receipt=None):
    people = existing_people or {}
    rows = {('users', UID): {'name': 'Casey Owner', 'email': 'owner@example.invalid'}}
    rows.update({('users', UID, 'people', pid): p for pid, p in people.items()})
    db = StrictFirestore(rows)
    user_ref = db.collection('users').document(UID)
    data = {
        'id': CID,
        'structured': {
            'participants': [
                participant
                or {'name': NAME, 'email': EMAIL, 'source': 'screen', 'alias': 'Mo', 'speaker_bindings': [2]}
            ]
        },
        'transcript_segments': [
            {
                'id': 'synthetic-segment',
                'text': 'I can do that.',
                'speaker_id': 2,
                'start': 0,
                'end': 15,
                'is_user': False,
            }
        ],
        '_notes_identity': {
            'catalog_ids': list(people),
            'owner_names': ['Casey Owner'],
            'owner_emails': ['owner@example.invalid'],
            'frame_count': 1,
        },
    }
    transaction = db.transaction()
    result = stage_notes_identity(
        transaction,
        user_ref,
        data,
        {'manual_speaker_assignments': receipt or {}},
        decode_segments=lambda uid, values, compressed: deepcopy(values),
        decode_receipt=lambda uid, values, compressed: values or {},
        encode=lambda values, uid, level: deepcopy(values),
    )
    # The note and people use the same transaction; this fixture rejects reads after writes.
    transaction.set(user_ref.collection('conversations').document(CID), data)
    return db, transaction, data, result


def test_provisional_person_email_alias_and_binding_never_teach():
    db, transaction, note, segments = fixture()
    pid = person_id_for(NAME, EMAIL)
    person = db.rows[('users', UID, 'people', pid)]
    assert person['name'] == NAME and person['email'] == EMAIL and person['aliases'] == ['Mo']
    assert person['confidence'] == 'unverified' and person['speech_samples'] == []
    assert segments[0]['person_id'] == pid
    assert segments[0]['speaker_label_source'] == 'auto'
    assert segments[0]['speaker_match_source'] == 'notes_inferred'
    assert authorized_teaching_segments(note, pid) == []
    assert len(transaction.creates) == 1 and len(transaction.sets) == 1
    assert all(path[-2] != 'speaker_learning_jobs' for path in db.rows)
    assert '_notes_identity' not in note


@pytest.mark.parametrize(
    'name,email,expected', [('Morgan', '', False), ('Different Name', EMAIL, True), ('Mo', '', True)]
)
def test_only_exact_email_or_stored_alias_attaches(name, email, expected):
    people = {
        'synthetic-person': {
            'id': 'synthetic-person',
            'name': NAME,
            'email': EMAIL,
            'aliases': ['Mo'],
            'speech_samples': [],
        }
    }
    _, _, _, segments = fixture(people, {'name': name, 'email': email, 'source': 'screen', 'speaker_bindings': [2]})
    assert (segments[0]['person_id'] == 'synthetic-person') is expected


def test_notes_roster_does_not_first_name_merge():
    people = [{'id': 'synthetic-person', 'name': NAME, 'email': EMAIL, 'aliases': ['Mo']}]
    calendar = CalendarMeetingContext(
        calendar_event_id='synthetic-event',
        title='Synthetic intro',
        participants=[MeetingParticipant(name='Morgan')],
        start_time=NOW,
        duration_minutes=30,
        calendar_source='google',
    )
    result = normalize_meeting_participants(calendar, 'desktop', 'Casey Owner', [], people, exact_people_match=True)
    assert next(e for e in result.entries if e.kind == 'human').person_id is None


@pytest.mark.parametrize(
    'decision',
    [
        {
            'person_id': None,
            'is_user': False,
            'rejection': {'kind': 'not_person', 'person_id': 'synthetic-person'},
            'generation': 1,
        },
        {'person_id': None, 'is_user': False, 'generation': 2},
        {'person_id': 'manual-person', 'is_user': False, 'generation': 3},
    ],
)
def test_reprocess_never_overwrites_rejection_unassignment_or_manual_label(decision):
    _, transaction, _, segments = fixture(receipt={'speakers': {'2': decision}})
    assert segments[0].get('person_id') == decision['person_id']
    assert segments[0].get('speaker_match_source') is None
    assert not transaction.creates


def test_rejection_removes_only_identifiers_this_note_added():
    person = {
        'name': 'Existing Person',
        'email': EMAIL,
        'emails': [EMAIL, 'existing@example.invalid'],
        'aliases': ['Mo', 'Existing'],
        'notes_identity_identifiers': {CID: {'emails': [EMAIL], 'aliases': ['Mo']}},
    }
    updates = identifier_retraction(person, CID)
    assert updates['email'] is None
    assert updates['emails'] == ['existing@example.invalid'] and updates['aliases'] == ['Existing']
    assert CID in updates['notes_identity_rejected_conversations']
    rejected_person = {**person, **updates, 'id': 'synthetic-person', 'name': NAME}
    _, transaction, _, segments = fixture({'synthetic-person': rejected_person})
    assert not transaction.creates and not transaction.updates
    assert segments[0].get('person_id') is None


def test_dismissal_removes_notes_identifiers():
    path = ('users', UID, 'people', 'synthetic-person')
    db = StrictFirestore(
        {
            path: {
                'name': NAME,
                'email': EMAIL,
                'aliases': ['Mo', 'Manual'],
                'notes_identity_identifiers': {CID: {'emails': [EMAIL], 'aliases': ['Mo']}},
            }
        }
    )
    assert dismiss_person_transaction.to_wrap(
        db.transaction(), db.collection('users').document(UID).collection('people').document('synthetic-person')
    )
    assert db.rows[path]['email'] is None and db.rows[path]['aliases'] == ['Manual']
    assert db.rows[path]['is_dismissed'] is True


def test_recent_people_context_includes_identifiers_with_empty_roster():
    facts = _gather_people_facts(
        roster(),
        [
            {'id': 'synthetic-person', 'name': NAME, 'email': EMAIL, 'aliases': ['Mo']},
            {'id': 'dismissed', 'name': 'Hidden', 'is_dismissed': True},
        ],
    )
    block = render_meeting_context_pack(MeetingContextPack(people_facts=facts))
    assert NAME in block and EMAIL in block and 'Mo' in block and 'Hidden' not in block


@pytest.mark.parametrize(
    'title,frames,claimed,expected',
    [(None, 0, None, True), ('My title', 0, None, False), (None, 1, None, False), (None, 0, 'already', False)],
)
def test_late_marker_claims_one_refresh_unless_user_titled(title, frames, claimed, expected):
    path = ('users', UID, 'conversations', CID)
    db = StrictFirestore(
        {
            path: {
                'status': 'completed',
                'user_title': title,
                'notes_screen_frame_count': frames,
                'notes_written_at': NOW,
                'notes_evidence_reprocess_claimed': claimed,
            }
        }
    )
    ref = db.collection('users').document(UID).collection('conversations').document(CID)
    assert (
        claim_late_evidence(
            db.transaction(), ref, marker_at=NOW + timedelta(seconds=30), fingerprint='synthetic-window'
        )
        is expected
    )
    if expected:
        assert not claim_late_evidence(
            db.transaction(), ref, marker_at=NOW + timedelta(seconds=31), fingerprint='synthetic-window'
        )


def test_no_visual_or_attendee_evidence_still_drops_uncorroborated_name():
    result = validate_rich_meeting_notes(
        Structured(participants=[Participant(name=NAME, source='screen')]),
        transcript_body='hello',
        roster=roster(),
        has_background_context=False,
    )
    assert result.participants == []


@pytest.fixture(scope='module')
def notes_module():
    from utils.llm import conversation_processing

    return conversation_processing


@pytest.mark.parametrize('evidence', ['frame', 'screen_moment', 'calendar_attendee'])
def test_actual_notes_call_admits_model_screen_identity(monkeypatch, notes_module, evidence):
    import json
    from types import SimpleNamespace
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix
    from utils.llm.meeting_notes_rich_prompts import NotesFrameImage

    payload = {
        'title': 'Intro with Morgan Reed',
        'participants': [{'name': NAME, 'email': EMAIL, 'source': 'screen', 'speaker_bindings': [2]}],
    }
    captured = []

    def invoke(messages):
        captured.extend(messages)
        return SimpleNamespace(content=json.dumps(payload))

    monkeypatch.setattr(notes_module, 'get_llm', lambda *a, **kw: SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(notes_module, 'shared_conversation_cache_supported', lambda: False)
    frames = (
        (NotesFrameImage('synthetic-frame', '+00:05', 'data:image/jpeg;base64,c3ludGhldGlj'),)
        if evidence == 'frame'
        else ()
    )
    result = notes_module.get_conversation_notes(
        ConversationPromptPrefix(
            conversation_id=CID,
            context='CONVERSATION METADATA\nFULL TRANSCRIPT\n[s1 2] Hello. Let us discuss the project.',
        ),
        started_at=NOW,
        language_code='en',
        output_language_code='en',
        task_intelligence_capture=False,
        tz='UTC',
        roster=roster([MeetingParticipant(email=EMAIL)] if evidence == 'calendar_attendee' else []),
        rich_context_enabled=True,
        meeting_context='BACKGROUND CONTEXT\nSCREEN MOMENTS\n- Calendar card' if evidence == 'screen_moment' else None,
        screen_frames=frames,
    )
    assert [(p.name, p.email) for p in result.participants] == [(NAME, EMAIL)]
    assert result.participants[0].speaker_bindings == [2]
    assert getattr(result, '_notes_identity')['frame_count'] == len(frames)
    if frames:
        assert captured[-1]['content'][-1]['image_url']['url'] == frames[0].data_url


def test_owner_never_upserted_from_false_is_user_bit():
    db, transaction, note, _ = fixture(
        participant={'name': 'Casey Owner', 'email': 'owner@example.invalid', 'source': 'screen', 'is_user': False}
    )
    assert not transaction.creates
    assert not any(path[-2] == 'people' for path in db.rows)
    assert note['structured']['participants'] == []


@pytest.fixture(scope='module')
def late_module():
    from utils.conversations import late_meeting_notes

    return late_meeting_notes


@pytest.mark.asyncio
@pytest.mark.parametrize('frame_count', [0, 1])
async def test_late_pass_refreshes_notes_once_including_all_rejected_pass(monkeypatch, late_module, frame_count):
    from models.conversation import Conversation
    from utils.conversations.screen_content_window import selection_fingerprint, trusted_content_window

    raw = {
        'id': CID,
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW + timedelta(minutes=5),
        'source': 'desktop',
        'status': 'completed',
        'structured': {'title': 'Topic'},
        'notes_written_at': NOW,
        'notes_screen_frame_count': 0,
        'transcript_segments': [
            {
                'id': 'synthetic-segment',
                'text': 'Hello, let us talk.',
                'speaker_id': 2,
                'is_user': False,
                'start': 5,
                'end': 300,
            }
        ],
        'audio_timeline': {'version': 2},
    }
    fingerprint = selection_fingerprint(*trusted_content_window(raw))
    path = ('users', UID, 'conversations', CID)
    db = StrictFirestore({path: raw})
    monkeypatch.setattr(late_module, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(late_module, 'meeting_notes_rich_context_enabled', lambda: True)
    monkeypatch.setattr(late_module, 'configured_screen_frames_bucket', lambda: 'synthetic-bucket')
    monkeypatch.setattr(late_module.conversations_db, 'get_conversation', lambda *a: deepcopy(db.rows[path]))
    monkeypatch.setattr(
        late_module.screen_frames_db,
        'get_conversation_screen_frames_marker',
        lambda *a, **kw: (NOW + timedelta(seconds=30), fingerprint),
    )
    monkeypatch.setattr(late_module, 'deserialize_conversation', lambda data: Conversation(**data))

    async def inline(pool, fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr(late_module, 'run_blocking', inline)
    generated = []

    def generate(*a, **kw):
        generated.append(kw)
        structured = Structured(
            title='Intro with Morgan Reed',
            participants=[Participant(name=NAME, email=EMAIL, source='screen', speaker_bindings=[2])],
        )
        setattr(
            structured,
            '_notes_identity',
            {
                'frame_count': frame_count,
                'catalog_ids': [],
                'owner_names': ['Casey Owner'],
                'owner_emails': ['owner@example.invalid'],
            },
        )
        return structured, False

    monkeypatch.setattr(late_module, '_get_structured', generate)
    saved = []
    monkeypatch.setattr(
        late_module.lifecycle, 'persist_processed_conversation', lambda uid, payload: saved.append(payload) or True
    )
    failures = []
    monkeypatch.setattr(late_module, 'record_fallback', lambda **kw: failures.append(kw))
    await late_module.refresh_notes_after_evidence(UID, CID)
    await late_module.refresh_notes_after_evidence(UID, CID)
    assert not failures
    assert len(generated) == len(saved) == 1
    assert saved[0]['structured']['participants'][0]['email'] == EMAIL
    assert saved[0]['_notes_evidence_reprocess'] is True
    assert saved[0]['_notes_identity']['frame_count'] == frame_count


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('manual_rejection', [False, True])
def test_real_completed_write_commits_people_and_inference_with_current_receipt(monkeypatch, level, manual_rejection):
    from database import conversations as conversations_db
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreTransaction

    db, _, payload, _ = fixture()
    pid = person_id_for(NAME, EMAIL)
    db.rows.pop(('users', UID, 'people', pid))
    path = ('users', UID, 'conversations', CID)
    receipt = (
        {
            'speakers': {
                '2': {
                    'is_user': False,
                    'person_id': None,
                    'rejection': {'kind': 'not_person', 'person_id': pid},
                    'generation': 1,
                }
            }
        }
        if manual_rejection
        else {}
    )
    db.rows[path] = conversations_db._prepare_conversation_for_write(
        {
            'id': CID,
            'data_protection_level': level,
            'status': 'processing',
            'transcript_segments': payload['transcript_segments'],
            'manual_speaker_assignments': receipt,
        },
        UID,
        level,
    )
    payload.update(
        status='completed',
        _notes_identity={
            'catalog_ids': [],
            'owner_names': ['Casey Owner'],
            'owner_emails': ['owner@example.invalid'],
            'frame_count': 1,
        },
    )
    monkeypatch.setattr(conversations_db, 'db', db)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *a: None)
    original_set = StrictFirestoreTransaction.set

    def set_with_merge(transaction, ref, data, merge=False):
        transaction.update(ref, data) if merge else original_set(transaction, ref, data)

    monkeypatch.setattr(StrictFirestoreTransaction, 'set', set_with_merge)
    encoded = conversations_db._prepare_conversation_for_write(payload, UID, level)
    assert conversations_db.persist_processing_result_with_lifecycle.__wrapped__.__wrapped__(UID, encoded)
    stored = db.rows[path]
    segments = conversations_db._decode_transcript_segments_strict(
        UID, stored['transcript_segments'], stored['transcript_segments_compressed']
    )
    if manual_rejection:
        assert segments[0]['person_id'] is None
        assert ('users', UID, 'people', pid) not in db.rows
    else:
        assert segments[0]['person_id'] == pid and segments[0]['speaker_match_source'] == 'notes_inferred'
        assert db.rows[('users', UID, 'people', pid)]['speech_samples'] == []
    assert '_notes_identity' not in stored


def test_calendar_context_passes_through_without_frame_names(monkeypatch):
    from types import SimpleNamespace
    from utils.conversations import meeting_notes_wiring as wiring
    from utils.conversations.screen_frame_evidence import ScreenFrameEvidence

    monkeypatch.setenv('MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED', 'true')
    monkeypatch.setattr(
        wiring,
        'load_screen_frame_evidence',
        lambda *a: (ScreenFrameEvidence('synthetic-frame', NOW, 'strip', 0.5, ('Tile Person',), 'Calendar card'),),
    )
    monkeypatch.setattr(wiring, 'load_people_documents', lambda *a: [])
    monkeypatch.setattr(wiring, 'resolve_owner_identity', lambda *a: ('Casey Owner', ['owner@example.invalid']))
    context = CalendarMeetingContext(
        calendar_event_id='synthetic-event',
        title='Original calendar title',
        participants=[MeetingParticipant(name=NAME, email=EMAIL)],
        start_time=NOW,
        duration_minutes=30,
        calendar_source='google',
    )
    original = context.model_dump()
    captured = []

    def normalize(context_value, *a, **kw):
        captured.append(context_value)
        return normalize_meeting_participants(context_value, *a, **kw)

    monkeypatch.setattr(wiring, 'normalize_meeting_participants', normalize)
    result, _, _, _ = wiring._rich_meeting_roster(
        UID, SimpleNamespace(id=CID, source='desktop', external_data={'conversation_role': 'meeting'}), context
    )
    assert captured == [context] and captured[0] is context
    assert context.model_dump() == original
    assert result.display_title == 'Original calendar title'
    assert [e.display_name for e in result.entries if e.kind == 'human'] == [NAME]


@pytest.mark.parametrize('bindings', [{'speaker_id': 2}, [True, '2', None, -1], [2, 2]])
def test_bad_optional_binding_does_not_cost_the_participant(bindings):
    result = RichStructuredExtraction.model_validate(
        {'participants': [{'name': NAME, 'email': EMAIL, 'source': 'screen', 'speaker_bindings': bindings}]}
    ).to_structured()
    assert result.participants[0].name == NAME and result.participants[0].email == EMAIL
    assert result.participants[0].speaker_bindings == ([2] if bindings == [2, 2] else [])


def test_real_reject_removes_note_added_identifiers(monkeypatch):
    from database import conversations as conversations_db

    db, _, note, _ = fixture()
    pid = person_id_for(NAME, EMAIL)
    path = ('users', UID, 'conversations', CID)
    db.rows[path] = conversations_db._prepare_conversation_for_write(note, UID, 'standard')
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations_db, 'record_speaker_review', lambda *a: None)
    raw, _, _, _ = conversations_db.assign_conversation_speaker(
        UID,
        CID,
        speaker_id=2,
        person_id=None,
        is_user=False,
        use_for_speech_training=False,
        rejection={'kind': 'not_person', 'person_id': pid},
    )
    assert raw['transcript_segments'][0]['person_id'] is None
    person = db.rows[('users', UID, 'people', pid)]
    assert person['email'] is None and person['emails'] == [] and person['aliases'] == []
    assert person['is_dismissed'] is True
    assert CID in person['notes_identity_rejected_conversations']


def test_initial_note_and_people_create_in_one_idempotent_transaction(monkeypatch):
    from database import conversations as conversations_db

    db, _, payload, _ = fixture()
    pid = person_id_for(NAME, EMAIL)
    path = ('users', UID, 'conversations', CID)
    db.rows.pop(path)
    db.rows.pop(('users', UID, 'people', pid))
    payload.update(
        status='completed',
        _notes_identity={
            'catalog_ids': [],
            'owner_names': ['Casey Owner'],
            'owner_emails': ['owner@example.invalid'],
            'frame_count': 1,
        },
    )
    monkeypatch.setattr(conversations_db, 'db', db)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *a: None)
    encoded = conversations_db._prepare_conversation_for_write(payload, UID, 'standard')
    create = conversations_db.create_conversation_if_absent_with_lifecycle.__wrapped__.__wrapped__
    assert create(UID, encoded)
    assert len(db.transactions[-1].creates) == 2
    assert not create(UID, encoded)
    assert db.transactions[-1].creates == []
    assert db.rows[('users', UID, 'people', pid)]['email'] == EMAIL


def test_user_title_set_during_late_model_call_vetoes_commit(monkeypatch):
    from database import conversations as conversations_db

    db, _, payload, _ = fixture()
    path = ('users', UID, 'conversations', CID)
    db.rows[path]['user_title'] = 'Manually chosen title'
    before = deepcopy(db.rows)
    payload.update(
        status='completed', _notes_identity={'catalog_ids': [], 'frame_count': 1}, _notes_evidence_reprocess=True
    )
    monkeypatch.setattr(conversations_db, 'db', db)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *a: None)
    encoded = conversations_db._prepare_conversation_for_write(payload, UID, 'standard')
    assert not conversations_db.persist_processing_result_with_lifecycle.__wrapped__.__wrapped__(UID, encoded)
    assert db.rows == before
    assert not db.transactions[-1].creates and not db.transactions[-1].updates


def test_dismissed_person_is_not_recreated():
    person = {'id': 'synthetic-person', 'name': NAME, 'aliases': [], 'email': None, 'is_dismissed': True}
    _, transaction, _, segments = fixture({'synthetic-person': person})
    assert not transaction.creates and not transaction.updates
    assert segments[0].get('person_id') is None


def test_rejected_alias_is_not_recreated_without_a_model_binding():
    pid = person_id_for(NAME, EMAIL)
    person = {
        'id': pid,
        'name': NAME,
        'email': EMAIL,
        'aliases': ['Mo'],
        'notes_identity_identifiers': {CID: {'created': True, 'emails': [EMAIL], 'aliases': ['Mo']}},
    }
    person.update(identifier_retraction(person, CID))
    receipt = {
        'speakers': {
            '2': {
                'person_id': None,
                'is_user': False,
                'rejection': {'kind': 'not_person', 'person_id': pid},
                'generation': 1,
            }
        }
    }
    _, transaction, _, _ = fixture({pid: person}, {'name': 'Mo', 'source': 'screen', 'speaker_bindings': []}, receipt)
    assert not transaction.creates and not transaction.updates
