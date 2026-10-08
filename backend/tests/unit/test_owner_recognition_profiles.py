"""Owner recognition survives ancillary reads and observes newly taught profiles."""

import asyncio
from types import SimpleNamespace
from datetime import datetime, timezone

import numpy as np
import pytest

from routers.listen import speakers
from database import users
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.stt import owner_profile
from tests.unit.test_owner_speaker_profiles import _Persistence
from utils.sync import speaker_identity as sync_identity
from utils.conversations import speaker_resolution as stage


def test_newly_taught_owner_is_loaded_despite_false_connection_latch(monkeypatch):
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    monkeypatch.setattr(speakers, 'get_user_name', lambda *a: 'Owner')
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', lambda uid: False)
    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(
            request=SimpleNamespace(uid='u', include_speech_profile=True),
            persistence=_Persistence(),
            has_speech_profile=False,
        )
    )
    asyncio.run(matcher._load_profiles())
    assert matcher.person_embeddings['user']['name'] == 'Owner'


def test_sync_name_failure_retains_owner_and_denies_free_people(monkeypatch):
    monkeypatch.setattr(sync_identity, 'named_speaker_prompts_allowed', lambda uid: False)
    monkeypatch.setattr(sync_identity.users_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])

    def missing_name(uid):
        raise RuntimeError('synthetic ancillary failure')

    deps = sync_identity.SpeakerIdentityDependencies(get_user_name=missing_name)
    cache = sync_identity.build_person_embeddings_cache('u', dependencies=deps)
    assert set(cache) == {'user'}
    np.testing.assert_array_equal(cache['user']['embedding'], [[1.0, 0.0]])


def test_resolution_failed_paid_people_read_retains_owner(monkeypatch):
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: True)

    def failed(uid):
        raise RuntimeError('synthetic people failure')

    monkeypatch.setattr(stage.users_db, 'get_people', failed)
    assert set(stage.load_voiceprints_for_resolution('u')) == {'user'}


def test_owner_recovery_cas_enrollment_and_deletion_win(monkeypatch):
    store = StrictFirestore()
    path = ('users', 'u')
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.rows[path] = {'speaker_embedding_updated_at': stamp}
    monkeypatch.setattr(users, 'get_firestore_client', lambda: store)
    assert users.recover_user_speaker_embedding('u', [1.0, 0.0], expected_updated_at=stamp)
    assert not users.recover_user_speaker_embedding('u', [0.0, 1.0], expected_updated_at=stamp)
    assert store.rows[path]['speaker_embedding'] == [1.0, 0.0]
    store.rows[path] = {'speaker_embedding_updated_at': stamp}
    store.rows[('account_deletions', 'u')] = {'wipe_status': 'pending'}
    assert not users.recover_user_speaker_embedding('u', [0.0, 1.0], expected_updated_at=stamp)
    assert 'speaker_embedding' not in store.rows[path]


@pytest.mark.parametrize('surface', ['sync', 'resolution'])
def test_legacy_enrollment_audio_repair_reaches_all_consumers(monkeypatch, surface):
    monkeypatch.setattr(users, 'get_user_speaker_embedding', lambda uid: None)
    monkeypatch.setattr(users, 'get_user_speaker_embedding_recovery_state', lambda uid: (None, None))
    monkeypatch.setattr(users, 'recover_user_speaker_embedding', lambda *a, **kw: True)
    load = lambda uid, **kw: owner_profile.load_owner_embedding(
        uid,
        users=users,
        audio_loader=lambda uid: 'fake',
        read_file=lambda path: b'enrolled',
        extractor=lambda *a: np.array([[1.0, 0.0]]),
    )
    if surface == 'sync':
        monkeypatch.setattr(sync_identity, 'load_owner_embedding', load)
        monkeypatch.setattr(sync_identity, 'named_speaker_prompts_allowed', lambda uid: False)
        cache = sync_identity.build_person_embeddings_cache(
            'u', dependencies=sync_identity.SpeakerIdentityDependencies(get_user_name=lambda uid: 'Owner')
        )
    else:
        monkeypatch.setattr(stage, 'load_owner_embedding', load)
        monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: False)
        cache = stage.load_voiceprints_for_resolution('u')
    assert set(cache) == {'user'}
