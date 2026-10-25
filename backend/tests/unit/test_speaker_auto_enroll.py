"""Explicit consent, measured evidence, encrypted pools and publication fences."""

import json
import struct
from datetime import datetime, timezone

import numpy as np
import pytest

from database import speaker_auto_enroll as db
from database import conversations as conversations_db
from database import users as users_db
from database.speaker_learning_fields import project_person_learning
from models.other import Person
from utils.speakers import auto_enroll as p
from utils.stt.voiceprints import usable_person_voiceprint
from utils import speaker_auto_enroll as workflow
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID, PID, CID = 'owner-a', 'person-a', 'conversation-a'
NOW = datetime.now(timezone.utc)
OWNER = [1.0, *([0.0] * 255)]
VOICE = [0.0, 1.0, *([0.0] * 254)]


def source():
    segments = [
        dict(
            id=f's{i}',
            start=i * 6.0,
            end=i * 6.0 + 5,
            speaker_id=1,
            speaker_id_scope='capture-a',
            person_id=PID,
            is_user=False,
        )
        for i in range(2)
    ]
    return {
        'private_cloud_sync_enabled': True,
        'transcript_segments': segments,
        'manual_speaker_assignments': {
            'generation': 1,
            'speakers': {'1': dict(person_id=PID, is_user=False, use_for_speech_training=True, generation=1)},
        },
    }


def evidence(conversation=None):
    conversation = conversation or source()
    return {
        s['id']: dict(binding=p.binding(s), window=[s['start'], s['end']], seconds=5, vector=VOICE)
        for s in conversation['transcript_segments']
    }


def contribution(cid=CID, at=None, vector=VOICE):
    return dict(
        conversation_id=cid,
        segment_ids=['s0', 's1'],
        vector=vector,
        model=p.MODEL,
        seconds=10,
        generation=1,
        **({'at': at} if at is not None else {}),
    )


def pick(c=None, e=None, owner=OWNER):
    return p.candidate(c or source(), PID, ['s0', 's1'], evidence() if e is None else e, owner)


def test_clean_explicit_disjoint_voice_is_accepted():
    chosen = pick()
    assert chosen['seconds'] == 10 and chosen['segment_ids'] == ['s0', 's1']
    assert chosen['vector'] == VOICE


@pytest.mark.parametrize(
    'case',
    [
        'automatic',
        'carried',
        'no_training',
        'owner',
        'foreign_overlap',
        'stale',
        'short',
        'unmeasured',
        'mixed',
        'dimensions',
        'overlap',
    ],
)
def test_invalid_evidence_abstains(case):
    c, e = source(), evidence()
    d = c['manual_speaker_assignments']['speakers']['1']
    if case == 'automatic':
        c['manual_speaker_assignments'] = {}
    elif case == 'carried':
        d['source'] = 'carried'
    elif case == 'no_training':
        d['use_for_speech_training'] = False
    elif case == 'owner':
        e['s0']['vector'] = OWNER
    elif case == 'foreign_overlap':
        c['transcript_segments'].append(dict(id='foreign', start=1, end=9, speaker_id=2, speaker_id_scope='capture-a'))
    elif case == 'stale':
        c['transcript_segments'][0]['start'] = 0.1
    elif case == 'short':
        e.pop('s1')
    elif case == 'unmeasured':
        e['s0']['seconds'] = 0
    elif case == 'mixed':
        e['s1']['vector'] = [-v for v in VOICE]
    elif case == 'dimensions':
        e['s1']['vector'] = [1, 0]
    elif case == 'overlap':
        e['s1']['window'] = [4, 9]
    assert pick(c, e) is None


@pytest.mark.parametrize('owner', [None, [], [1, 0], [float('nan')] * 256])
def test_missing_or_incompatible_owner_abstains(owner):
    assert pick(owner=owner) is None


def test_cache_requires_model_measurement_and_exact_binding():
    c = source()
    h = dict(
        v=1,
        ids=['s0', 's1'],
        durations=[5, 5],
        dim=256,
        enrollment_model=p.MODEL,
        evidence_seconds={'s0': 5, 's1': 5},
        enrollment_bindings={
            k: {field: value for field, value in row.items() if field in ('binding', 'window')}
            for k, row in evidence(c).items()
        },
    )

    def encode():
        header = json.dumps(h).encode()
        return struct.pack('>I', len(header)) + header + np.array([VOICE, VOICE], dtype='<f2').tobytes()

    assert pick(c, p.decode_evidence(encode())) is not None
    h.pop('enrollment_model')
    assert p.decode_evidence(encode()) == {}
    assert p.decode_evidence(b'invalid') == {}


def test_cache_writer_only_grants_authority_to_fresh_or_unchanged_bound_vectors():
    bindings = {'s0': {'binding': 'current', 'window': [0, 5]}}
    value = (5, np.asarray(VOICE))
    cache = {'s0': value}
    assert p.accepted_bindings(bindings, cache, dict(cache), {}) == {}
    prior = {'s0': {'binding': 'old', 'window': [0, 5]}}
    assert p.accepted_bindings(bindings, cache, dict(cache), prior) == {}
    assert p.accepted_bindings(bindings, cache, dict(cache), bindings) == bindings
    assert p.accepted_bindings(bindings, cache, {}, {}) == bindings


def test_encryption_is_owner_and_person_bound_and_kill_switch_stops_use(monkeypatch):
    blob = p.seal(UID, PID, [contribution(at=NOW.timestamp())])
    assert 'vector' not in blob and CID not in blob
    assert p.open_pool('different-owner', PID, blob) == []
    assert p.open_pool(UID, 'different-person', blob) == []
    person = dict(id=PID, **{p.POOL_FIELD: blob})
    assert usable_person_voiceprint(person, uid=UID, auto_enroll_allowed=True) == VOICE
    assert usable_person_voiceprint(person, uid=UID) is None
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    assert usable_person_voiceprint(person, uid=UID, auto_enroll_allowed=True) is None
    assert p.retract(UID, PID, blob, [CID], ['s0'])


def test_independent_manual_audio_replacement_cannot_be_shadowed_by_old_pool():
    blob = p.seal(UID, PID, [contribution(at=NOW.timestamp())])
    replacement = [0.0, 0.0, 1.0, *([0.0] * 253)]
    person = dict(
        id=PID,
        speaker_embedding=replacement,
        speech_samples=['synthetic.wav'],
        speech_samples_version=3,
        **{p.POOL_FIELD: blob},
    )
    assert p.usable(UID, person, True) is None
    assert usable_person_voiceprint(person, uid=UID, auto_enroll_allowed=True) == replacement


def test_pool_caps_decay_expiration_refresh_and_incompatible_replacement():
    now = NOW.timestamp()
    entries = []
    for i in range(7):
        entries = p.refresh(entries, contribution(str(i)), now + i)
    assert len(entries) == 5 and [e['conversation_id'] for e in entries] == ['2', '3', '4', '5', '6']
    retried = p.refresh(entries, contribution('6'), now + 30)
    assert len(retried) == 5 and retried[-1]['at'] == now + 6
    assert p.refresh(entries, contribution('different', vector=[-v for v in VOICE]), now + 10) is None
    assert p.vector(entries, now + p.MAX_AGE_SECONDS + 7) is None
    other = [0.0, 0.8, 0.6, *([0.0] * 253)]
    result = p.vector([contribution('old', now - p.HALF_LIFE_SECONDS), contribution('new', now, other)], now)
    assert result[2] / result[1] == pytest.approx(1.2 / 2.6)


@pytest.fixture
def store():
    return StrictFirestore(
        {
            ('users', UID): dict(
                private_cloud_sync_enabled=True, save_other_voice_profiles=True, speaker_embedding=OWNER
            ),
            ('users', UID, 'people', PID): dict(id=PID, updated_at=NOW, speech_samples=[]),
            ('users', UID, 'conversations', CID): source(),
        }
    )


def publish(store):
    return db.publish(UID, PID, CID, ['s0', 's1'], evidence(), NOW, 1, firestore_client=store)


def test_publication_and_retraction_are_strict_transactions(store):
    assert publish(store)
    person_path = ('users', UID, 'people', PID)
    assert p.open_pool(UID, PID, store.rows[person_path][p.POOL_FIELD])[0]['seconds'] == 10
    assert store.rows[('users', UID)][db.OWNER_INDEX] == [PID]
    db.retract_conversation(UID, CID, firestore_client=store)
    assert p.open_pool(UID, PID, store.rows[person_path][p.POOL_FIELD]) == []
    assert not publish(store)


@pytest.mark.parametrize(
    'race',
    [
        'sync_off',
        'save_off',
        'source_sync_off',
        'correction',
        'person_version',
        'person_deleted',
        'conversation_deleted',
        'locked',
        'discarded',
        'tombstone',
        'account_deletion',
        'kill',
    ],
)
def test_publication_rechecks_every_authority(store, monkeypatch, race):
    user = store.rows[('users', UID)]
    person = store.rows[('users', UID, 'people', PID)]
    c = store.rows[('users', UID, 'conversations', CID)]
    if race == 'sync_off':
        user['private_cloud_sync_enabled'] = False
    elif race == 'save_off':
        user['save_other_voice_profiles'] = False
    elif race == 'source_sync_off':
        c['private_cloud_sync_enabled'] = False
    elif race == 'correction':
        c['manual_speaker_assignments']['speakers']['1']['person_id'] = 'different'
    elif race == 'person_version':
        person['updated_at'] = None
    elif race == 'person_deleted':
        store.rows.pop(('users', UID, 'people', PID))
    elif race == 'conversation_deleted':
        store.rows.pop(('users', UID, 'conversations', CID))
    elif race in ('locked', 'discarded'):
        c['is_locked' if race == 'locked' else race] = True
    elif race == 'tombstone':
        store.rows[('users', UID, 'deleted_conversations', CID)] = {'deleted': True}
    elif race == 'account_deletion':
        store.rows[('account_deletions', UID)] = {'wipe_status': 'running'}
        with pytest.raises(Exception, match='account deletion'):
            publish(store)
        return
    elif race == 'kill':
        monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    assert not publish(store)
    assert not store.transactions[-1].updates


@pytest.mark.parametrize('setting', ['private_cloud_sync_enabled', 'save_other_voice_profiles'])
def test_privacy_optout_removes_indexed_pools_atomically(store, setting):
    assert publish(store)
    db.update_privacy(UID, {setting: False}, firestore_client=store)
    assert store.rows[('users', UID)][setting] is False
    assert store.rows[('users', UID)][db.OWNER_INDEX] == []
    assert store.rows[('users', UID, 'people', PID)][p.POOL_FIELD] is db.firestore.DELETE_FIELD


def test_privacy_off_on_cannot_resurrect_an_attempt_started_before_optout(store):
    db.update_privacy(UID, {'private_cloud_sync_enabled': False}, firestore_client=store)
    db.update_privacy(UID, {'private_cloud_sync_enabled': True}, firestore_client=store)
    assert not publish(store)


def test_assignment_correction_retracts_pool_with_receipt_even_when_killed(store, monkeypatch):
    assert publish(store)
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    store.rows[('users', UID, 'people', 'replacement')] = {'id': 'replacement', 'name': 'Synthetic'}
    conversations_db.assign_conversation_speaker(
        UID,
        CID,
        person_id='replacement',
        segment_ids=['s0'],
        firestore_client=store,
    )
    blob = store.rows[('users', UID, 'people', PID)][p.POOL_FIELD]
    assert p.open_pool(UID, PID, blob) == []
    row = store.rows[('users', UID, 'conversations', CID)]
    receipt = conversations_db.decode_manual_speaker_assignments(
        UID,
        row['manual_speaker_assignments'],
        bool(row.get('manual_speaker_assignments_compressed')),
    )
    assert receipt['segments']['s0']['person_id'] == 'replacement'


def test_readiness_projects_a_vector_without_claiming_audio_exists(store):
    assert publish(store)
    raw = store.rows[('users', UID, 'people', PID)]
    data = project_person_learning(UID, raw, firestore_client=store)
    assert data['voice_readiness'] == 'ready' and data['speech_samples'] == []
    person = Person(**{**data, 'name': 'Synthetic'})
    assert person.voice_readiness == 'ready' and person.voice_learning_state == 'learned'
    public = person.model_dump(mode='json')
    assert p.POOL_FIELD not in public and 'speaker_embedding' not in public


def test_no_training_overlap_cannot_ride_along_in_a_same_voice_clip():
    c, e = source(), evidence()
    c['transcript_segments'].append({**c['transcript_segments'][0], 'id': 'refused', 'start': 2, 'end': 4})
    c['manual_speaker_assignments']['segments'] = {
        'refused': dict(person_id=PID, generation=2, use_for_speech_training=False)
    }
    assert pick(c, e) is None


@pytest.mark.parametrize(
    'case', ['valid', 'owner', 'missing_owner', 'dimension', 'privacy_epoch', 'sync_off', 'source_off', 'tombstone']
)
def test_audio_fallback_rechecks_owner_retention_and_privacy_in_publication(store, monkeypatch, case):
    monkeypatch.setattr(users_db, 'db', store)
    owner = store.rows[('users', UID)]
    embedding = VOICE
    if case == 'owner':
        embedding = OWNER
    elif case == 'missing_owner':
        owner.pop('speaker_embedding')
    elif case == 'dimension':
        embedding = [1.0, 0.0]
    elif case == 'privacy_epoch':
        owner[db.PRIVACY_VERSION] = 1
    elif case == 'sync_off':
        owner['private_cloud_sync_enabled'] = False
    elif case == 'source_off':
        store.rows[('users', UID, 'conversations', CID)]['private_cloud_sync_enabled'] = False
    elif case == 'tombstone':
        store.rows[('users', UID, 'deleted_conversations', CID)] = {'deleted': True}
    user = store.collection('users').document(UID)
    result = users_db._replace_speech_profile_transaction(
        store.transaction(),
        user.collection('people').document(PID),
        NOW,
        {'speaker_embedding': embedding},
        user_ref=user,
        source=(UID, CID, ['s0', 's1'], 1),
        enrollment_privacy_version=0,
    )
    assert (result is not None) is (case == 'valid')
    assert bool(store.transactions[-1].updates) is (case == 'valid')


@pytest.mark.parametrize('case', ['valid', 'owner', 'missing_target', 'missing_owner', 'sync_off', 'source_off'])
def test_vector_worker_distinguishes_missing_evidence_from_authority_rejection(store, monkeypatch, case):
    rows = evidence()
    if case == 'owner':
        rows['s0']['vector'] = OWNER
    elif case == 'missing_target':
        for row in rows.values():
            row['binding'] = 'another-voice'
    elif case == 'missing_owner':
        store.rows[('users', UID)].pop('speaker_embedding')
    elif case == 'sync_off':
        store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    elif case == 'source_off':
        store.rows[('users', UID, 'conversations', CID)]['private_cloud_sync_enabled'] = False
    monkeypatch.setattr(workflow, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(workflow.users, 'get_person', lambda *args: store.rows[('users', UID, 'people', PID)])
    monkeypatch.setattr(
        workflow.conversations, 'get_conversation', lambda *args: store.rows[('users', UID, 'conversations', CID)]
    )
    monkeypatch.setattr(workflow, 'download_owner_evidence_cache', lambda *args: b'synthetic-cache')
    monkeypatch.setattr(workflow.policy, 'decode_evidence', lambda *args: rows)
    expected = {
        'valid': 'stored',
        'owner': 'rejected_quality',
        'missing_target': None,
        'missing_owner': 'rejected_embedding',
        'sync_off': 'disabled',
        'source_off': 'disabled',
    }
    assert workflow.enroll(UID, PID, CID, ['s0', 's1']) == expected[case]
