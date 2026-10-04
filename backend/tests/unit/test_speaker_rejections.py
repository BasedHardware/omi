"""C4: explicit speaker rejections persist in the manual receipt and are honored.

The reject route writes the same ledger the tag sheet and tag prompts write:
a negative decision carrying ``rejection`` that clears automatic identity and
suppresses live matching until a newer positive decision wins.
"""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import os
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as db
from database import voice_profiles as voice_profiles_db
from models.conversation import Conversation
from models.structured import Structured
from routers import speaker_labels as speaker_labels_router
from routers.listen import speakers as listen_speakers
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import speaker_resolution
from utils.manual_speaker_assignments import apply_manual_assignments, manual_rejected_speakers
from utils.other import endpoints as auth
from utils.conversations.speaker_resolution import _manual_speakers
from utils.speaker_assignment_teaching import commit_manual_assignment
from utils import speaker_assignment_teaching as teaching
from utils.speaker_tag_prompts import service
from utils.speaker_tag_prompts.selection import _manually_decided
from utils.stt.speaker_match import SpeakerMatchDecision
from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswer,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptKind,
    SpeakerTagPromptOrigin,
)

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

UID = 'uid-rejections'
CONV = 'conv-r'
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _segment(seg_id, start, end, *, speaker_id=4, is_user=False, person_id=None, scope=None, match=None):
    segment = {
        'id': seg_id,
        'start': start,
        'end': end,
        'speaker_id': speaker_id,
        'is_user': is_user,
        'person_id': person_id,
        'text': 'words',
    }
    if scope:
        segment['speaker_id_scope'] = scope
    if match:
        segment['speaker_match_source'] = match
    return segment


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    path = ('users', UID, 'conversations', CONV)
    segments = [
        _segment('s0', 0, 5, is_user=False, person_id='p1', match='live_embedding'),
        _segment('s1', 6, 10),
        _segment('s2', 11, 15, speaker_id=7),
    ]
    store.rows[path] = dict(id=CONV, status='in_progress', transcript_segments=segments)
    store.rows[('users', UID, 'people', 'p1')] = dict(id='p1', name='Sam', speaker_embedding=[1.0, 0.0])
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(voice_profiles_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(
        speaker_labels_router,
        'deserialize_conversation',
        lambda raw: Conversation(
            id=raw['id'],
            created_at=NOW,
            started_at=NOW,
            finished_at=NOW,
            structured=Structured(title='t', overview='o'),
            transcript_segments=[{**{'is_user': False}, **s} for s in raw['transcript_segments']],
        ),
    )
    app = FastAPI()
    app.include_router(speaker_labels_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return SimpleNamespace(store=store, path=path, segments=segments, client=TestClient(app))


def receipt(world):
    raw = deepcopy(world.store.rows[world.path])
    return db.decode_manual_speaker_assignments(
        UID, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )


@pytest.mark.parametrize('kind', ['not_me', 'not_person', 'not_a_person'])
def test_reject_route_persists_a_durable_receipt(world, kind):
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject',
        json={'kind': kind, 'person_id': 'p1' if kind == 'not_person' else None},
    )
    assert response.status_code == 200
    entry = receipt(world)['speakers']['4']
    assert entry['rejection'] == {'kind': kind, 'person_id': 'p1' if kind == 'not_person' else None}
    assert entry['is_user'] is False and entry['person_id'] is None
    assert entry['use_for_speech_training'] is False
    assert receipt(world)['generation'] == 1


def test_rejection_clears_the_automatic_person_label(world):
    world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person', 'person_id': 'p1'})
    saved = deepcopy(world.store.rows[world.path])
    raw = db._decrypt_conversation_data(saved, UID)
    assert raw['transcript_segments'][0]['person_id'] is None
    assert raw['transcript_segments'][0]['is_user'] is False
    assert raw['transcript_segments'][0]['speaker_match_source'] is None
    assert raw['transcript_segments'][0]['speaker_label_source'] is None
    assert raw['transcript_segments'][2]['person_id'] is None


def test_rejection_receipt_survives_a_completed_conversation(world):
    world.store.rows[world.path]['status'] = 'completed'
    response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_me'})
    assert response.status_code == 200
    assert receipt(world)['speakers']['4']['rejection']['kind'] == 'not_me'


def test_selected_segment_rejection_validates_the_requested_speaker(world):
    before = deepcopy(world.store.rows)
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject',
        json={'kind': 'not_me', 'segment_ids': ['s0', 's2']},
    )
    assert response.status_code == 409
    assert world.store.rows == before
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject',
        json={'kind': 'not_me', 'segment_ids': ['s0', 'missing']},
    )
    assert response.status_code == 409
    assert world.store.rows == before


def test_selected_rejection_writes_segment_entries_with_speaker_id(world):
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject',
        json={'kind': 'not_me', 'segment_ids': ['s0', 's1']},
    )
    assert response.status_code == 200
    entries = receipt(world)['segments']
    assert entries['s0']['rejection']['kind'] == 'not_me' and entries['s0']['speaker_id'] == 4
    assert entries['s1']['rejection']['kind'] == 'not_me'
    assert 'speakers' not in receipt(world)


def test_not_person_requires_person_id(world):
    response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person'})
    assert response.status_code == 422


def test_not_person_rejects_a_missing_person(world, monkeypatch):
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person', 'person_id': 'foreign'}
    )
    assert response.status_code == 404
    assert receipt(world) == {}


def test_not_person_is_free_on_every_plan(world, monkeypatch):
    # Correcting a label in your own transcript is not a paid action; only
    # automatic naming (prompts, earlier matches) follows the entitlement.
    monkeypatch.setattr('utils.speaker_permissions.users_db.get_user_valid_subscription', lambda uid, **kwargs: None)
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person', 'person_id': 'p1'}
    )
    assert response.status_code == 200
    assert receipt(world) != {}


def test_locked_and_deleted_conversations_reject(world):
    world.store.rows[world.path]['is_locked'] = True
    response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_me'})
    assert response.status_code == 402
    assert receipt(world) == {}
    world.store.rows[world.path] = dict(id=CONV, deleted=True)
    response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_me'})
    assert response.status_code == 404


def test_not_a_person_records_the_ignored_voice_marker(world):
    response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_a_person'})
    assert response.status_code == 200
    state = voice_profiles_db.get_tag_prompt_state(UID, firestore_client=world.store)
    markers = voice_profiles_db.ignored_voices(state)
    assert [(m['conversation_id'], m['speaker_id']) for m in markers] == [(CONV, 4)]
    assert markers[0]['assignment_generation'] == receipt(world)['generation']


def test_not_person_counts_one_auto_correction_per_conversation(world):
    world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person', 'person_id': 'p1'})
    world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person', 'person_id': 'p1'})
    person = world.store.rows[('users', UID, 'people', 'p1')]
    assert person['label_evidence']['auto_corrected'] == 1


def test_rejection_invalidates_a_profile_taught_from_the_voice(world):
    world.store.rows[('users', UID, 'people', 'p1')] = dict(
        id='p1',
        name='Sam',
        speaker_embedding=[1.0, 0.0],
        speech_samples=['a.wav'],
        speech_sample_source=dict(conversation_id=CONV, segment_ids=['s0']),
    )
    world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_person', 'person_id': 'p1'})
    person = world.store.rows[('users', UID, 'people', 'p1')]
    assert person['speaker_embedding'] is None and person['speech_samples'] == []


def test_newer_positive_decision_overrides_the_rejection(world):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    assert manual_rejected_speakers(receipt(world)) != {}
    db.assign_conversation_speaker(UID, CONV, person_id='p1', speaker_id=4)
    assert manual_rejected_speakers(receipt(world)) == {}


def test_rejected_voice_is_anonymous_in_processing_and_prompts(world):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    current = deepcopy(world.store.rows[world.path])
    current['manual_speaker_assignments'] = receipt(world)
    decided_speakers, decided_segments = _manually_decided(current)
    assert '4' in decided_speakers
    identities = _manual_speakers(current['manual_speaker_assignments'])
    assert identities[4].person_id is None and not identities[4].is_user
    assert identities[4].anonymous_key == 4


def test_selected_rejection_blocks_the_voice_in_processing(world):
    db.assign_conversation_speaker(
        UID, CONV, speaker_id=4, segment_ids=['s0', 's1'], rejection={'kind': 'not_me', 'person_id': None}
    )
    identities = _manual_speakers(receipt(world))
    assert identities[4].anonymous_key == 4


def test_tag_prompt_not_me_on_an_unnamed_voice_writes_the_ledger(world, monkeypatch):
    captured = []
    monkeypatch.setattr(
        service.conversations_db,
        'assign_conversation_speaker',
        lambda uid, conversation_id, **kwargs: captured.append(kwargs)
        or ({'id': conversation_id, 'transcript_segments': []}, [], [], []),
    )
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompt_answered', lambda *a: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **kwargs: None)
    service.apply_answer(
        UID,
        SpeakerTagPromptAnswerRequest(
            prompt_id='p',
            kind=SpeakerTagPromptKind.owner_check,
            origin=SpeakerTagPromptOrigin.unnamed,
            conversation_id=CONV,
            speaker_id=4,
            segment_ids=['s0'],
            answer=SpeakerTagPromptAnswer.not_me,
        ),
    )
    assert captured[0]['rejection'] == {'kind': 'not_me', 'person_id': None}


def _matcher_host(emitted):
    async def _call(fn, *args):
        return fn(*args)

    return SimpleNamespace(
        request=SimpleNamespace(uid=UID, sample_rate=16000),
        state=SimpleNamespace(active=True, speaker_id_enabled=True),
        persistence=SimpleNamespace(call=_call),
        emit_speaker_suggestion=lambda *a, **k: emitted.append((a, k)),
        limits=SimpleNamespace(speaker_id_min_audio=1.0),
        spawn=lambda coro, name=None: coro.close() or SimpleNamespace(add_done_callback=lambda f: None),
        private_cloud_sync_enabled=False,
        send_speaker_sample_request=None,
        recording_session_id='rec-1',
        has_speech_profile=False,
    )


def test_matcher_publishes_nothing_for_a_rejected_voice(world, monkeypatch):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    emitted = []
    host = _matcher_host(emitted)
    matcher = listen_speakers.SpeakerMatcher(host)
    matcher._profile_conversation_id = CONV
    matcher._suggested_person[4] = 'p1'
    matcher.voice_candidates[4] = [{'person_id': 'p1', 'level': 3}]
    host.state.audio_ring_buffer = SimpleNamespace(
        get_time_range=lambda: (0.0, 60.0), extract=lambda a, b: b'\x01\x00' * 16000
    )
    monkeypatch.setattr(listen_speakers, 'extract_embedding_from_bytes', lambda *a, **k: np.array([[1.0, 0.0]]))
    matcher.person_embeddings['p1'] = {'embedding': np.array([[1.0, 0.0]]), 'name': 'Sam'}
    matcher.speaker_evidence[4] = deque([(np.array([[1.0, 0.0]]), 10.0)])

    asyncio.run(matcher.match(4, {'id': 's0', 'conversation_id': CONV, 'duration': 10, 'abs_start': 0, 'abs_end': 10}))
    assert 4 not in matcher.speaker_to_person
    assert 4 not in matcher._suggested_person and 4 not in matcher.voice_candidates
    assert matcher.voice_identity_status.get(4) is not None
    assert emitted and all(kwargs.get('retracted') for _args, kwargs in emitted)


def test_matcher_drops_an_already_mapped_rejected_voice(world):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    emitted = []
    host = _matcher_host(emitted)
    matcher = listen_speakers.SpeakerMatcher(host)
    matcher._profile_conversation_id = CONV
    matcher.speaker_to_person[4] = ('p1', 'Sam')
    matcher._suggested_person[4] = 'p1'

    asyncio.run(matcher.match(4, {'id': 's0', 'conversation_id': CONV, 'duration': 10, 'abs_start': 0, 'abs_end': 10}))
    assert 4 not in matcher.speaker_to_person
    assert 4 not in matcher._suggested_person
    assert matcher.voice_identity_status[4].value == 'no_match'
    assert emitted and all(kwargs.get('retracted') for _args, kwargs in emitted)


def test_matcher_keeps_a_nonrejected_mapping(world):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    emitted = []
    host = _matcher_host(emitted)
    matcher = listen_speakers.SpeakerMatcher(host)
    matcher._profile_conversation_id = CONV
    matcher.speaker_to_person[7] = ('p1', 'Sam')

    asyncio.run(matcher.match(7, {'id': 's2', 'conversation_id': CONV, 'duration': 10, 'abs_start': 11, 'abs_end': 15}))
    assert matcher.speaker_to_person[7] == ('p1', 'Sam')
    assert not emitted


def test_empty_segment_ids_is_rejected(world):
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_me', 'segment_ids': []}
    )
    assert response.status_code == 422


def test_not_me_ignores_an_extraneous_person_id(world):
    response = world.client.post(
        f'/v1/conversations/{CONV}/speakers/7/reject', json={'kind': 'not_me', 'person_id': 'p1'}
    )
    assert response.status_code == 200
    entry = receipt(world)['speakers']['7']
    assert entry['rejection'] == {'kind': 'not_me', 'person_id': None}
    assert 'label_evidence' not in world.store.rows[('users', UID, 'people', 'p1')]


def test_selected_rejection_overlays_the_whole_voice(world):
    db.assign_conversation_speaker(
        UID, CONV, speaker_id=4, segment_ids=['s0'], rejection={'kind': 'not_person', 'person_id': 'p1'}
    )
    saved = deepcopy(world.store.rows[world.path])
    raw = db._decrypt_conversation_data(saved, UID)
    assert raw['transcript_segments'][0]['person_id'] is None
    assert raw['transcript_segments'][1]['person_id'] is None
    assert raw['transcript_segments'][1]['speaker_identity_status'] == 'unknown'


def test_rejected_voice_stays_unnamed_for_appended_segments(world):
    db.assign_conversation_speaker(
        UID, CONV, speaker_id=4, segment_ids=['s0'], rejection={'kind': 'not_me', 'person_id': None}
    )
    appended = [_segment('s3', 20, 25, person_id='p1', match='live_embedding')]
    overlaid = apply_manual_assignments(appended, receipt(world))
    assert overlaid[0]['person_id'] is None and overlaid[0]['speaker_match_source'] is None


def _scoped_rejection_world(world):
    segments = [
        _segment('s0', 0, 5, person_id='p1', match='live_embedding', scope='sync:chunk'),
        _segment('s1', 6, 10, person_id='p1', match='live_embedding', scope='sync:chunk'),
    ]
    world.store.rows[world.path]['transcript_segments'] = deepcopy(segments)
    db.assign_conversation_speaker(
        UID, CONV, speaker_id=4, segment_ids=['s0'], rejection={'kind': 'not_person', 'person_id': 'p1'}
    )
    conversation = Conversation(
        id=CONV,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured=Structured(title='t', overview='o'),
        transcript_segments=deepcopy(segments),
        private_cloud_sync_enabled=True,
    )
    return conversation


def test_processing_overlay_neutralizes_the_whole_rejected_voice(world, monkeypatch):
    conversation = _scoped_rejection_world(world)
    monkeypatch.setattr(
        speaker_resolution.conversations_db,
        'get_manual_speaker_receipt',
        lambda uid, cid: receipt(world),
    )
    monkeypatch.setattr(speaker_resolution, 'resolution_enabled', lambda: False)
    applied = speaker_resolution.resolve_speakers_for_processing(UID, conversation)
    assert applied
    by_id = {s.id: s for s in conversation.transcript_segments}
    assert by_id['s0'].person_id is None and by_id['s1'].person_id is None
    assert by_id['s0'].speaker_identity_status == 'unknown'
    assert by_id['s1'].speaker_identity_status == 'unknown'


def test_processing_resolution_keeps_the_whole_rejected_voice_unnamed(world, monkeypatch):
    conversation = _scoped_rejection_world(world)
    monkeypatch.setattr(
        speaker_resolution.conversations_db,
        'get_manual_speaker_receipt',
        lambda uid, cid: receipt(world),
    )
    monkeypatch.setattr(speaker_resolution, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(speaker_resolution, 'load_voiceprints_for_resolution', lambda uid: {})
    vector = np.array([1.0, 0.0], dtype=np.float32)
    cache = speaker_resolution.encode_cache(
        {'s0': (5.0, vector), 's1': (4.0, np.array([0.99, 0.01], dtype=np.float32))}
    )
    monkeypatch.setattr(speaker_resolution, 'download_speaker_embedding_cache', lambda uid, cid: cache)
    monkeypatch.setattr(speaker_resolution, 'upload_speaker_embedding_cache', lambda *a, **k: None)
    applied = speaker_resolution.resolve_speakers_for_processing(UID, conversation)
    assert applied
    by_id = {s.id: s for s in conversation.transcript_segments}
    assert by_id['s0'].person_id is None and by_id['s0'].is_user is False
    assert by_id['s1'].person_id is None and by_id['s1'].is_user is False


def test_rejection_spillover_fences_profiles_taught_from_unselected_segments(world):
    world.store.rows[world.path]['transcript_segments'][1]['person_id'] = 'p1'
    world.store.rows[world.path]['transcript_segments'][1]['speaker_match_source'] = 'live_embedding'
    world.store.rows[('users', UID, 'people', 'p2')] = dict(id='p2', name='Jo')
    world.store.rows[('users', UID, 'people', 'p1')] = dict(
        id='p1',
        name='Sam',
        speaker_embedding=[1.0, 0.0],
        speech_samples=['b.wav'],
        speech_sample_source=dict(conversation_id=CONV, segment_ids=['s1']),
    )
    db.assign_conversation_speaker(
        UID, CONV, speaker_id=4, segment_ids=['s0'], rejection={'kind': 'not_person', 'person_id': 'p2'}
    )
    person = world.store.rows[('users', UID, 'people', 'p1')]
    assert person['speaker_embedding'] is None and person['speech_samples'] == []


def test_is_user_false_from_assign_routes_records_not_me(world, monkeypatch):
    captured = []
    monkeypatch.setattr(
        teaching.conversations_db,
        'assign_conversation_speaker',
        lambda uid, conversation_id, **kwargs: captured.append(kwargs)
        or ({'id': conversation_id, 'transcript_segments': []}, [], [], []),
    )
    commit_manual_assignment(
        UID, CONV, person_id=None, is_user=False, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None}
    )
    assert captured[0]['rejection'] == {'kind': 'not_me', 'person_id': None}


def test_identify_someone_else_writes_a_plain_anonymous_decision(world, monkeypatch):
    captured = []
    monkeypatch.setattr(
        service.conversations_db,
        'assign_conversation_speaker',
        lambda uid, conversation_id, **kwargs: captured.append(kwargs)
        or ({'id': conversation_id, 'transcript_segments': []}, [], [], []),
    )
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompt_answered', lambda *a: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **kwargs: None)
    monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: True)
    service.apply_answer(
        UID,
        SpeakerTagPromptAnswerRequest(
            prompt_id='p',
            kind=SpeakerTagPromptKind.identify,
            origin=SpeakerTagPromptOrigin.unnamed,
            conversation_id=CONV,
            speaker_id=4,
            segment_ids=['s0'],
            answer=SpeakerTagPromptAnswer.someone_else,
        ),
    )
    assert 'rejection' not in captured[0]
    assert captured[0]['person_id'] is None and captured[0]['is_user'] is False
    assert captured[0]['use_for_speech_training'] is False


def test_confirm_person_someone_else_requires_a_known_suggestion(world, monkeypatch):
    captured = []
    monkeypatch.setattr(
        service.conversations_db,
        'assign_conversation_speaker',
        lambda uid, conversation_id, **kwargs: captured.append(kwargs)
        or ({'id': conversation_id, 'transcript_segments': []}, [], [], []),
    )
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompt_answered', lambda *a: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **kwargs: None)
    monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: True)
    request = SpeakerTagPromptAnswerRequest(
        prompt_id='p',
        kind=SpeakerTagPromptKind.confirm_person,
        origin=SpeakerTagPromptOrigin.auto_person,
        conversation_id=CONV,
        speaker_id=4,
        segment_ids=['s0'],
        answer=SpeakerTagPromptAnswer.someone_else,
    )
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer(UID, request)
    request = SpeakerTagPromptAnswerRequest(**{**request.model_dump(), 'suggested_person_id': 'p1'})
    service.apply_answer(UID, request)
    assert captured[0]['rejection'] == {'kind': 'not_person', 'person_id': 'p1'}


def test_donor_selection_must_resolve_every_requested_id(world):
    store = world.store
    donor = ('users', UID, 'conversations', 'donor')
    survivor = ('users', UID, 'conversations', CONV)
    rejection = {'kind': 'not_me', 'person_id': None}
    store.rows[donor] = dict(
        id='donor',
        deleted=True,
        sync_merged_into=CONV,
        transcript_segments=[
            _segment('d0', 0, 5, speaker_id=4),
            _segment('d1', 6, 10, speaker_id=7),
        ],
    )
    with pytest.raises(ValueError):
        db.assign_conversation_speaker(UID, 'donor', speaker_id=4, segment_ids=['d0', 'd1'], rejection=rejection)
    with pytest.raises(ValueError):
        db.assign_conversation_speaker(UID, 'donor', speaker_id=4, segment_ids=['d0', 'missing'], rejection=rejection)
    with pytest.raises(ValueError):
        db.assign_conversation_speaker(UID, 'donor', speaker_id=4, segment_ids=['d0', 'missing'], person_id='p1')
    store.rows[donor]['transcript_segments'].append(_segment('d9', 11, 15, speaker_id=4))
    store.rows[survivor]['transcript_segments'] = [_segment('d0', 0, 5, speaker_id=4)]
    with pytest.raises(ValueError):
        db.assign_conversation_speaker(UID, 'donor', speaker_id=4, segment_ids=['d0', 'd9'], rejection=rejection)
    raw, resolved, _, _ = db.assign_conversation_speaker(UID, 'donor', speaker_id=4, segment_ids=['d0'], person_id='p1')
    assert raw['id'] == CONV and resolved == ['d0']
    assert receipt(world)['segments']['d0']['person_id'] == 'p1'


def test_rejected_voice_cannot_contend_the_owner(world, monkeypatch):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    emitted = []
    host = _matcher_host(emitted)
    matcher = listen_speakers.SpeakerMatcher(host)
    matcher._profile_conversation_id = CONV
    matcher._voice_distances[4] = {'user': 0.0}
    matcher._voice_decisions[4] = SpeakerMatchDecision(
        person_id='user', best_id='user', best_distance=0.0, runner_up_distance=1.0
    )
    matcher._voice_segments[4] = 's0'
    host.state.audio_ring_buffer = SimpleNamespace(
        get_time_range=lambda: (0.0, 60.0), extract=lambda a, b: b'\x01\x00' * 16000
    )
    monkeypatch.setattr(listen_speakers, 'extract_embedding_from_bytes', lambda *a, **k: np.array([[1.0, 0.0]]))
    matcher.person_embeddings['user'] = {'embedding': np.array([[1.0, 0.0]]), 'name': 'The User'}
    matcher.speaker_evidence[5] = deque([(np.array([[1.0, 0.0]]), 10.0)])

    asyncio.run(matcher.match(5, {'id': 's9', 'conversation_id': CONV, 'duration': 10, 'abs_start': 0, 'abs_end': 10}))
    assert matcher.speaker_to_person.get(5) == ('user', 'The User')
    assert matcher.voice_identity_status[5].value == 'user'
    assert matcher.voice_identity_status[4].value == 'no_match'
    assert any(args[0] == 5 and args[1] == 'user' for args, kwargs in emitted if not kwargs.get('retracted'))
