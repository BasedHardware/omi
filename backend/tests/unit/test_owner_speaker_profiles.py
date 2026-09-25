"""Live and sync owner caches share display names and stored voiceprints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from routers.listen import speakers
from utils.sync import pipeline


class _Persistence:
    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


@pytest.fixture
def profile_sources(monkeypatch):
    monkeypatch.setattr(speakers.user_db, 'get_people', lambda uid: [])
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    name = Mock(return_value='David')
    monkeypatch.setattr(speakers, 'get_user_name', name)
    monkeypatch.setattr(pipeline, 'get_user_name', name)
    return name


@pytest.mark.parametrize('has_audio', [False, True])
def test_live_loads_stored_embedding_and_resolved_name_without_audio(profile_sources, monkeypatch, has_audio):
    audio = Mock(side_effect=AssertionError('stored embedding must not download audio'))
    monkeypatch.setattr(speakers, 'get_profile_audio_if_exists', audio)
    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(request=SimpleNamespace(uid='u'), persistence=_Persistence(), has_speech_profile=has_audio)
    )
    asyncio.run(matcher._load_profiles())
    if not has_audio:
        # Excluded profiles are never read; the runtime owns un-gating via the
        # stored-embedding availability probe (a6b439f809).
        assert matcher.person_embeddings == {}
        profile_sources.assert_not_called()
        return
    owner = matcher.person_embeddings[speakers.USER_SELF_PERSON_ID]
    assert owner['name'] == 'David'
    np.testing.assert_array_equal(owner['embedding'], [[1.0, 0.0]])
    audio.assert_not_called()
    profile_sources.assert_called_once_with('u', False)
    assert asyncio.run(matcher.resolve_owner_name()) == 'David'
    assert profile_sources.call_count == 1


def test_sync_owner_cache_uses_resolved_name(profile_sources):
    cache = pipeline.build_person_embeddings_cache('u')
    assert cache[pipeline.USER_SELF_PERSON_ID]['name'] == 'David'
    np.testing.assert_array_equal(cache[pipeline.USER_SELF_PERSON_ID]['embedding'], [[1.0, 0.0]])
    profile_sources.assert_called_once_with('u')


def test_live_without_either_embedding_or_audio_skips_owner(profile_sources, monkeypatch):
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', lambda uid: None)
    audio = Mock(side_effect=AssertionError('no speech profile'))
    monkeypatch.setattr(speakers, 'get_profile_audio_if_exists', audio)
    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(request=SimpleNamespace(uid='u'), persistence=_Persistence(), has_speech_profile=False)
    )
    asyncio.run(matcher._load_profiles())
    assert matcher.person_embeddings == {}
    audio.assert_not_called()
    profile_sources.assert_not_called()


def test_live_audio_recovery_keeps_resolved_owner_name(profile_sources, monkeypatch):
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', lambda uid: None)
    monkeypatch.setattr(speakers, 'get_profile_audio_if_exists', lambda uid: 'fake.wav')
    monkeypatch.setattr(speakers, '_read_file', lambda path: b'synthetic')
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]]))
    save = Mock()
    monkeypatch.setattr(speakers.user_db, 'set_user_speaker_embedding', save)
    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(request=SimpleNamespace(uid='u'), persistence=_Persistence(), has_speech_profile=True)
    )
    asyncio.run(matcher._load_profiles())
    assert matcher.person_embeddings[speakers.USER_SELF_PERSON_ID]['name'] == 'David'
    save.assert_called_once_with('u', [1.0, 0.0])
