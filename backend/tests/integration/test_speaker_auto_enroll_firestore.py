"""Synthetic loopback proof that pool and cache authority commit together."""

from datetime import datetime, timezone

import pytest

from database import speaker_auto_enroll as db
from database import conversations, person_aliases
from tests.integration.test_batch_pipeline_deletion_firestore import state  # noqa: F401
from utils.speakers import auto_enroll as policy

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('revocation', ['source', 'correction', 'person', 'dismiss', 'privacy'])
def test_pool_authority_publication_and_revocation_on_real_firestore(state, monkeypatch, revocation):
    store, uid, user, _, _ = state
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'true')
    monkeypatch.setattr(policy.encryption, 'derive_key', lambda owner: b's' * 32)
    owner = [1.0, *([0.0] * 255)]
    voice = [0.0, 1.0, *([0.0] * 254)]
    user.update(dict(private_cloud_sync_enabled=True, save_other_voice_profiles=True, speaker_embedding=owner))
    person = user.collection('people').document('synthetic-person')
    stamp = datetime.now(timezone.utc)
    person.set(dict(id=person.id, name='Synthetic', updated_at=stamp))
    segments = [
        dict(id=f's{i}', start=i * 6.0, end=i * 6.0 + 5, speaker_id=1, is_user=False, person_id=person.id)
        for i in range(2)
    ]
    user.collection('conversations').document('source').set(
        dict(
            private_cloud_sync_enabled=True,
            transcript_segments=segments,
            manual_speaker_assignments=dict(
                generation=1,
                speakers={'1': dict(person_id=person.id, is_user=False, use_for_speech_training=True, generation=1)},
            ),
        )
    )
    evidence = {
        s['id']: dict(binding=policy.binding(s), window=[s['start'], s['end']], seconds=5, vector=voice)
        for s in segments
    }
    assert db.publish(uid, person.id, 'source', ['s0', 's1'], evidence, stamp, 1, firestore_client=store.client)
    old_person = person.get().to_dict()
    before = db.context(uid, firestore_client=store.client)
    cached = dict(embedding=policy.usable(uid, old_person, before), **policy.cache_authority(uid, old_person, before))
    assert cached['embedding'] == voice
    assert policy.cached_authorized(person.id, cached, before)
    assert before[policy.AUTHORITY_FIELD][person.id] == policy.pool_token(old_person[policy.POOL_FIELD])
    # All revocation paths stay effective while publication/use is disabled.
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'false')
    if revocation == 'source':
        db.retract_conversation(uid, 'source', firestore_client=store.client)
    elif revocation == 'correction':
        user.collection('people').document('replacement').set({'id': 'replacement', 'name': 'Synthetic replacement'})
        conversations.assign_conversation_speaker(
            uid, 'source', person_id='replacement', segment_ids=['s0'], firestore_client=store.client
        )
    elif revocation == 'person':
        db.revoke_person(uid, person.id, firestore_client=store.client)
    elif revocation == 'dismiss':
        assert person_aliases.dismiss_person_transaction(store.client.transaction(), person)
    else:
        db.update_privacy(uid, {'save_other_voice_profiles': False}, firestore_client=store.client)
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'true')
    after = db.context(uid, firestore_client=store.client)
    assert person.id not in after[policy.AUTHORITY_FIELD]
    assert not policy.cached_authorized(person.id, cached, after)
    assert policy.usable(uid, old_person, after) is None
    if revocation != 'dismiss':
        assert not person.get().to_dict().get(policy.POOL_FIELD)
    else:
        assert person.get().to_dict()['is_dismissed'] is True
    if revocation == 'source':
        assert user.collection('conversations').document('source').get().to_dict()['deleted']
    if revocation == 'person':
        current = person.get().to_dict()
        assert current[policy.REVOKED_FIELD] is True
        assert not db.publish(
            uid, person.id, 'source', ['s0', 's1'], evidence, current['updated_at'], 1, firestore_client=store.client
        )
