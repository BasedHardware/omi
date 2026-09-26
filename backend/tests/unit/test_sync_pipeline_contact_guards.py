from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from utils.sync import pipeline


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


def test_identify_speakers_for_segments_person_missing_name_or_id():
    uid = 'user-123'
    seg = MagicMock()
    seg.id = 'seg-1'
    seg.text = 'Hey Bob, how are you?'
    seg.speaker_id = 1
    transcript_segments = [seg]

    # Person found by name has id but missing name key
    person_doc = {'id': 'person-bob'}

    with patch('utils.sync.pipeline.detect_speaker_from_text', return_value='Bob'), patch(
        'database.users.get_person_by_name', return_value=person_doc
    ), patch('utils.sync.pipeline.build_person_embeddings_cache', return_value={}), patch(
        'utils.sync.pipeline.process_speaker_assigned_segments'
    ) as mock_process:
        pipeline.identify_speakers_for_segments(
            transcript_segments,
            None,
            {},
            uid,
            language='en',
        )
        assert mock_process.called
        # Check speaker_to_person_map passed to process_speaker_assigned_segments
        args, kwargs = mock_process.call_args
        speaker_map = args[2]
        assert 1 in speaker_map
        assert speaker_map[1] == ('person-bob', 'Bob')
