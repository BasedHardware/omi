from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from utils.sync import pipeline


@pytest.fixture(autouse=True)
def paid_plan():
    # These guards cover naming other people, which is paid; declare the plan instead of reading it.
    with patch('utils.sync.speaker_identity.named_speaker_prompts_allowed', return_value=True), patch(
        'database.owner_profile_updates.get_user_speaker_embedding_recovery_state', return_value=None
    ):
        yield


def test_build_person_embeddings_cache_missing_id():
    uid = 'user-123'
    # Person with voiceprint but missing 'id'
    people = [
        {'name': 'Alice', 'speech_samples': [{'embedding': [0.1] * 192}]},
    ]
    with patch('database.users.get_user_speaker_embedding', return_value=None), patch(
        'database.users.get_people', return_value=people
    ), patch('utils.sync.pipeline.usable_person_voiceprint', return_value=[0.1] * 192):
        cache = pipeline.build_person_embeddings_cache(uid)
        # Should not crash with KeyError: 'id', and invalid person skipped
        assert len(cache) == 0


def test_build_person_embeddings_cache_missing_or_none_name():
    uid = 'user-123'
    # Person with voiceprint and id, but missing 'name' or None
    people = [
        {'id': 'p1', 'speech_samples': [{'embedding': [0.1] * 192}]},
        {'id': 'p2', 'name': None, 'speech_samples': [{'embedding': [0.2] * 192}]},
    ]
    with patch('database.users.get_user_speaker_embedding', return_value=None), patch(
        'database.users.get_people', return_value=people
    ), patch('utils.sync.pipeline.usable_person_voiceprint', side_effect=lambda p: [0.1] * 192):
        cache = pipeline.build_person_embeddings_cache(uid)
        assert 'p1' in cache
        assert cache['p1']['name'] == 'Unknown'
        assert isinstance(cache['p1']['embedding'], np.ndarray)
        assert 'p2' in cache
        assert cache['p2']['name'] == 'Unknown'


def test_sync_does_not_lookup_or_assign_a_text_match():
    seg = MagicMock()
    seg.id = 'seg-1'
    seg.text = 'My name is Bob.'
    seg.speaker_id = 1

    with patch('utils.sync.pipeline.detect_speaker_from_text', return_value='Bob') as detect, patch(
        'database.users.get_person_by_name', return_value={'id': 'person-bob'}
    ) as lookup, patch('utils.sync.pipeline.process_speaker_assigned_segments') as assign:
        pipeline.identify_speakers_for_segments([seg], None, {}, 'user-123', language='en')
        detect.assert_not_called()
        lookup.assert_not_called()
        assign.assert_not_called()
