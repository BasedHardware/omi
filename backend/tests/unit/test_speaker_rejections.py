"""C4: explicit speaker rejections persist in the manual receipt and are honored.

The reject route writes the same ledger the tag sheet and tag prompts write:
a negative decision carrying ``rejection`` that clears automatic identity and
suppresses live matching until a newer positive decision wins.
"""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import logging
import os
import time
from types import SimpleNamespace

import fakeredis
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import _client as firestore_client_module
from database import conversations as db
from database import live_owner_continuity as continuity_cache
from database import voice_profiles as voice_profiles_db
from models.conversation import Conversation
from tests.unit.test_owner_recognition_reconnect import connect, speak, visible_owner, OWNER, DEVICE
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
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL
from utils.observability.owner_recognition import LIVE_SPEAKER_DECISIONS, OWNER_RECONNECT
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
    monkeypatch.setattr(firestore_client_module, 'get_firestore_client', lambda: store)
    path = ('users', UID, 'conversations', CONV)
    segments = [
        _segment('s0', 0, 5, is_user=False, person_id='p1', match='live_embedding'),
        _segment('s1', 6, 10),
        _segment('s2', 11, 15, speaker_id=7),
    ]
    store.rows[path] = dict(id=CONV, status='in_progress', transcript_segments=segments)
    for receiving in ('conversation', 'next'):
        store.rows[('users', UID, 'conversations', receiving)] = dict(id=receiving, status='in_progress')
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
    client = TestClient(app)
    # Initialize the ASGI/AnyIO transport during setup, outside route CPU guards.
    assert client.get('/').status_code == 404
    return SimpleNamespace(store=store, path=path, segments=segments, client=client)


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
        or (
            {'id': conversation_id, 'transcript_segments': [], 'owner_confirmation_prompt': {'origin': 'unnamed'}},
            [],
            [],
            [],
        ),
    )
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompt_answered', lambda *a: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **kwargs: None)
    service.apply_answer(
        UID,
        SpeakerTagPromptAnswerRequest(
            prompt_id='p',
            evidence_id='bound-evidence',
            kind=SpeakerTagPromptKind.owner_check,
            origin=SpeakerTagPromptOrigin.unnamed,
            conversation_id=CONV,
            speaker_id=4,
            segment_ids=['s0'],
            answer=SpeakerTagPromptAnswer.not_me,
        ),
    )
    assert captured[0]['rejection'] == {'kind': 'not_me', 'person_id': None}

    assert captured[0]['segment_ids'] == ['s0'] and captured[0]['segment_only']


def _matcher_host(emitted):
    async def _call(fn, *args):
        return fn(*args)

    return SimpleNamespace(
        request=SimpleNamespace(uid=UID, sample_rate=16000),
        state=SimpleNamespace(active=True, speaker_id_enabled=True, audio_ring_buffer=None),
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


@pytest.mark.parametrize('buffered', [False, True])
def test_matcher_keeps_a_nonrejected_mapping(world, buffered):
    db.assign_conversation_speaker(UID, CONV, speaker_id=4, rejection={'kind': 'not_me', 'person_id': None})
    emitted = []
    host = _matcher_host(emitted)
    matcher = listen_speakers.SpeakerMatcher(host)
    matcher._profile_conversation_id = CONV
    matcher.speaker_to_person[7] = ('p1', 'Sam')
    matcher._voice_scopes[7] = 'mapped-scope'
    if buffered:
        host.state.audio_ring_buffer = SimpleNamespace(get_time_range=lambda: (0.0, 60.0))

    asyncio.run(matcher.match(7, {'id': 's2', 'conversation_id': CONV, 'duration': 10, 'abs_start': 11, 'abs_end': 15}))
    assert matcher.speaker_to_person[7] == ('p1', 'Sam')
    assert bool(matcher.continuity.observed.get(('mapped-scope', 7))) == buffered
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
    monkeypatch.setattr(speaker_resolution, 'load_voiceprints_for_resolution', lambda uid, **kw: {})
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


@pytest.mark.parametrize('after_consumption', [False, True, 'accepted', 'rollover'])
def test_donor_correction_route_revokes_closed_socket_hint(world, monkeypatch, after_consumption):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(continuity_cache, '_client', lambda: client)
    monkeypatch.setattr(continuity_cache, 'get_firestore_client', lambda: world.store)

    async def run():
        old, host, _ = await connect(monkeypatch, [OWNER], uid=UID)
        old._profile_conversation_id = CONV

        async def read(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        host.persistence.call = read
        await speak(old, 4, 5, scope='old-socket')
        assert visible_owner(old, 4)
        assert continuity_cache.donor_authority(UID, CONV) == {}
        old.clear()  # donor socket is gone; no continuity.update(corrected_receipt)
        new = None
        if after_consumption:
            new, _, _ = await connect(monkeypatch, [OWNER, OWNER], uid=UID)
            assert new.continuity.donor
            new.host.persistence.call = read
            assert await new.continuity.authorize(), 'uncorrected donor must genuinely authorize reuse'
            if after_consumption in ('accepted', 'rollover'):
                await speak(new, 0, 2)
                assert visible_owner(new, 0)
        response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_me'})
        assert response.status_code == 200
        assert continuity_cache.donor_authority(UID, CONV)['generation'] == 1
        if new is None:
            new, _, _ = await connect(monkeypatch, [OWNER, OWNER], uid=UID)
        new.host.persistence.call = read
        if after_consumption == 'rollover':
            new.host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='new-socket'))
            await new.refresh_for_conversation(
                'next', owner_carry_scope='new-socket', owner_carry_donor={'id': 'conversation'}
            )
        elif after_consumption == 'accepted':
            monotonic = time.monotonic()
            monkeypatch.setattr(time, 'monotonic', lambda: monotonic + 31)
            new.observe_segment(0, 'new-socket', 'after-correction')
            await new.continuity.refresh()
            assert not visible_owner(new, 0), 'idle observation path must revoke without another embedding'
        else:
            await speak(new, 0, 2)
        assert not visible_owner(new, 0), 'persisted donor correction revokes even a consumed capsule'
        assert new.continuity.donor is None
        await speak(new, 0, 5 if after_consumption == 'rollover' else 3, start=3)
        assert visible_owner(new, 0), 'independent five-second recognition still works'

    asyncio.run(run())


async def _seed_closed_owner_donor(world, monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(continuity_cache, '_client', lambda: client)
    monkeypatch.setattr(continuity_cache, 'get_firestore_client', lambda: world.store)
    old, host, _ = await connect(monkeypatch, [OWNER], uid=UID)
    old._profile_conversation_id = CONV

    async def read(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host.persistence.call = read
    await speak(old, 4, 5, scope='old-socket')
    assert visible_owner(old, 4)
    assert continuity_cache.donor_authority(UID, CONV) == {}
    old.clear()


@pytest.mark.parametrize(
    'phase', ['acquire', 'rollover_profile', 'rollover_receipt', 'ordinary_peer', 'profile_recovery']
)
def test_final_short_authority_observes_correction_during_prior_await(world, monkeypatch, phase):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, _ = await connect(monkeypatch, [OWNER, noisy], uid=UID)
        reads = []
        corrected = False

        def correct():
            nonlocal corrected
            response = world.client.post(f'/v1/conversations/{CONV}/speakers/4/reject', json={'kind': 'not_me'})
            assert response.status_code == 200
            assert continuity_cache.donor_authority(UID, CONV)['generation'] == 1
            corrected = True

        async def read(fn, *args, **kwargs):
            reads.append(fn.__name__)
            if fn is db.get_conversation:
                return {'id': 'conversation'}
            if fn is db.get_manual_speaker_receipt and armed and not corrected:
                correct()
            return fn(*args, **kwargs)

        armed = phase == 'acquire'
        host.persistence.call = read
        if phase == 'acquire':
            await speak(new, 0, 2)
        else:
            await speak(new, 0, 2)
            assert visible_owner(new, 0), 'uncorrected donor must genuinely authorize the shortened owner'
            armed = phase != 'rollover_profile'
            if phase.startswith('rollover'):
                host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='new-socket'))

                async def load():
                    if phase == 'rollover_profile':
                        correct()
                    new.person_embeddings = {'user': {'embedding': OWNER.copy(), 'name': 'Owner'}}

                new._load_profiles = load
                new.note_rollover_carry(set())
                await new.refresh_for_conversation(
                    'next', owner_carry_scope='new-socket', owner_carry_donor={'id': 'conversation'}
                )
            elif phase == 'ordinary_peer':
                await speak(new, 1, 5, start=3)
            else:
                await new._reevaluate_loaded_owner()
        assert corrected
        assert reads[-1] == 'authority_snapshot', 'donor validation must follow the profile/current-receipt reads'
        assert not visible_owner(new, 0), 'a correction committed during awaited work must precede publication'
        assert new.continuity.donor is None

    asyncio.run(run())


@pytest.mark.parametrize('cancel', [False, True])
def test_pending_short_authority_keeps_shared_rows_coherent(world, monkeypatch, caplog, cancel):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, _ = await connect(monkeypatch, [noisy, OWNER], uid=UID)
        entered, release = asyncio.Event(), asyncio.Event()

        async def read(fn, *args, **kwargs):
            if fn is continuity_cache.authority_snapshot:
                entered.set()
                await release.wait()
            return fn(*args, **kwargs)

        host.persistence.call = read
        pending = asyncio.create_task(speak(new, 0, 2))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert 0 not in new._voice_distances and 0 not in new._voice_decisions
            assert 0 not in new._voice_centroids
            if cancel:
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
            await asyncio.wait_for(speak(new, 1, 5, start=3), 5)
            assert visible_owner(new, 1), 'ordinary recognition must work while a different probe waits or is cancelled'
            assert new._voice_distances.keys() <= new._voice_decisions.keys()
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)
        assert visible_owner(new, 1)
        assert 'type=KeyError' not in caplog.text

    asyncio.run(run())


@pytest.mark.parametrize('change', ['clear', 'profile', 'competing_voice'])
def test_final_authority_rebuilds_current_state_after_wait(world, monkeypatch, change):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        new, host, _ = await connect(monkeypatch, [OWNER, OWNER], uid=UID)
        entered, release = asyncio.Event(), asyncio.Event()

        async def read(fn, *args, **kwargs):
            if fn is continuity_cache.authority_snapshot:
                entered.set()
                await release.wait()
            return fn(*args, **kwargs)

        host.persistence.call = read
        pending = asyncio.create_task(speak(new, 0, 2))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            if change == 'clear':
                new.clear()
            elif change == 'profile':
                # Still similar enough for the enrolled threshold, but a new
                # enrollment cannot authorize the old session's shortcut.
                new.person_embeddings['user']['embedding'] = np.array([[0.99, 0.1]], dtype=np.float32)
            else:
                await asyncio.wait_for(speak(new, 1, 5, start=3), 5)
                assert visible_owner(new, 1)
        finally:
            release.set()
            await pending
        assert not visible_owner(new, 0)
        if change == 'competing_voice':
            assert not visible_owner(new, 1), 'the final arbitration must include the other voice that finished'
        assert new._voice_distances.keys() <= new._voice_decisions.keys()

    asyncio.run(run())


def test_manual_query_row_is_installed_coherently_after_name_lookup(world, monkeypatch):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        new, host, _ = await connect(monkeypatch, [OWNER], uid=UID)
        entered, release = asyncio.Event(), asyncio.Event()

        async def read(fn, *args, **kwargs):
            if fn is db.get_manual_speaker_receipt:
                return {'speakers': {'0': {'person_id': 'peer', 'is_user': False, 'generation': 1}}}
            if fn is continuity_cache.authority_snapshot:
                return {
                    conversation: (
                        {'speakers': {'0': {'person_id': 'peer', 'is_user': False, 'generation': 1}}}
                        if conversation == 'conversation'
                        else {}
                    )
                    for conversation in args[1]
                }
            if fn is listen_speakers.user_db.get_person:
                entered.set()
                await release.wait()
                return {'name': 'Peer'}
            return fn(*args, **kwargs)

        host.persistence.call = read
        pending = asyncio.create_task(speak(new, 0, 2))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert 0 not in new._voice_distances and 0 not in new._voice_decisions
        finally:
            release.set()
            await pending
        assert new.speaker_to_person[0] == ('peer', 'Peer')
        assert new._mapping_origin[0] == 'manual'
        assert 0 in new._voice_distances and 0 in new._voice_decisions
        assert new._voice_distances[0]['user'] == pytest.approx(0.0), 'manual voices still retain acoustic competition'

    asyncio.run(run())


@pytest.mark.parametrize('phase', ['acquire', 'reevaluate', 'rollover', 'mapped'])
def test_receiving_correction_during_final_authority_read_blocks_owner(world, monkeypatch, phase):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        receiving = 'next' if phase == 'rollover' else 'conversation'
        target = ('users', UID, 'conversations', receiving)
        world.store.rows[target]['transcript_segments'] = [_segment('current', 0, 2, speaker_id=0, scope='new-socket')]
        new, host, emitted = await connect(monkeypatch, [OWNER], uid=UID)
        armed = phase == 'acquire'
        corrected = False
        reads = []

        async def read(fn, *args, **kwargs):
            nonlocal corrected
            reads.append(fn.__name__)
            if fn is db.get_conversation:
                return {'id': 'conversation'}
            if (
                fn in (continuity_cache.donor_authority, continuity_cache.authority_snapshot)
                and armed
                and not corrected
            ):
                response = world.client.post(
                    f'/v1/conversations/{receiving}/speakers/0/reject', json={'kind': 'not_me'}
                )
                assert response.status_code == 200
                assert db.get_manual_speaker_receipt(UID, receiving)['generation'] == 1
                corrected = True
            return fn(*args, **kwargs)

        host.persistence.call = read
        if phase == 'acquire':
            await speak(new, 0, 2)
        else:
            await speak(new, 0, 2)
            assert visible_owner(new, 0)
            emitted.clear()
            armed = True
            if phase == 'reevaluate':
                await new._reevaluate_loaded_owner()
            elif phase == 'mapped':
                await new._drop_rejected_mapping(0, {'id': 'current'}, new._generation, receiving)
            else:
                host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='new-socket'))
                new.note_rollover_carry(set())
                await new.refresh_for_conversation(
                    receiving, owner_carry_scope='new-socket', owner_carry_donor={'id': 'conversation'}
                )
        assert corrected
        assert 'authority_snapshot' in reads
        assert not visible_owner(new, 0), 'receiving correction committed before the snapshot must veto publication'
        assert new._suggested_person.get(0) != 'user'
        assert not any(args[0] == 0 and args[1] == 'user' for args in emitted)
        assert new._voice_distances.keys() <= new._voice_decisions.keys()

    asyncio.run(run())


def test_authority_snapshot_binds_all_receipts_to_one_transaction(world, monkeypatch):
    from_read = type(world.store.collection('users').document(UID)).get
    transactions = []

    def read(ref, *args, **kwargs):
        transactions.append(kwargs.get('transaction'))
        return from_read(ref, *args, **kwargs)

    monkeypatch.setattr(type(world.store.collection('users').document(UID)), 'get', read)
    snapshots = continuity_cache.authority_snapshot(UID, ('conversation', CONV, 'next'), firestore_client=world.store)
    assert snapshots == {'conversation': {}, CONV: {}, 'next': {}}
    assert len(transactions) == 3 and transactions[0] is not None
    assert all(transaction is transactions[0] for transaction in transactions)
    assert not transactions[0].has_written


@pytest.mark.parametrize('seconds', [2, 5])
def test_immediate_rollover_donor_correction_during_snapshot_blocks_carry(world, monkeypatch, seconds):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        new, host, _ = await connect(monkeypatch, [OWNER], uid=UID)
        world.store.rows[('users', UID, 'conversations', 'conversation')]['transcript_segments'] = [
            _segment('current', 0, seconds, speaker_id=0, scope='new-socket')
        ]
        armed = False
        corrected = False

        async def read(fn, *args, **kwargs):
            nonlocal corrected
            if fn is db.get_conversation:
                return {'id': 'conversation'}
            if fn is continuity_cache.authority_snapshot and armed:
                response = world.client.post(
                    '/v1/conversations/conversation/speakers/0/reject', json={'kind': 'not_me'}
                )
                assert response.status_code == 200
                corrected = True
            return fn(*args, **kwargs)

        host.persistence.call = read
        await speak(new, 0, seconds)
        assert visible_owner(new, 0)
        host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='new-socket'))
        new.note_rollover_carry(set())
        armed = True
        await new.refresh_for_conversation(
            'next', owner_carry_scope='new-socket', owner_carry_donor={'id': 'conversation'}
        )
        assert corrected
        assert not visible_owner(
            new, 0
        ), 'the immediate donor is part of the same snapshot even for a five-second owner'

    asyncio.run(run())


@pytest.mark.parametrize('origin', ['manual', 'automatic'])
def test_failed_authority_snapshot_preserves_known_receiving_rejection(world, monkeypatch, origin):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        receiving = 'conversation'
        world.store.rows[('users', UID, 'conversations', receiving)]['transcript_segments'] = [
            _segment('current', 0, 5, speaker_id=0, scope='new-socket')
        ]
        if origin == 'manual':
            db.assign_conversation_speaker(UID, receiving, speaker_id=0, is_user=True, use_for_speech_training=False)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, emitted = await connect(monkeypatch, [OWNER, noisy, noisy], uid=UID)
        reads = []

        async def read(fn, *args, **kwargs):
            reads.append(fn.__name__)
            return fn(*args, **kwargs)

        host.persistence.call = read
        await speak(new, 0, 5)
        assert visible_owner(new, 0) and new._mapping_origin[0] == origin
        await speak(new, 1, 2, start=6)
        assert visible_owner(new, 0)
        assert sum(seconds for _, seconds in new.speaker_evidence[1]) == 2
        response = world.client.post(f'/v1/conversations/{receiving}/speakers/0/reject', json={'kind': 'not_me'})
        assert response.status_code == 200
        known = db.get_manual_speaker_receipt(UID, receiving)
        assert known['generation'] == (2 if origin == 'manual' else 1)
        assert 0 in manual_rejected_speakers(known)
        reference_type = type(world.store.collection('users').document(UID))
        original_read = reference_type.get
        failures = []

        def fail_transaction(ref, *args, **kwargs):
            if kwargs.get('transaction') is not None:
                failures.append(ref)
                raise ConnectionError('injected authority transaction failure')
            return original_read(ref, *args, **kwargs)

        monkeypatch.setattr(reference_type, 'get', fail_transaction)
        reads.clear()
        emitted.clear()
        if origin == 'manual':
            # An ordinary peer match must retract the corrected manual map too.
            await speak(new, 2, 5, start=9)
        else:
            # Five-second owners have no shortened proof whose revocation could hide this bug.
            await new.match(0, {'id': 'current'})
        assert reads == ['get_manual_speaker_receipt', 'authority_snapshot']
        assert failures
        assert not visible_owner(new, 0), 'unavailable authority must not erase a known receiving rejection'
        assert 0 not in new._mapping_origin and new._suggested_person.get(0) != 'user'
        assert new.host.state.speaker_map_dirty
        assert any(args[0] == 0 and args[1] == '' for args in emitted)
        assert not any(args[1] == 'user' for args in emitted)

    asyncio.run(run())


@pytest.mark.parametrize('seconds', [2, 5])
def test_failed_authority_snapshot_vetoes_new_owner_claim(world, monkeypatch, seconds):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, _ = await connect(monkeypatch, [noisy, OWNER], uid=UID)

        async def read(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        host.persistence.call = read
        await speak(new, 1, 2)
        assert new.continuity.donor is not None
        # Retained short evidence requires the final snapshot even for a fresh five-second query.
        reference_type = type(world.store.collection('users').document(UID))
        original_read = reference_type.get
        failures = []

        def fail_transaction(ref, *args, **kwargs):
            if kwargs.get('transaction') is not None:
                failures.append(ref)
                raise ConnectionError('injected authority transaction failure')
            return original_read(ref, *args, **kwargs)

        monkeypatch.setattr(reference_type, 'get', fail_transaction)
        await speak(new, 0, seconds, start=3)
        assert failures and not visible_owner(new, 0)
        assert new.continuity.donor is None and not new.continuity.accepted
        assert new._voice_distances.keys() <= new._voice_decisions.keys()

    asyncio.run(run())


@pytest.mark.parametrize('earlier', ['positive', 'negative', 'none'])
@pytest.mark.parametrize('origin', ['manual', 'automatic', 'carried'])
@pytest.mark.parametrize('seconds', [2, 5])
@pytest.mark.parametrize('snapshot_fails', [False, True], ids=['snapshot_ok', 'snapshot_fail'])
@pytest.mark.parametrize('correct_during_read', [False, True], ids=['unchanged', 'correction_during_read'])
def test_final_authority_publication_matrix(
    world, monkeypatch, earlier, origin, seconds, snapshot_fails, correct_during_read
):
    """Exercise fresh/manual naming, retained automatic evidence, and rollover carry.

    A positive manual receipt reserves the voice in the automatic/carry paths;
    only fresh matching installs that explicit manual decision. Failed final
    authority permits no publication or cache renewal in any of these paths.
    """

    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, emitted = await connect(monkeypatch, [noisy, OWNER], uid=UID)

        async def read(fn, *args, **kwargs):
            if fn is db.get_conversation:
                return {'id': 'conversation'}
            return fn(*args, **kwargs)

        host.persistence.call = read
        # Retained short competition forces a final snapshot for the 5s cases too.
        await speak(new, 1, 2)
        if origin != 'manual':
            await speak(new, 0, seconds, start=3)
            assert visible_owner(new, 0)
            if origin == 'automatic':
                # Retained evidence must pass the same gate when republished.
                new.speaker_to_person.pop(0)
                new._mapping_origin.pop(0)
        receiving = 'next' if origin == 'carried' else 'conversation'
        world.store.rows[('users', UID, 'conversations', receiving)]['transcript_segments'] = [
            _segment('current', 0, seconds, speaker_id=0, scope='new-socket')
        ]
        if earlier == 'positive':
            db.assign_conversation_speaker(UID, receiving, speaker_id=0, is_user=True, use_for_speech_training=False)
        elif earlier == 'negative':
            response = world.client.post(f'/v1/conversations/{receiving}/speakers/0/reject', json={'kind': 'not_me'})
            assert response.status_code == 200
        known = db.get_manual_speaker_receipt(UID, receiving)
        reference_type = type(world.store.collection('users').document(UID))
        original_read = reference_type.get
        transactional_reads = []
        correcting = False

        def final_read(ref, *args, **kwargs):
            nonlocal correcting
            if kwargs.get('transaction') is not None and not correcting:
                first_read = not transactional_reads
                transactional_reads.append(ref)
                if first_read and correct_during_read:
                    # The real correction's own transaction must remain usable.
                    correcting = True
                    try:
                        response = world.client.post(
                            f'/v1/conversations/{receiving}/speakers/0/reject', json={'kind': 'not_me'}
                        )
                        assert response.status_code == 200
                    finally:
                        correcting = False
                if snapshot_fails:
                    raise ConnectionError('injected final authority read failure')
            return original_read(ref, *args, **kwargs)

        monkeypatch.setattr(reference_type, 'get', final_read)
        earlier_reads = []

        async def capture_read(fn, *args, **kwargs):
            value = await read(fn, *args, **kwargs)
            if fn is db.get_manual_speaker_receipt:
                earlier_reads.append(deepcopy(value))
            return value

        host.persistence.call = capture_read
        renewals = []
        update = new.continuity.update

        async def capture_update(*args, **kwargs):
            renewals.append(args)
            await update(*args, **kwargs)

        monkeypatch.setattr(new.continuity, 'update', capture_update)
        emitted.clear()
        if origin == 'manual':
            await speak(new, 0, seconds, start=3)
        elif origin == 'automatic':
            await new._reevaluate_loaded_owner()
        else:
            host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='new-socket'))
            new.note_rollover_carry(set())
            await new.refresh_for_conversation(
                receiving, owner_carry_scope='new-socket', owner_carry_donor={'id': 'conversation'}
            )
        assert earlier_reads == [known]
        assert transactional_reads, 'every table row must exercise the final authority transaction'
        expected_owner = (
            not snapshot_fails
            and not correct_during_read
            and (earlier == 'none' or (earlier == 'positive' and origin == 'manual'))
        )
        assert visible_owner(new, 0) == expected_owner
        if expected_owner:
            assert new._mapping_origin[0] == ('manual' if earlier == 'positive' else 'automatic')
        else:
            assert new._suggested_person.get(0) != 'user'
            assert not any(args[1] == 'user' for args in emitted)
        if snapshot_fails:
            assert not renewals, 'unavailable authority must not renew any owner continuity publication'
            if origin == 'carried':
                assert new._embedding_attempts.get(0, 0) == 0, 'failed carry keeps the fresh conversation allowance'
        assert new._voice_distances.keys() <= new._voice_decisions.keys()

    asyncio.run(run())


@pytest.mark.parametrize('mode,seconds', [('mapped', 2), ('mapped', 5), ('idle', 2)])
def test_unavailable_authority_cannot_renew_an_existing_owner(world, monkeypatch, mode, seconds):
    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, emitted = await connect(monkeypatch, [noisy, OWNER], uid=UID)

        async def read(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        host.persistence.call = read
        await speak(new, 1, 2)
        await speak(new, 0, seconds, start=3)
        assert visible_owner(new, 0)
        reference_type = type(world.store.collection('users').document(UID))
        original_read = reference_type.get
        failures = []

        def fail_final_read(ref, *args, **kwargs):
            if kwargs.get('transaction') is not None:
                failures.append(ref)
                raise ConnectionError('injected final authority read failure')
            return original_read(ref, *args, **kwargs)

        monkeypatch.setattr(reference_type, 'get', fail_final_read)
        mapping = dict(new.speaker_to_person)
        observed = dict(new.continuity.observed)
        revision = new.continuity._revision
        emitted.clear()
        if mode == 'mapped':
            await new.match(0, {'id': 'current', 'abs_start': 3, 'abs_end': 3 + seconds})
        else:
            new.continuity._last_authority_check -= 31
            # Exercise the continuation with a pending cache write due, too.
            monkeypatch.setattr(new.continuity, 'refresh_due', lambda: True)
            reads = []

            async def capture_read(fn, *args, **kwargs):
                reads.append(fn.__name__)
                return await read(fn, *args, **kwargs)

            host.persistence.call = capture_read
            await new.continuity.refresh()
            assert reads == ['get_manual_speaker_receipt', 'authority_snapshot']
        assert failures
        assert new.speaker_to_person == mapping, 'unknown authority permits neither republishing nor new retraction'
        assert new.continuity.observed == observed, 'failed authority must not renew the owner speech gap'
        assert new.continuity._revision == revision, 'failed authority must not write a refreshed capsule'
        assert not emitted

    asyncio.run(run())


@pytest.mark.parametrize('seconds', [2, 5])
@pytest.mark.parametrize('known_rejection', [False, True])
def test_authority_veto_accounts_for_one_spent_embedding(world, monkeypatch, caplog, seconds, known_rejection):
    """The round-6 five-second probe must exit measurably without an acoustic decision."""

    async def run():
        await _seed_closed_owner_donor(world, monkeypatch)
        noisy = np.array([[-1.0, 0.0]], dtype=np.float32)
        new, host, emitted = await connect(monkeypatch, [noisy, OWNER], uid=UID)

        async def read(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        host.persistence.call = read
        # Short peer evidence forces final authority even for the ordinary 5s query.
        await speak(new, 1, 2)
        if known_rejection:
            world.store.rows[('users', UID, 'conversations', 'conversation')]['transcript_segments'] = [
                _segment('manual', 0, 5, speaker_id=2, scope='new-socket')
            ]
            db.assign_conversation_speaker(
                UID, 'conversation', speaker_id=2, is_user=True, use_for_speech_training=False
            )
            new.speaker_to_person[2] = ('user', 'Owner')
            new._mapping_origin[2] = 'manual'
            new._voice_segments[2] = 'manual'
            response = world.client.post('/v1/conversations/conversation/speakers/2/reject', json={'kind': 'not_me'})
            assert response.status_code == 200

        reference_type = type(world.store.collection('users').document(UID))
        original_read = reference_type.get
        failures = []

        def fail_final_read(ref, *args, **kwargs):
            if kwargs.get('transaction') is not None:
                failures.append(ref)
                raise ConnectionError('injected final authority read failure')
            return original_read(ref, *args, **kwargs)

        monkeypatch.setattr(reference_type, 'get', fail_final_read)
        renewals = []

        async def capture_update(*args, **kwargs):
            renewals.append(args)

        monkeypatch.setattr(new.continuity, 'update', capture_update)

        def total(counter):
            return sum(
                sample.value
                for metric in counter.collect()
                for sample in metric.samples
                if sample.name.endswith('_total')
            )

        before = (total(LIVE_SPEAKER_DECISIONS), total(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL))
        exit_before = OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason='authority_unavailable')._value.get()
        reconnect = OWNER_RECONNECT.labels(outcome='rejected', reason='arbitration')
        reconnect_before = reconnect._value.get()
        emitted.clear()
        with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
            await speak(new, 0, seconds, start=3)
        after = (total(LIVE_SPEAKER_DECISIONS), total(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL))
        assert failures and new._embedding_attempts[0] == 1
        assert after == (
            before[0],
            before[1] + 1,
        ), 'each spent attempt needs exactly one live exit, not a fabricated decision'
        assert OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason='authority_unavailable')._value.get() == exit_before + 1
        assert (
            sum('speaker_id_exit reason=authority_unavailable speaker=0 ' in row.message for row in caplog.records) == 1
        )
        assert reconnect._value.get() == reconnect_before + (seconds == 2)
        assert not visible_owner(new, 0) and not renewals
        assert not any(args[1] == 'user' for args in emitted)
        if known_rejection:
            assert not visible_owner(new, 2) and 2 not in new._mapping_origin
            assert any(args[0] == 2 and args[1] == '' for args in emitted)

    asyncio.run(run())
