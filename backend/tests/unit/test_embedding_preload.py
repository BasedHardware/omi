"""Tests for cross-conversation speaker embedding persistence."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from utils.speaker_assignment import load_person_embeddings_cache


class TestLoadPersonEmbeddingsCache:
    """Tests for load_person_embeddings_cache."""

    @patch('utils.speaker_assignment.user_db')
    def test_loads_embeddings_for_people_with_data(self, mock_user_db):
        mock_user_db.get_people_with_embeddings.return_value = [
            {
                'id': 'person-1',
                'name': 'Alice',
                'speaker_embedding': [0.1] * 512,
            },
            {
                'id': 'person-2',
                'name': 'Bob',
                'speaker_embedding': [0.2] * 512,
            },
        ]

        cache = load_person_embeddings_cache('test-uid')

        assert len(cache) == 2
        assert 'person-1' in cache
        assert 'person-2' in cache
        assert cache['person-1']['name'] == 'Alice'
        assert cache['person-2']['name'] == 'Bob'
        assert cache['person-1']['embedding'].shape == (1, 512)
        assert cache['person-2']['embedding'].shape == (1, 512)

    @patch('utils.speaker_assignment.user_db')
    def test_returns_empty_cache_when_no_people(self, mock_user_db):
        mock_user_db.get_people_with_embeddings.return_value = []

        cache = load_person_embeddings_cache('test-uid')

        assert len(cache) == 0

    @patch('utils.speaker_assignment.user_db')
    def test_skips_people_with_invalid_embeddings(self, mock_user_db):
        mock_user_db.get_people_with_embeddings.return_value = [
            {
                'id': 'person-1',
                'name': 'Alice',
                'speaker_embedding': [0.1] * 512,
            },
            {
                'id': 'person-2',
                'name': 'Bob',
                'speaker_embedding': 'not-a-valid-embedding',
            },
        ]

        cache = load_person_embeddings_cache('test-uid')

        assert len(cache) == 1
        assert 'person-1' in cache

    @patch('utils.speaker_assignment.user_db')
    def test_reshapes_1d_embeddings(self, mock_user_db):
        mock_user_db.get_people_with_embeddings.return_value = [
            {
                'id': 'person-1',
                'name': 'Alice',
                'speaker_embedding': [0.5] * 256,
            },
        ]

        cache = load_person_embeddings_cache('test-uid')

        assert cache['person-1']['embedding'].shape == (1, 256)

    @patch('utils.speaker_assignment.user_db')
    def test_embedding_values_are_correct(self, mock_user_db):
        embedding_data = [float(i) / 10.0 for i in range(128)]
        mock_user_db.get_people_with_embeddings.return_value = [
            {
                'id': 'person-1',
                'name': 'Alice',
                'speaker_embedding': embedding_data,
            },
        ]

        cache = load_person_embeddings_cache('test-uid')

        expected = np.array(embedding_data, dtype=np.float32).reshape(1, -1)
        np.testing.assert_array_almost_equal(cache['person-1']['embedding'], expected)

    @patch('utils.speaker_assignment.user_db')
    def test_continues_after_single_failure(self, mock_user_db):
        """Ensure one bad embedding doesn't prevent loading others."""
        mock_user_db.get_people_with_embeddings.return_value = [
            {
                'id': 'person-1',
                'name': 'Alice',
                'speaker_embedding': [0.1] * 512,
            },
            {
                'id': 'person-2',
                'name': 'Bob',
                'speaker_embedding': None,  # Will cause np.array to fail meaningfully
            },
            {
                'id': 'person-3',
                'name': 'Charlie',
                'speaker_embedding': [0.3] * 512,
            },
        ]

        cache = load_person_embeddings_cache('test-uid')

        assert len(cache) == 2
        assert 'person-1' in cache
        assert 'person-3' in cache
