"""Synthetic endpoint/transaction acceptance for the excerpt authorization boundary."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import owner_confirmation as owner_confirmation_db
from database import conversations as db
from models.speaker_tag_prompts import SpeakerTagPrompt, SpeakerTagPromptAnswerRequest
from routers import speaker_tag_prompts as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.manual_speaker_assignments import apply_manual_assignments, manual_owner_reserved, manual_rejected_speakers
from utils.speaker_tag_prompts import selection, service
from utils.speaker_tag_prompts.owner_confirmation import FIELD, StaleOwnerConfirmation, binding_for
from utils.owner_voice_evidence import authorized_owner_segments
from utils.stt.speaker_match import arbitrate_owner_matches, select_speaker_match
from utils.conversations.speaker_resolution import _manual_speakers

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


def conversation():
    return dict(
        id='c',
        status='completed',
        started_at=NOW - timedelta(hours=1),
        audio_files=[dict(chunk_timestamps=[(NOW - timedelta(hours=1)).timestamp()], duration=60)],
        transcript_segments=[
            dict(
                id='played',
                speaker_id=1,
                speaker_id_scope='capture:a',
                text='Synthetic played excerpt',
                start=0.0,
                end=6.0,
                is_user=False,
                person_id=None,
            ),
            dict(
                id='sibling',
                speaker_id=1,
                speaker_id_scope='capture:a',
                text='Unplayed automatic owner',
                start=10.0,
                end=16.0,
                is_user=True,
                person_id=None,
            ),
            dict(
                id='other',
                speaker_id=2,
                speaker_id_scope='capture:a',
                text='Unplayed other owner',
                start=20.0,
                end=26.0,
                is_user=True,
                person_id=None,
            ),
        ],
    )


def card(raw):
    return SpeakerTagPrompt(
        id=selection.prompt_id('c', 1, selection.SpeakerTagPromptKind.owner_check),
        kind='owner_check',
        origin='unnamed',
        conversation_id='c',
        speaker_id=1,
        segment_ids=['played'],
        clip_start=0,
        clip_end=6,
    )


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    raw = conversation()
    store.rows[path] = deepcopy(raw)
    store.rows[('users', 'u')] = dict(speaker_embedding=[1.0, 0.0])
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda uid: None)
    monkeypatch.setattr(db, 'record_speaker_review', lambda *a: None)
    monkeypatch.setattr(db, 'get_conversation', lambda uid, cid: decoded(store, path))
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompt_answered', lambda *a: None)
    monkeypatch.setattr(router, 'conversation_clip_pcm', lambda *a: b'\x01\x00' * (16000 * 6))
    monkeypatch.setattr(service, 'verified_clip_pcm', lambda *a, **k: b'\x01\x00' * (16000 * 6))
    monkeypatch.setattr(service.owner_embedding_cache, 'load', lambda *a: {})
    monkeypatch.setattr(service.owner_embedding_cache, 'save', lambda *a: None)
    binding = binding_for(raw, card(raw))
    binding['selected_pcm_sha256'] = hashlib.sha256(b'\x01\x00' * (16000 * 6)).hexdigest()
    assert owner_confirmation_db.record('u', 'c', 'claim', binding)
    assert not owner_confirmation_db.record('u', 'c', 'claim', binding)
    return store, path, binding


def decoded(store, path):
    raw = deepcopy(store.rows[path])
    raw['transcript_segments'] = db._decode_transcript_segments_strict(
        'u', raw['transcript_segments'], bool(raw.get('transcript_segments_compressed'))
    )
    raw['manual_speaker_assignments'] = db.decode_manual_speaker_assignments(
        'u', raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    return raw


def test_claim_rejects_unverified_transcript_blob_without_consuming_quota(world, monkeypatch):
    store, path, binding = world
    del store.rows[path][FIELD]
    store.rows[path]['transcript_segments'] = json.dumps(store.rows[path]['transcript_segments'])
    monkeypatch.setattr(db.encryption, 'decrypt', lambda raw, uid: raw)
    before = deepcopy(store.rows[path])
    with pytest.raises(StaleOwnerConfirmation, match='unreadable'):
        owner_confirmation_db.record('u', 'c', 'claim', binding)
    assert store.rows[path] == before
    assert FIELD not in store.rows[path]


def test_question_shown_does_not_stamp_another_set_and_is_idempotent(world, monkeypatch):
    store, path, binding = world
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompts_shown', lambda *a: pytest.fail('Extra set'))
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: [decoded(store, path)])
    counter = service.OWNER_CONFIRMATION_EVENTS.labels(event='shown')
    before = counter._value.get()
    assert service.mark_shown('u', [binding['prompt_id']], NOW, set_shown=False) is False
    assert service.mark_shown('u', [binding['prompt_id']], NOW, set_shown=False) is False
    assert counter._value.get() == before + 1


@pytest.mark.parametrize('answer', ['me', 'not_me', 'skip'])
def test_late_duplicate_visibility_counts_consumed_card_without_reopening(world, monkeypatch, answer):
    store, path, binding = world
    played(world)
    service.apply_answer('u', request(binding, answer))
    consumed = deepcopy(store.rows[path][FIELD])
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompts_shown', lambda *a: pytest.fail('Extra set'))
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: [decoded(store, path)])
    counter = service.OWNER_CONFIRMATION_EVENTS.labels(event='shown')
    before = counter._value.get()
    service.mark_shown('u', [binding['prompt_id']], NOW, set_shown=False)
    service.mark_shown('u', [binding['prompt_id']], NOW, set_shown=False)
    assert counter._value.get() == before + 1
    assert store.rows[path][FIELD] == dict(consumed, shown=True)
    assert not owner_confirmation_db.record('u', 'c', 'shown', binding)
    assert not owner_confirmation_db.record('u', 'c', 'claim', binding)
    assert selection.complete_owner_runs(decoded(store, path)) == []
    with pytest.raises(StaleOwnerConfirmation):
        service.apply_answer('u', request(binding, answer))
    with pytest.raises(StaleOwnerConfirmation):
        owner_confirmation_db.record('u', 'c', 'played', binding, pcm_sha256=binding['selected_pcm_sha256'])


def test_visibility_requires_exact_issued_evidence_even_after_answer(world):
    store, path, binding = world
    service.apply_answer('u', request(binding, 'skip'))
    for field, value in [
        ('prompt_id', 'other'),
        ('evidence_id', 'other'),
        ('segment_ids', ['sibling']),
        ('speaker_id', 9),
    ]:
        with pytest.raises(StaleOwnerConfirmation):
            owner_confirmation_db.record('u', 'c', 'shown', dict(binding, **{field: value}))
    assert not store.rows[path][FIELD].get('shown')


def request(binding, answer='me', **extra):
    return SpeakerTagPromptAnswerRequest(
        prompt_id=binding['prompt_id'],
        kind='owner_check',
        origin='auto_user',
        conversation_id='c',
        speaker_id=1,
        segment_ids=['played'],
        answer=answer,
        evidence_id=binding['evidence_id'],
        **extra,
    )


def played(world):
    store, path, binding = world
    owner_confirmation_db.record('u', 'c', 'played', binding, pcm_sha256=binding['selected_pcm_sha256'])


@pytest.mark.parametrize('answer', ['me', 'not_me'])
def test_answer_changes_only_played_complete_segment_and_never_enrolls(world, answer):
    store, path, binding = world
    played(world)
    before = decoded(store, path)
    scheduled = []
    response = service.apply_answer('u', request(binding, answer), lambda *a, **k: scheduled.append((a, k)))
    after = decoded(store, path)
    assert after['transcript_segments'][1:] == before['transcript_segments'][1:]
    assert after['transcript_segments'][0]['is_user'] == (answer == 'me')
    receipt = after['manual_speaker_assignments']
    assert not receipt.get('speakers')
    assert receipt['segments']['played']['segment_only']
    assert receipt['segments']['played']['use_for_speech_training'] is False
    assert not manual_owner_reserved(receipt) and not manual_rejected_speakers(receipt)
    # Reload/post-resolution overlays the manual receipt without altering siblings.
    assert apply_manual_assignments(before['transcript_segments'], receipt) == after['transcript_segments']
    assert [s.id for s in response.segment_identities] == ['played']
    assert not response.voice_sample_queued and not scheduled
    assert authorized_owner_segments(after, ['played'], card_generation=receipt['generation']) == []
    assert store.rows[('users', 'u')] == dict(speaker_embedding=[1.0, 0.0])
    assert response.quality_outcome == ('owner_missed' if answer == 'me' else 'owner_unmatched_not_owner')


@pytest.mark.parametrize(
    'change',
    [
        'regroup',
        'scope',
        'capture',
        'delete_segment',
        'overlap',
        'receipt',
        'audio',
        'locked',
        'deleted',
        'discarded',
        'baseline_status',
    ],
)
def test_stale_answer_is_atomic(world, change):
    store, path, binding = world
    played(world)
    raw = store.rows[path]
    if change == 'regroup':
        raw['transcript_segments'][0]['speaker_id'] = 3
    elif change == 'scope':
        raw['transcript_segments'][0]['speaker_id_scope'] = 'other-capture'
    elif change == 'capture':
        raw['transcript_segments'][0]['audio_capture_run'] = 123
    elif change == 'delete_segment':
        raw['transcript_segments'].pop(0)
    elif change == 'overlap':
        raw['transcript_segments'].append(dict(id='overlap', speaker_id=2, start=1, end=3, text='other', is_user=False))
    elif change == 'receipt':
        raw['manual_speaker_assignments'] = {'generation': 1}
    elif change == 'audio':
        raw['audio_files'][0]['duration'] = 59
    elif change == 'locked':
        raw['is_locked'] = True
    elif change == 'deleted':
        raw['deleted'] = True
    elif change == 'discarded':
        raw['discarded'] = True
    elif change == 'baseline_status':
        raw['transcript_segments'][0]['speaker_identity_status'] = 'ambiguous'
    before = deepcopy(store.rows)
    with pytest.raises(StaleOwnerConfirmation):
        service.apply_answer('u', request(binding))
    assert store.rows == before


def test_yes_requires_delivered_clip_skip_does_not_and_quota_survives_refresh(world):
    store, path, binding = world
    with pytest.raises(StaleOwnerConfirmation):
        service.apply_answer('u', request(binding))
    response = service.apply_answer('u', request(binding, 'skip'))
    assert response.quality_outcome == 'skipped'
    assert store.rows[path][FIELD]['answered'] == 'skip'
    assert selection.complete_owner_runs(decoded(store, path)) == []
    with pytest.raises(StaleOwnerConfirmation):
        service.apply_answer('u', request(binding, 'skip'))


@pytest.mark.parametrize('answer', ['person', 'new_person', 'someone_else', 'not_a_person'])
def test_owner_card_never_accepts_naming_or_nonbinary_answers(world, answer):
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer('u', request(world[2], answer))


@pytest.mark.parametrize('kind', ['identify', 'confirm_person'])
def test_owner_card_kind_edit_cannot_expand_scope_or_create_person(world, monkeypatch, kind):
    store, path, binding = world
    before = deepcopy(store.rows)
    monkeypatch.setattr(service, '_resolve_person', lambda *a: pytest.fail('Owner card reached naming'))
    payload = request(binding, 'new_person', name='Synthetic person').model_dump()
    payload.update(kind=kind, evidence_id=None)
    with pytest.raises(StaleOwnerConfirmation, match='naming'):
        service.apply_answer('u', SpeakerTagPromptAnswerRequest(**payload))
    assert store.rows == before


def test_legacy_owner_answer_without_evidence_fails_closed(world):
    old = request(world[2]).model_copy(update={'evidence_id': None})
    with pytest.raises(StaleOwnerConfirmation):
        service.apply_answer('u', old)


def test_clip_endpoint_binds_exact_audio_and_rejects_changed_bytes(world, monkeypatch):
    store, path, binding = world
    app = FastAPI()
    app.include_router(router.router)
    # Override the concrete route dependency, without auth or any network service.
    for route in app.routes:
        if hasattr(route, 'dependant'):
            for dep in route.dependant.dependencies:
                app.dependency_overrides[dep.call] = lambda: 'u'
    client = TestClient(app)
    params = dict(
        conversation_id='c', start=0, end=6, prompt_id=binding['prompt_id'], evidence_id=binding['evidence_id']
    )
    assert client.get('/v1/speaker-tag-prompts/clip', params={**params, 'end': 5}).status_code == 409
    assert client.get('/v1/speaker-tag-prompts/clip', params=params).status_code == 200
    monkeypatch.setattr(service, 'verified_clip_pcm', lambda *a, **k: b'\x02\x00' * (16000 * 6))
    assert client.get('/v1/speaker-tag-prompts/clip', params=params).status_code == 409
    response = client.post('/v1/speaker-tag-prompts/answer', json=request(binding).model_dump(mode='json'))
    assert response.status_code == 200
    assert response.json()['segment_identities'] == [dict(id='played', is_user=True, person_id=None)]
    assert (
        client.post('/v1/speaker-tag-prompts/answer', json=request(binding).model_dump(mode='json')).status_code == 409
    )


def test_excerpt_owner_does_not_retract_automatic_owner_but_legacy_receipt_still_reserves():
    decision = select_speaker_match({'user': 0.2})
    scoped = {'segments': {'played': dict(is_user=True, segment_only=True)}}
    legacy = {'segments': {'played': dict(is_user=True)}}
    assert not manual_owner_reserved(scoped)
    assert manual_owner_reserved(legacy)
    assert arbitrate_owner_matches({2: {'user': 0.2}}, {2: decision}, owner_reserved=manual_owner_reserved(scoped))[
        2
    ].accepted
    assert not arbitrate_owner_matches({2: {'user': 0.2}}, {2: decision}, owner_reserved=manual_owner_reserved(legacy))[
        2
    ].accepted


def test_complete_windows_reject_long_crops_mixed_source_and_cross_scope():
    raw = conversation()
    raw['transcript_segments'] = [dict(raw['transcript_segments'][0], end=60)]
    assert selection.complete_owner_runs(raw) == []
    raw['transcript_segments'] = [
        dict(raw['transcript_segments'][0], end=3),
        dict(raw['transcript_segments'][0], id='second', start=3, end=6, speaker_id_scope='b'),
    ]
    assert selection.complete_owner_runs(raw) == []
    raw['transcript_segments'][1]['speaker_id_scope'] = 'capture:a'
    raw['transcript_segments'][1]['audio_source'] = {'type': 'system_audio'}
    assert selection.complete_owner_runs(raw) == []


def test_pool_selects_ambiguity_then_centroid_not_labels(monkeypatch):
    raw = conversation()
    raw['transcript_segments'][2]['speaker_id'] = 1
    runs = selection.complete_owner_runs(raw)
    vectors = iter([np.array([[1.0, 0.0]]), np.array([[0.5, 0.8660254]]), np.array([[0.6, 0.8]])])
    monkeypatch.setattr(service, 'verified_clip_pcm', lambda uid, raw, start, *a, **k: str(start).encode())
    monkeypatch.setattr(service.owner_embedding_cache, 'load', lambda *a: {})
    monkeypatch.setattr(service.owner_embedding_cache, 'save', lambda *a: None)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a, **k: next(vectors))
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda *a, **k: None)
    run, distance, digest = service._owner_group_evidence('u', raw, runs, [1.0, 0.0], time.monotonic() + 5)
    assert run.segment_ids == ('other',)  # closest to the mean, not the first/longest/owner label
    assert 0 < distance < 0.5 and len(digest) == 64


def test_free_service_selects_one_owner_card_and_claims_quota_durably(world, monkeypatch):
    store, path, _ = world
    store.rows[path].pop(FIELD)
    settings = dict(speaker_tag_prompts_enabled=True, save_other_voice_profiles=False)
    monkeypatch.setattr(service.voice_profiles_db, 'get_voice_profile_context', lambda uid: (settings, True))
    monkeypatch.setattr(service.voice_profiles_db, 'get_tag_prompt_state', lambda uid: {})
    monkeypatch.setattr(service.voice_profiles_db, 'mark_tag_prompts_empty', lambda *a: None)
    monkeypatch.setattr(service.voice_profiles_db, 'record_tag_prompts_shown', lambda *a: False)
    monkeypatch.setattr(service.users_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    monkeypatch.setattr(service.users_db, 'get_people', lambda uid: pytest.fail('Free owner selector loaded people'))
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: [decoded(store, path)])
    monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: False)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a, **k: np.array([[0.5, 0.8660254]]))
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda *a, **k: None)
    monkeypatch.setattr(service, 'emit_product_event', lambda **k: None)
    # Older clients do not receive owner cards or consume the durable quota.
    assert service.get_prompts('u', NOW).prompts == []
    assert FIELD not in store.rows[path]
    result = service.get_prompts('u', NOW, owner_excerpt=True)
    assert len(result.prompts) == 1 and result.prompts[0].kind == 'owner_check'
    prompt = result.prompts[0]
    assert prompt.segment_ids == ['played'] and prompt.evidence_id
    assert prompt.suggested_person_id is None and not prompt.candidates
    assert not service.get_prompts('u', NOW, owner_excerpt=True).prompts
    service.mark_shown('u', [prompt.id], NOW)
    assert store.rows[path][FIELD]['shown']
    assert not owner_confirmation_db.record('u', 'c', 'shown', store.rows[path][FIELD])


def test_scoped_manual_receipt_is_not_a_post_resolution_voice_anchor(world):
    played(world)
    service.apply_answer('u', request(world[2]))
    receipt = decoded(world[0], world[1])['manual_speaker_assignments']
    assert _manual_speakers(receipt) == {}


def test_sync_source_complete_segments_share_clock_without_sharing_bounds():
    raw = conversation()
    raw['transcript_segments'] = [
        dict(raw['transcript_segments'][0], end=3, audio_source=dict(type='sync', start=100, end=103)),
        dict(
            raw['transcript_segments'][0],
            id='second',
            start=3,
            end=6,
            audio_source=dict(type='sync', start=103, end=106),
        ),
    ]
    runs = selection.complete_owner_runs(raw)
    assert len(runs) == 1 and runs[0].segment_ids == ('played', 'second')
    raw['transcript_segments'][1]['audio_source'] = dict(type='sync', start=203, end=206)
    assert selection.complete_owner_runs(raw) == []


def test_no_rejects_only_owner_preserving_existing_automatic_nonowner(world):
    store, path, _ = world
    store.rows[path].pop(FIELD)
    store.rows[path]['transcript_segments'][0].update(
        person_id='known',
        speaker_match_source='voiceprint',
        speaker_label_source='auto',
        speaker_identity_status='not_user',
    )
    person = dict(name='Known', speaker_embedding=[0.0, 1.0])
    store.rows[('users', 'u', 'people', 'known')] = deepcopy(person)
    raw = decoded(store, path)
    binding = binding_for(raw, card(raw))
    binding['selected_pcm_sha256'] = hashlib.sha256(b'\x01\x00' * (16000 * 6)).hexdigest()
    owner_confirmation_db.record('u', 'c', 'claim', binding)
    owner_confirmation_db.record('u', 'c', 'played', binding, pcm_sha256=binding['selected_pcm_sha256'])
    before = deepcopy(raw['transcript_segments'])
    service.apply_answer('u', request(binding, 'not_me'))
    after = decoded(store, path)
    assert after['transcript_segments'] == before
    assert after['manual_speaker_assignments']['segments']['played']['person_id'] is None
    assert store.rows[('users', 'u', 'people', 'known')] == person


def test_owner_excerpt_boundaries_do_not_depend_on_identity_labels():
    raw = conversation()
    raw['transcript_segments'] = [
        dict(id='a', speaker_id=1, start=0.0, end=3.0, text='First half', is_user=False),
        dict(id='b', speaker_id=1, start=3.0, end=6.0, text='Second half', is_user=True),
    ]
    before = selection.complete_owner_runs(raw)
    raw['transcript_segments'][1]['is_user'] = False
    after = selection.complete_owner_runs(raw)
    assert [(run.segment_ids, run.start, run.end) for run in after] == [
        (run.segment_ids, run.start, run.end) for run in before
    ]
    assert before[0].identity == 'mixed' and after[0].identity == 'none'
    assert before[0].segment_ids == ('a', 'b')


@pytest.mark.parametrize(
    'labels', [('user', 'none'), ('user', 'person:a'), ('person:a', 'none'), ('person:a', 'person:b')]
)
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('answer', ['me', 'not_me', 'skip'])
def test_mixed_baselines_are_bound_per_segment_and_quality_is_order_independent(world, labels, reverse, answer):
    store, path, _ = world
    raw = conversation()
    if reverse:
        labels = labels[::-1]
    selected = []
    for index, label in enumerate(labels):
        selected.append(
            dict(
                raw['transcript_segments'][0],
                id=f'part-{index}',
                start=index * 3.0,
                end=(index + 1) * 3.0,
                is_user=label == 'user',
                person_id=label.split(':')[1] if label.startswith('person:') else None,
            )
        )
    raw['transcript_segments'] = selected + raw['transcript_segments'][1:]
    store.rows[path] = deepcopy(raw)
    run = selection.complete_owner_runs(raw)[0]
    assert run.identity == 'mixed' and run.segment_ids == ('part-0', 'part-1')
    prompt = card(raw).model_copy(update={'segment_ids': list(run.segment_ids)})
    binding = binding_for(raw, prompt)
    binding['selected_pcm_sha256'] = hashlib.sha256(b'played').hexdigest()
    assert binding['origin'] == 'mixed'
    assert binding['baseline_labels'] == [
        {key: segment.get(key) for key in ('id', 'is_user', 'person_id', 'speaker_identity_status')}
        for segment in selected
    ]
    owner_confirmation_db.record('u', 'c', 'claim', binding)
    owner_confirmation_db.record('u', 'c', 'played', binding, pcm_sha256=binding['selected_pcm_sha256'])
    payload = request(binding, answer).model_copy(update={'segment_ids': list(run.segment_ids)})
    label = 'skipped' if answer == 'skip' else 'owner_mixed_yes' if answer == 'me' else 'owner_mixed_no'
    counter = service.SPEAKER_TAG_PROMPT_QUALITY.labels(outcome=label)
    before = counter._value.get()
    uniform = [
        service.SPEAKER_TAG_PROMPT_QUALITY.labels(outcome=value)
        for value in (
            'owner_auto_confirmed',
            'owner_auto_rejected',
            'owner_missed',
            'owner_unmatched_not_owner',
            'person_auto_confirmed',
            'person_auto_corrected',
        )
    ]
    uniform_before = [value._value.get() for value in uniform]
    response = service.apply_answer('u', payload)
    assert counter._value.get() == before + 1
    assert [value._value.get() for value in uniform] == uniform_before
    assert response.quality_outcome == ('skipped' if answer == 'skip' else 'unknown_voice')
    after = decoded(store, path)
    assert after[FIELD]['baseline_labels'] == binding['baseline_labels']
    assert after['transcript_segments'][2:] == raw['transcript_segments'][2:]
    if answer == 'not_me':
        assert [segment.get('person_id') for segment in after['transcript_segments'][:2]] == [
            segment.get('person_id') for segment in selected
        ]
    assert store.rows[('users', 'u')]['speaker_embedding'] == [1.0, 0.0]


@pytest.mark.parametrize('answer', ['me', 'not_me'])
def test_uniform_person_baseline_observes_owner_quality_without_judging_person_identity(world, answer):
    store, path, _ = world
    store.rows[path].pop(FIELD)
    store.rows[path]['transcript_segments'][0]['person_id'] = 'known'
    raw = decoded(store, path)
    binding = binding_for(raw, card(raw))
    binding['selected_pcm_sha256'] = hashlib.sha256(b'played').hexdigest()
    assert binding['origin'] == 'auto_person'
    owner_confirmation_db.record('u', 'c', 'claim', binding)
    owner_confirmation_db.record('u', 'c', 'played', binding, pcm_sha256=binding['selected_pcm_sha256'])
    result = service.apply_answer('u', request(binding, answer))
    assert result.quality_outcome == ('owner_missed' if answer == 'me' else 'owner_unmatched_not_owner')
