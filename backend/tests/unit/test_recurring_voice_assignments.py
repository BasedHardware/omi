"""Binding uses current manual receipts and authoritative person prints in one transaction."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from google.cloud import firestore

from database import recurring_voices as store, recurring_voice_assignments as assignments, speaker_auto_enroll
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.speakers import recurring_voices as policy

NOW = datetime.now(timezone.utc).timestamp()
OWNER = [1.0, *([0.0] * 255)]
VOICE = [0.0, 1.0, *([0.0] * 254)]
OTHER = [0.0, 0.0, 1.0, *([0.0] * 253)]


def segments(pid=None):
    return [
        {
            'id': 's1',
            'speaker_id': 1,
            'speaker_id_scope': 'final:batch:conversation:c1',
            'recurring_voice_id': 'v',
            'person_id': pid,
            'is_user': False,
            'start': 0,
            'end': 30,
            'text': 'hello',
        }
    ]


def receipt(pid):
    return {
        'generation': 1,
        'segments': {
            's1': {
                'person_id': pid,
                'is_user': False,
                'use_for_speech_training': True,
                'generation': 1,
                'source': 'manual',
            }
        },
    }


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(store.encryption, 'derive_key', lambda uid: bytes(32))
    profile = {
        'state': 'recurring',
        'entries': [{'conversation_id': cid, 'at': NOW, 'seconds': 30, 'vector': VOICE} for cid in ['c1', 'c2']],
    }
    blob = store.seal('u', 'v', profile)
    owner = {
        'private_cloud_sync_enabled': True,
        'save_other_voice_profiles': True,
        'speaker_embedding': OWNER,
        store.INDEX: {'v': store.pools.pool_token(blob)},
    }
    return StrictFirestore(
        {
            ('users', 'u'): owner,
            ('users', 'u', store.COLLECTION, 'v'): {'sealed': blob},
            ('users', 'u', 'people', 'p'): {
                'speaker_embedding': VOICE,
                'speech_samples': ['private'],
                'speech_samples_version': 3,
            },
            ('users', 'u', 'conversations', 'c1'): {'private_cloud_sync_enabled': True},
        }
    )


def assign(db, *, pid='p', rejection=None, is_user=False, train=True, before=None, after=None):
    user = db.collection('users').document('u')

    @firestore.transactional
    def commit(tx):
        owner = user.get(transaction=tx).to_dict()
        person = user.collection('people').document(pid).get(transaction=tx).to_dict() if pid else None
        profiles, events = assignments.prepare(
            tx,
            user,
            owner,
            'c1',
            before or segments(),
            after or segments(pid),
            receipt(pid),
            ['s1'],
            person_id=pid,
            person=person,
            rejection=rejection,
            is_user=is_user,
            train=train,
        )
        if profiles is not None:
            store.write_profiles(tx, user, owner, profiles)
        return profiles, events

    return commit(db.transaction())


def test_bind_and_future_batch_uses_existing_person_naming_path(db):
    profiles, events = assign(db)
    assert profiles['v']['bound_person_id'] == 'p' and events == ['bound']
    clusters = {'a': {'embedding': VOICE, 'evidence_seconds': 30}, 'b': {'embedding': OWNER, 'evidence_seconds': 30}}
    _, labels, _, _ = policy.evaluate(clusters, {'user': OWNER, 'p': VOICE}, profiles, 'future', NOW + 1)
    assert labels['a'] == {'person_id': 'p', 'recurring_voice_id': 'v'}
    assert set(db.rows) == {
        ('users', 'u'),
        ('users', 'u', store.COLLECTION, 'v'),
        ('users', 'u', 'people', 'p'),
        ('users', 'u', 'conversations', 'c1'),
    }


@pytest.mark.parametrize('case', ['missing_print', 'inconsistent', 'no_training', 'kill', 'consent'])
def test_binding_fails_closed(db, monkeypatch, case):
    if case == 'missing_print':
        db.rows[('users', 'u', 'people', 'p')].pop('speaker_embedding')
    if case == 'inconsistent':
        db.rows[('users', 'u', 'people', 'p')]['speaker_embedding'] = OTHER
    if case == 'kill':
        monkeypatch.setenv('SPEAKER_RECURRING_VOICES_ENABLED', 'false')
    if case == 'consent':
        db.rows[('users', 'u')]['save_other_voice_profiles'] = False
    profiles, _ = assign(db, train=case != 'no_training')
    assert profiles is None if case == 'consent' else all(not p.get('bound_person_id') for p in profiles.values())


@pytest.mark.parametrize('kind', ['not_me', 'not_person', 'not_a_person'])
def test_rejection_tombstones_even_with_kill_switch(db, monkeypatch, kind):
    assign(db)
    monkeypatch.setenv('SPEAKER_RECURRING_VOICES_ENABLED', 'false')
    profiles, events = assign(db, rejection={'kind': kind})
    assert profiles['v']['state'] == 'rejected' and 'bound_person_id' not in profiles['v']
    assert events == ['rejected']
    monkeypatch.delenv('SPEAKER_RECURRING_VOICES_ENABLED')
    _, labels, events, _ = policy.evaluate(
        {'a': {'embedding': VOICE, 'evidence_seconds': 30}, 'b': {'embedding': OWNER, 'evidence_seconds': 30}},
        {'user': OWNER},
        profiles,
        'c3',
        NOW + 1,
    )
    assert labels['a'] == {} and 'created' not in events


def test_conflicting_assignment_retracts_and_unbinds(db):
    assign(db)
    db.rows[('users', 'u', 'people', 'q')] = deepcopy(db.rows[('users', 'u', 'people', 'p')])
    profiles, _ = assign(db, pid='q')
    assert profiles['v']['state'] == 'candidate'
    assert [e['conversation_id'] for e in profiles['v']['entries']] == ['c2']
    assert 'bound_person_id' not in profiles['v']


def test_conversation_and_person_delete_remove_sealed_evidence(db):
    speaker_auto_enroll.retract_conversation('u', 'c1', firestore_client=db)
    profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
    assert [e['conversation_id'] for e in profile['entries']] == ['c2']
    # Recreate recurrence, bind, and exercise the existing person-delete hook.
    blob = store.seal('u', 'v', {'state': 'bound', 'bound_person_id': 'p', 'entries': profile['entries']})
    db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'] = blob
    db.rows[('users', 'u')][store.INDEX]['v'] = store.pools.pool_token(blob)
    speaker_auto_enroll.revoke_person('u', 'p', firestore_client=db)
    assert db.rows[('users', 'u')][store.INDEX] == {}
    assert ('users', 'u', store.COLLECTION, 'v') not in db.rows


@pytest.fixture(scope='module')
def conversation_db():
    # Dependency startup belongs to setup; the call-phase CPU guard should
    # measure the real assignment/rejection transactions and their assertions.
    from database import conversations

    return conversations


def test_real_assignment_transaction_binds_and_rejection_clears_authority(db, monkeypatch, conversation_db):
    monkeypatch.setattr(conversation_db, 'get_firestore_client', lambda: db)
    db.rows[('users', 'u', 'conversations', 'c1')]['transcript_segments'] = segments()
    raw, resolved, *_ = conversation_db.assign_conversation_speaker('u', 'c1', person_id='p', segment_ids=['s1'])
    assert resolved == ['s1'] and raw['transcript_segments'][0]['person_id'] == 'p'
    profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
    assert profile['bound_person_id'] == 'p'
    conversation_db.assign_conversation_speaker(
        'u',
        'c1',
        segment_ids=['s1'],
        rejection={'kind': 'not_a_person', 'person_id': None},
        use_for_speech_training=False,
    )
    profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
    assert profile['state'] == 'rejected' and 'bound_person_id' not in profile


def test_person_print_drift_unbinds_instead_of_naming(db):
    profiles, _ = assign(db)
    clusters = {'a': {'embedding': VOICE, 'evidence_seconds': 30}, 'b': {'embedding': OWNER, 'evidence_seconds': 30}}
    following, labels, *_ = policy.evaluate(clusters, {'user': OWNER, 'p': OTHER}, profiles, 'c3', NOW + 1)
    assert 'person_id' not in labels['a']
    assert 'bound_person_id' not in following['v']


@pytest.fixture
def assignment_http(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import _client
    from routers import conversations as router
    from utils import speaker_assignment_teaching

    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(speaker_assignment_teaching, 'schedule_assignment_teaching', lambda *a, **kw: None)
    monkeypatch.setattr(router, 'emit_product_event', lambda **kw: True)
    db.rows[('users', 'u', 'conversations', 'c1')].update(
        id='c1',
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        structured={'title': 'Synthetic conversation', 'overview': '', 'emoji': '', 'category': 'other'},
        transcript_segments=segments(),
        status='completed',
    )
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        yield client


def test_assignment_http_endpoint_names_only_after_manual_confirmation(db, assignment_http):
    response = assignment_http.patch(
        '/v1/conversations/c1/assign-speaker/1', params={'assign_type': 'person_id', 'value': 'p'}
    )
    assert response.status_code == 200, response.text
    assert response.json()['transcript_segments'][0]['person_id'] == 'p'
    profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
    assert profile['bound_person_id'] == 'p'


def test_unrelated_conversation_deletion_preserves_confirmed_profile(db):
    profiles, _ = assign(db)
    original = deepcopy(profiles['v'])
    assert policy.retract(original, {'unrelated'}) == profiles['v']
    changed = policy.retract(original, {'c1'})
    assert 'bound_person_id' not in changed and 'bound_conversation_id' not in changed


def test_conversation_delete_does_not_resurrect_a_rejected_profile(db):
    assign(db, rejection={'kind': 'not_a_person'})
    speaker_auto_enroll.retract_conversation('u', 'c1', firestore_client=db)
    profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
    assert profile['state'] == 'rejected'
    following, labels, events, _ = policy.evaluate(
        {'a': {'embedding': VOICE, 'evidence_seconds': 30}, 'b': {'embedding': OWNER, 'evidence_seconds': 30}},
        {'user': OWNER},
        {'v': profile},
        'future',
        NOW + 1,
    )
    assert following['v']['state'] == 'rejected' and labels['a'] == {} and events == []


def test_confirmed_profile_refreshes_on_later_person_match_without_extending_retry_age(db):
    profiles, _ = assign(db)
    clusters = {'a': {'embedding': VOICE, 'evidence_seconds': 30}, 'b': {'embedding': OWNER, 'evidence_seconds': 30}}
    following, labels, events, _ = policy.evaluate(clusters, {'user': OWNER, 'p': VOICE}, profiles, 'c3', NOW + 1)
    assert labels['a'] == {'person_id': 'p', 'recurring_voice_id': 'v'}
    assert following['v']['state'] == 'bound' and 'refreshed' in events
    assert {e['conversation_id'] for e in following['v']['entries']} == {'c1', 'c2', 'c3'}
    retry, *_ = policy.evaluate(clusters, {'user': OWNER, 'p': VOICE}, following, 'c3', NOW + 10)
    assert next(e['at'] for e in retry['v']['entries'] if e['conversation_id'] == 'c3') == NOW + 1


@pytest.mark.parametrize('setting', ['private_cloud_sync_enabled', 'save_other_voice_profiles'])
def test_consent_checked_before_any_profile_read_or_write(db, monkeypatch, setting):
    db.rows[('users', 'u')][setting] = False
    original = deepcopy(db.rows)
    monkeypatch.setattr(store, 'read_profiles', lambda *a: pytest.fail('must not decrypt after opt-out'))
    assert assign(db) == (None, [])
    assert db.rows == original and not db.transactions[-1].has_written


@pytest.mark.parametrize('writer', ['bind', 'privacy', 'conversation', 'person'])
def test_all_profile_writers_use_account_deletion_fence(db, writer):
    from database import conversations
    from database.legal_holds import DestructiveOperationInProgress

    db.rows[('users', 'u', 'conversations', 'c1')]['transcript_segments'] = segments()
    db.rows[('account_deletions', 'u')] = {'wipe_status': 'running'}
    original = deepcopy(db.rows)
    with pytest.raises(DestructiveOperationInProgress):
        if writer == 'bind':
            conversations.assign_conversation_speaker('u', 'c1', person_id='p', segment_ids=['s1'], firestore_client=db)
        elif writer == 'privacy':
            speaker_auto_enroll.update_privacy('u', {'save_other_voice_profiles': False}, firestore_client=db)
        elif writer == 'conversation':
            speaker_auto_enroll.retract_conversation('u', 'c1', firestore_client=db)
        else:
            speaker_auto_enroll.revoke_person('u', 'p', firestore_client=db)
    assert db.rows == original and not db.transactions[-1].has_written


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize(
    'revocation', ['consent', 'sync', 'candidate_expiry', 'evidence_expiry', 'eviction', 'ttl', 'person', 'rejection']
)
def test_conversation_read_drops_revoked_recurring_links(db, level, revocation):
    from database import conversations

    assign(db)
    raw = conversations.encode_conversation_for_write('u', {'transcript_segments': segments()}, level)
    raw['data_protection_level'] = level
    assert (
        conversations.prepare_conversation_for_read(raw, 'u', firestore_client=db)['transcript_segments'][0][
            'recurring_voice_id'
        ]
        == 'v'
    )
    if revocation in {'consent', 'sync'}:
        db.rows[('users', 'u')][
            'save_other_voice_profiles' if revocation == 'consent' else 'private_cloud_sync_enabled'
        ] = False
    elif revocation == 'eviction':
        db.rows[('users', 'u')][store.INDEX] = {}
    elif revocation == 'ttl':
        db.rows.pop(('users', 'u', store.COLLECTION, 'v'))
    elif revocation == 'person':
        speaker_auto_enroll.revoke_person('u', 'p', firestore_client=db)
    elif revocation == 'rejection':
        assign(db, rejection={'kind': 'not_a_person'})
    else:
        profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
        age = policy.CANDIDATE_AGE if revocation == 'candidate_expiry' else store.pools.MAX_AGE_SECONDS
        for entry in profile['entries']:
            entry['at'] = NOW - age - 1
        if revocation == 'candidate_expiry':
            profile['state'] = 'candidate'
        blob = store.seal('u', 'v', profile)
        db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'] = blob
        db.rows[('users', 'u')][store.INDEX]['v'] = store.pools.pool_token(blob)
    result = conversations.prepare_conversation_for_read(raw, 'u', firestore_client=db)
    assert 'recurring_voice_id' not in result['transcript_segments'][0]
    assert result['transcript_segments'][0]['text'] == 'hello'


@pytest.mark.parametrize('revocation', ['consent', 'rejection', 'eviction'])
def test_assignment_http_response_cannot_return_a_revoked_pointer(db, assignment_http, revocation):
    params = {'assign_type': 'person_id', 'value': 'p'}
    if revocation == 'consent':
        db.rows[('users', 'u')]['save_other_voice_profiles'] = False
    elif revocation == 'eviction':
        db.rows[('users', 'u')][store.INDEX] = {}
    else:
        params = {'assign_type': 'is_user', 'value': 'false'}
    response = assignment_http.patch('/v1/conversations/c1/assign-speaker/1', params=params)
    assert response.status_code == 200, response.text
    assert 'recurring_voice_id' not in response.json()['transcript_segments'][0]


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('revocation', ['active', 'consent', 'sync', 'rejected', 'evicted', 'ttl', 'expired'])
def test_processing_write_uses_transactional_profile_authority(db, level, revocation):
    from database import conversations, recurring_voice_privacy

    if revocation in {'consent', 'sync'}:
        setting = 'save_other_voice_profiles' if revocation == 'consent' else 'private_cloud_sync_enabled'
        db.rows[('users', 'u')][setting] = False
    elif revocation == 'evicted':
        db.rows[('users', 'u')][store.INDEX] = {}
    elif revocation == 'ttl':
        db.rows.pop(('users', 'u', store.COLLECTION, 'v'))
    elif revocation in {'expired', 'rejected'}:
        profile = store.open_profile('u', 'v', db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'])
        if revocation == 'expired':
            for entry in profile['entries']:
                entry['at'] = NOW - store.pools.MAX_AGE_SECONDS - 1
        else:
            profile['state'] = 'rejected'
        blob = store.seal('u', 'v', profile)
        db.rows[('users', 'u', store.COLLECTION, 'v')]['sealed'] = blob
        db.rows[('users', 'u')][store.INDEX]['v'] = store.pools.pool_token(blob)
    data = conversations.encode_conversation_for_write('u', {'transcript_segments': segments()}, level)
    data['data_protection_level'] = level
    user = db.collection('users').document('u')
    transaction = db.transaction()
    recurring_voice_privacy.filter_processing_write(transaction, user, data)
    transaction.update(user.collection('conversations').document('c1'), data)
    decoded = conversations.decode_transcript_segments_verified(
        'u', data['transcript_segments'], data['transcript_segments_compressed']
    )
    assert (decoded[0].get('recurring_voice_id') == 'v') == (revocation == 'active')
    assert decoded[0]['text'] == 'hello'
    assert isinstance(data['transcript_segments'], str if level == 'enhanced' else bytes)


def test_processing_without_recurring_pointer_never_reads_profile_authority(db, monkeypatch):
    from database import recurring_voice_privacy

    monkeypatch.setattr(store, 'active_ids', lambda *a: pytest.fail('unexpected recurring read'))
    user = db.collection('users').document('u')
    data = {'transcript_segments': [{'text': 'plain'}]}
    recurring_voice_privacy.filter_processing_write(db.transaction(), user, data)
    assert data == {'transcript_segments': [{'text': 'plain'}]}
