"""Offline authority contracts: entitlement snapshots, consent races, retraction and deletion."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import conversations, users, voice_profiles
from models.transcript_segment import TranscriptSegment
from routers.listen import speakers
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import speaker_resolution
from utils.owner_voice_evidence import authorized_owner_segments, pool_owner_vectors
from utils.manual_speaker_assignments import apply_manual_assignments
from utils.speaker_learning_policy import authorized_teaching_segments
from utils.speaker_tag_prompts import service
from utils.sync import speaker_identity
from utils import speaker_permissions, executors

USER = ('users', 'u')
CONV = (*USER, 'conversations', 'c')
PERSON = (*USER, 'people', 'p')
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def source(training=True, generation=1):
    return {
        'id': 'c',
        'language': 'en',
        'transcript_segments': [
            {'id': 's', 'speaker_id': 1, 'start': 0, 'end': 8, 'text': 'synthetic owner speech', 'is_user': True}
        ],
        'manual_speaker_assignments': {
            'generation': generation,
            'segments': {'s': {'generation': generation, 'is_user': True, 'use_for_speech_training': training}},
        },
    }


@pytest.mark.parametrize('surface', ['live', 'sync', 'resolution'])
@pytest.mark.parametrize('paid', [False, True])
def test_candidates_are_gated_before_nonowner_reads(monkeypatch, surface, paid):
    person = {
        'id': 'p',
        'name': 'Synthetic',
        'speaker_embedding': [0.0, 1.0],
        'speech_samples': ['sample'],
        'speech_samples_version': 3,
    }
    load = Mock(return_value=[person])
    permission = Mock(return_value=paid)
    monkeypatch.setattr(users, 'get_people', load)
    monkeypatch.setattr(users, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', permission)
    monkeypatch.setattr(speaker_identity, 'named_speaker_prompts_allowed', permission)
    monkeypatch.setattr(speaker_permissions, 'named_speaker_prompts_allowed', permission)
    monkeypatch.setattr(speaker_resolution, 'named_speaker_prompts_allowed', permission)
    monkeypatch.setattr(speaker_identity, 'get_user_name', lambda uid: 'Owner')
    monkeypatch.setattr(speakers, 'get_user_name', lambda *a: 'Owner')

    async def migrate(uid, p):
        return p

    monkeypatch.setattr(speakers, 'maybe_migrate_person_samples', migrate)
    if surface == 'live':

        async def call(fn, *a, **kw):
            return fn(*a, **kw)

        matcher = speakers.SpeakerMatcher(
            SimpleNamespace(
                persistence=SimpleNamespace(call=call), request=SimpleNamespace(uid='u'), has_speech_profile=True
            )
        )
        asyncio.run(matcher._load_profiles())
        cache = matcher.person_embeddings
    elif surface == 'sync':
        dependencies = speaker_identity.SpeakerIdentityDependencies(get_user_name=lambda uid: 'Owner')
        cache = speaker_identity.build_person_embeddings_cache('u', dependencies=dependencies)
    else:
        cache = speaker_resolution.load_voiceprints_for_resolution('u')
    assert set(cache) == ({'user', 'p'} if paid else {'user'})
    assert load.call_count == int(paid)
    assert permission.call_count == 1


def test_live_plan_changes_are_observed_on_rotation_once(monkeypatch):
    permission = Mock(side_effect=[True, False, True])
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', permission)
    monkeypatch.setattr(users, 'get_people', lambda uid: [])

    async def call(fn, *a, **kw):
        return fn(*a, **kw)

    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(
            request=SimpleNamespace(uid='u'),
            persistence=SimpleNamespace(call=call),
            has_speech_profile=False,
            state=SimpleNamespace(speaker_id_enabled=True),
        )
    )

    async def run():
        for index, expected in enumerate([True, False, True]):
            await matcher.refresh_for_conversation(str(index))
            assert await matcher.named_speakers_allowed() is expected
            assert await matcher.named_speakers_allowed() is expected
        assert permission.call_count == 3

    asyncio.run(run())


def test_sync_empty_paid_cache_keeps_text_permission_without_rereading(monkeypatch):
    monkeypatch.setattr(speaker_identity, 'named_speaker_prompts_allowed', lambda uid: pytest.fail('batch re-read'))
    detect = Mock(return_value='Synthetic')
    lookup = Mock(return_value={'id': 'p', 'name': 'Synthetic'})
    deps = speaker_identity.SpeakerIdentityDependencies(
        detect_speaker_from_text=detect,
        users_db=SimpleNamespace(get_person_by_name=lookup),
    )
    for paid in [False, True]:
        segment = TranscriptSegment(id='s', text='My name is Synthetic', speaker_id=1, start=0, end=2, is_user=False)
        speaker_identity.identify_speakers_for_segments(
            [segment], None, speaker_identity.PersonEmbeddingsCache(paid), 'u', dependencies=deps
        )
        assert segment.person_id == ('p' if paid else None)
    assert detect.call_count == lookup.call_count == 1


@pytest.mark.parametrize('card_generation', [None, 1])
def test_delayed_owner_job_cannot_consume_newer_optout(monkeypatch, card_generation):
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a: source(False, 2))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *a: pytest.fail('unauthorized download'))
    assert (
        asyncio.run(service.store_owner_voice_sample('u', 'c', ['s'], card_generation=card_generation))
        == 'stale_assignment'
    )


def test_card_permission_is_bound_to_its_exact_decision():
    assert authorized_owner_segments(source(False), ['s']) == []
    assert authorized_owner_segments(source(False), ['s'], card_generation=1) == ['s']
    assert authorized_owner_segments(source(False, 2), ['s'], card_generation=1) == []
    assert authorized_owner_segments({'transcript_segments': source()['transcript_segments']}, ['s']) == []


@pytest.mark.parametrize('kind', ['correction', 'reject', 'optout'])
@pytest.mark.parametrize('legacy', [False, True])
def test_owner_correction_rebuilds_profile_in_assignment_transaction(monkeypatch, kind, legacy):
    store = StrictFirestore({USER: {'speaker_embedding': [1.0, 0.0]}, CONV: source(), PERSON: {'id': 'p'}})
    voice_profiles.add_owner_voice_confirmation(
        'u',
        [0.0, 1.0],
        pool_owner_vectors,
        conversation_id='c',
        expected_receipt_generation=1,
        segment_ids=None if legacy else ['s'],
        firestore_client=store,
    )
    voice_profiles.add_owner_voice_confirmation(
        'u', [1.0, 0.0], pool_owner_vectors, conversation_id='other', segment_ids=['other'], firestore_client=store
    )
    monkeypatch.setattr(conversations, 'record_speaker_review', lambda *a: None)
    kwargs = (
        {'person_id': 'p'}
        if kind == 'correction'
        else (
            {'rejection': {'kind': 'not_me'}}
            if kind == 'reject'
            else {'is_user': True, 'use_for_speech_training': False}
        )
    )
    conversations.assign_conversation_speaker('u', 'c', segment_ids=['s'], firestore_client=store, **kwargs)
    saved = store.rows[USER]
    assert saved['speaker_embedding'] == pytest.approx([1.0, 0.0])
    assert [x['conversation_id'] for x in saved['owner_voice_confirmations']] == ['other']
    assert {path for path, _ in store.transactions[-1].updates} >= {USER, CONV}


def test_duplicate_owner_delivery_has_one_contribution_and_correction_clears_cold_start(monkeypatch):
    store = StrictFirestore({USER: {}, CONV: source()})
    for _ in range(2):
        assert (
            voice_profiles.add_owner_voice_confirmation(
                'u',
                [0.0, 1.0],
                pool_owner_vectors,
                conversation_id='c',
                expected_receipt_generation=1,
                segment_ids=['s'],
                firestore_client=store,
            )
            == 1
        )
    monkeypatch.setattr(conversations, 'record_speaker_review', lambda *a: None)
    conversations.assign_conversation_speaker('u', 'c', segment_ids=['s'], firestore_client=store)
    assert store.rows[USER]['speaker_embedding'] is None
    assert store.rows[USER]['owner_voice_confirmations'] == []


@pytest.mark.parametrize(
    'mutation',
    ['unchanged', 'legacy', 'other_voice_edit', 'delete', 'tombstone', 'older_receipt', 'optout', 'identity'],
)
def test_person_publication_rechecks_source_in_transaction(monkeypatch, mutation):
    conv = source()
    conv['transcript_segments'][0].update(person_id='p', is_user=False)
    conv['manual_speaker_assignments']['segments']['s'].update(person_id='p', is_user=False)
    store = StrictFirestore({USER: {}, CONV: conv, PERSON: {'id': 'p'}})
    if mutation == 'delete':
        store.rows.pop(CONV)
    elif mutation == 'tombstone':
        store.rows[CONV]['deleted'] = True
    elif mutation == 'other_voice_edit':
        # Tagging a second speaker bumps the receipt generation but leaves this label alone.
        store.rows[CONV]['manual_speaker_assignments']['generation'] = 2
    elif mutation == 'older_receipt':
        store.rows[CONV]['manual_speaker_assignments']['generation'] = 0
    elif mutation == 'optout':
        store.rows[CONV]['manual_speaker_assignments']['segments']['s']['use_for_speech_training'] = False
    elif mutation == 'identity':
        store.rows[CONV]['transcript_segments'][0]['person_id'] = 'other'
    elif mutation == 'legacy':
        store.rows[CONV].pop('manual_speaker_assignments')
    monkeypatch.setattr(users, 'db', store)
    result = users.replace_person_speech_profile(
        'u',
        'p',
        None,
        'sample',
        'synthetic',
        [1, 0],
        'c',
        ['s'],
        expected_receipt_generation=0 if mutation == 'legacy' else 1,
    )
    if mutation in {'unchanged', 'legacy', 'other_voice_edit'}:
        assert result == []
        assert store.rows[PERSON]['speaker_embedding'] == [1, 0]
        provenance = store.rows[PERSON]['speech_sample_source']
        assert provenance['conversation_id'] == 'c' and provenance['segment_ids'] == ['s']
        assert provenance['generation'] == (0 if mutation == 'legacy' else 1)
        assert provenance['stored_at'] is not None
    else:
        assert result is None
        assert not store.rows[PERSON].get('speaker_embedding')


def test_owner_clip_coordinator_borrows_sync_pool(monkeypatch):
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a: source())

    async def dispatch(executor, fn, *args, **kwargs):
        if fn is service.conversation_clip_pcm:
            assert executor is service.sync_executor and executor is not executors.storage_executor
            return None
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', dispatch)
    assert asyncio.run(service.store_owner_voice_sample('u', 'c', ['s'])) == 'no_audio'


def test_inflight_owner_publication_cannot_cross_a_correction():
    store = StrictFirestore({USER: {}, CONV: source(False, 2)})
    assert (
        voice_profiles.add_owner_voice_confirmation(
            'u',
            [0.0, 1.0],
            pool_owner_vectors,
            conversation_id='c',
            expected_receipt_generation=1,
            segment_ids=['s'],
            firestore_client=store,
        )
        == 0
    )
    assert not store.rows[USER].get('speaker_embedding')


def test_live_entitlement_read_cannot_restore_old_conversation_permission():
    async def call(fn, *a, **kw):
        matcher.clear()
        return True

    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(request=SimpleNamespace(uid='u'), persistence=SimpleNamespace(call=call))
    )
    assert asyncio.run(matcher.named_speakers_allowed()) is False
    assert matcher._named_speakers_allowed is None


def test_live_entitlement_read_failure_stays_closed_and_is_retried():
    calls = []

    async def call(fn, *a, **kw):
        calls.append(fn)
        if len(calls) == 1:
            raise RuntimeError('subscription read failed')
        return True

    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(request=SimpleNamespace(uid='u'), persistence=SimpleNamespace(call=call))
    )

    async def run():
        assert await matcher.named_speakers_allowed() is False
        assert matcher._named_speakers_allowed is None
        assert await matcher.named_speakers_allowed() is True

    asyncio.run(run())
    assert len(calls) == 2


@pytest.mark.parametrize('segment_scope, teaches', [('scope-a', True), ('scope-b', False)])
def test_carried_label_teaches_only_inside_its_capture_scope(monkeypatch, segment_scope, teaches):
    # A merged conversation reuses speaker id 1 in two capture scopes. The label carried
    # into scope-a must not authorize scope-b audio that merely bears the same person.
    segment = {
        'id': 's',
        'speaker_id': 1,
        'speaker_id_scope': segment_scope,
        'person_id': 'p',
        'is_user': False,
        'start': 0,
        'end': 10,
        'text': 'synthetic speech',
    }
    receipt = {
        'generation': 1,
        'segments': {},
        'speakers': {
            '1': {
                'generation': 1,
                'person_id': 'p',
                'is_user': False,
                'source': 'carried',
                'speaker_id_scope': 'scope-a',
            }
        },
    }
    conversation = {'id': 'c', 'transcript_segments': [segment], 'manual_speaker_assignments': receipt}
    assert authorized_teaching_segments(conversation, 'p') == ([segment] if teaches else [])
    # Label application already drew the same line; teaching now agrees with it.
    applied = apply_manual_assignments([dict(segment, person_id=None)], receipt)
    assert (applied[0].get('person_id') == 'p') is teaches
    store = StrictFirestore({USER: {}, CONV: conversation, PERSON: {'id': 'p'}})
    monkeypatch.setattr(users, 'db', store)
    users.replace_person_speech_profile(
        'u', 'p', None, 'sample', 'synthetic', [1.0, 0.0], 'c', ['s'], expected_receipt_generation=1
    )
    assert (store.rows[PERSON].get('speaker_embedding') == [1.0, 0.0]) is teaches


def _owner_source_after(decisions):
    conversation = source()
    conversation['transcript_segments'].append(
        {'id': 'other', 'speaker_id': 2, 'start': 9, 'end': 15, 'text': 'synthetic guest speech', 'is_user': False}
    )
    receipt = conversation['manual_speaker_assignments']
    receipt['generation'] = 2
    receipt['segments'].update(decisions)
    return conversation


def _pool_owner(store):
    return voice_profiles.add_owner_voice_confirmation(
        'u',
        [0.0, 1.0],
        pool_owner_vectors,
        conversation_id='c',
        expected_receipt_generation=1,
        segment_ids=['s'],
        firestore_client=store,
    )


def test_owner_teaching_survives_a_later_tag_on_another_voice():
    conversation = _owner_source_after({'other': {'generation': 2, 'person_id': 'p', 'is_user': False}})
    store = StrictFirestore({USER: {}, CONV: conversation})
    assert _pool_owner(store) == 1
    assert store.rows[USER]['speaker_embedding'] == pytest.approx([0.0, 1.0])


@pytest.mark.parametrize(
    'decision, still_owner',
    [
        ({'generation': 2, 'person_id': 'p', 'is_user': False}, False),
        ({'generation': 2, 'is_user': True, 'use_for_speech_training': False}, True),
        ({'generation': 2, 'is_user': False, 'rejection': {'kind': 'not_me'}}, False),
    ],
)
def test_owner_teaching_stops_when_its_own_segment_is_revoked(decision, still_owner):
    conversation = _owner_source_after({'s': decision})
    conversation['transcript_segments'][0]['is_user'] = still_owner
    store = StrictFirestore({USER: {}, CONV: conversation})
    assert _pool_owner(store) == 0
    assert 'speaker_embedding' not in store.rows[USER]
