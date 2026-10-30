"""Unit tests for resilient deserialization of app reviews and API keys.

Verifies that malformed or legacy documents in Redis cache or Firestore
do not crash the reviews or API keys presentation endpoints with HTTP 500,
mirroring Person.deserialize_many_safe and Message.deserialize_many_safe.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from models.app import AppReview, AppApiKeyResponse
from database.apps import list_api_keys_db


class _MockDoc:
    """Mock Firestore DocumentSnapshot."""

    def __init__(self, doc_id: str, data: dict[str, Any]):
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class TestAppReviewResilientDeserialization(unittest.TestCase):
    """Test suite for AppReview.deserialize_safe and deserialize_many_safe."""

    def setUp(self):
        self.valid_review_dict = {
            'uid': 'user_123',
            'rated_at': '2026-10-01T12:00:00+00:00',
            'score': 4.5,
            'review': 'Great application!',
            'username': 'Alice',
            'response': 'Thank you!',
            'responded_at': '2026-10-01T13:00:00+00:00',
        }

    def test_deserialize_safe_falsy_and_invalid_types(self):
        self.assertIsNone(AppReview.deserialize_safe(None))
        self.assertIsNone(AppReview.deserialize_safe({}))
        self.assertIsNone(AppReview.deserialize_safe('invalid'))
        self.assertIsNone(AppReview.deserialize_safe(42))
        self.assertIsNone(AppReview.deserialize_safe([]))

    def test_deserialize_safe_valid_dict(self):
        review = AppReview.deserialize_safe(self.valid_review_dict)
        self.assertIsNotNone(review)
        self.assertEqual(review.uid, 'user_123')
        self.assertEqual(review.score, 4.5)
        self.assertEqual(review.review, 'Great application!')
        self.assertEqual(review.username, 'Alice')
        self.assertEqual(review.response, 'Thank you!')
        self.assertIsInstance(review.rated_at, datetime)
        self.assertIsInstance(review.responded_at, datetime)

    def test_deserialize_safe_with_datetime_objects(self):
        data = {
            'uid': 'user_456',
            'rated_at': datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
            'score': 5.0,
            'review': 'Works perfectly',
            'responded_at': datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc),
        }
        review = AppReview.deserialize_safe(data)
        self.assertIsNotNone(review)
        self.assertEqual(review.uid, 'user_456')
        self.assertEqual(review.score, 5.0)

    def test_deserialize_safe_malformed_missing_fields(self):
        # Missing required 'uid'
        bad_uid = dict(self.valid_review_dict)
        del bad_uid['uid']
        self.assertIsNone(AppReview.deserialize_safe(bad_uid))

        # Missing required 'rated_at'
        bad_rated_at = dict(self.valid_review_dict)
        del bad_rated_at['rated_at']
        self.assertIsNone(AppReview.deserialize_safe(bad_rated_at))

        # Missing required 'score'
        bad_score = dict(self.valid_review_dict)
        del bad_score['score']
        self.assertIsNone(AppReview.deserialize_safe(bad_score))

        # Missing required 'review'
        bad_review = dict(self.valid_review_dict)
        del bad_review['review']
        self.assertIsNone(AppReview.deserialize_safe(bad_review))

    def test_deserialize_safe_invalid_date_format(self):
        bad_date = dict(self.valid_review_dict, rated_at='not-a-datetime')
        self.assertIsNone(AppReview.deserialize_safe(bad_date))

    def test_deserialize_many_safe_empty(self):
        self.assertEqual(AppReview.deserialize_many_safe(None), [])
        self.assertEqual(AppReview.deserialize_many_safe({}), [])
        self.assertEqual(AppReview.deserialize_many_safe([]), [])

    def test_deserialize_many_safe_filters_malformed_and_empty_reviews(self):
        records = {
            'user_1': self.valid_review_dict,
            'user_2': {'uid': 'user_2', 'review': ''},  # empty review text
            'user_3': {'uid': 'user_3', 'rated_at': 'invalid', 'score': 1.0, 'review': 'Bad date'},
            'user_4': {'review': 'Missing uid and score'},
            'user_5': {
                'uid': 'user_5',
                'rated_at': '2026-10-02T08:00:00+00:00',
                'score': 3.0,
                'review': 'Average app',
            },
        }
        skipped: list[tuple[Any, Exception]] = []
        parsed = AppReview.deserialize_many_safe(
            records,
            on_error=lambda rec, exc: skipped.append((rec, exc)),
        )
        self.assertEqual(len(parsed), 2)
        self.assertEqual([r.uid for r in parsed], ['user_123', 'user_5'])
        self.assertEqual(len(skipped), 2)

    def test_deserialize_many_safe_filters_malformed_cached_reviews_payload(self):
        """Deserializer-level check; route coverage lives in test_app_reviews_api_keys_routes.py."""
        malformed_cache = {
            'u1': self.valid_review_dict,
            'u2': {'uid': 'u2', 'score': 'invalid', 'review': 'Broken score'},
            'u3': 'not_a_dict',
            'u4': {'uid': 'u4', 'rated_at': '2026-10-02T09:00:00Z', 'score': 5.0, 'review': 'Awesome'},
        }
        # In endpoint: reviews = get_app_reviews(app_id); return AppReview.deserialize_many_safe(reviews)
        results = AppReview.deserialize_many_safe(malformed_cache)
        self.assertEqual(len(results), 2)
        self.assertEqual([r.uid for r in results], ['user_123', 'u4'])


class TestAppApiKeyResilientDeserialization(unittest.TestCase):
    """Test suite for AppApiKeyResponse and list_api_keys resilience."""

    def setUp(self):
        self.valid_key = {
            'id': '01ARZ3NDEKTSV4RRFFQ69G5FAV',
            'label': 'Production Key',
            'created_at': datetime.now(timezone.utc),
            'secret': 'sk_live_12345',
        }

    def test_deserialize_safe_valid(self):
        key = AppApiKeyResponse.deserialize_safe(self.valid_key)
        self.assertIsNotNone(key)
        self.assertEqual(key.id, '01ARZ3NDEKTSV4RRFFQ69G5FAV')
        self.assertEqual(key.label, 'Production Key')

    def test_deserialize_safe_fills_default_label(self):
        key_no_label = {
            'id': '01ARZ3NDEKTSV4RRFFQ69G5FAV',
            'label': '',
        }
        key = AppApiKeyResponse.deserialize_safe(key_no_label)
        self.assertIsNotNone(key)
        self.assertEqual(key.label, 'API Key')

    def test_deserialize_safe_malformed_missing_id(self):
        key_no_id = {
            'label': 'Key without id',
        }
        self.assertIsNone(AppApiKeyResponse.deserialize_safe(key_no_id))

    def test_deserialize_many_safe(self):
        keys = [
            self.valid_key,
            {'label': 'No id key'},
            {'id': '01ARZ3NDEKTSV4RRFFQ69G5FA2', 'created_at': datetime.now(timezone.utc)},
            None,
            'string_entry',
        ]
        parsed = AppApiKeyResponse.deserialize_many_safe(keys)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].id, '01ARZ3NDEKTSV4RRFFQ69G5FAV')
        self.assertEqual(parsed[1].id, '01ARZ3NDEKTSV4RRFFQ69G5FA2')
        self.assertEqual(parsed[1].label, 'API Key')

    def test_list_api_keys_db_injects_doc_id_and_filters_hashed(self):
        doc1 = _MockDoc('doc_id_1', {'label': 'Key 1', 'hashed': 'secret_hash_1'})
        doc2 = _MockDoc('doc_id_2', {'id': 'explicit_id_2', 'label': 'Key 2', 'hashed': 'secret_hash_2'})

        mock_query = MagicMock()
        mock_query.stream.return_value = [doc1, doc2]

        mock_collection = MagicMock()
        mock_collection.order_by.return_value = mock_query

        mock_doc_ref = MagicMock()
        mock_doc_ref.collection.return_value = mock_collection

        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch('database.apps.db', mock_db):
            result = list_api_keys_db('app_test')
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['id'], 'doc_id_1')
            self.assertEqual(result[0]['label'], 'Key 1')
            self.assertNotIn('hashed', result[0])
            self.assertEqual(result[1]['id'], 'explicit_id_2')
            self.assertNotIn('hashed', result[1])

    def test_deserialize_many_safe_drops_corrupted_key_documents(self):
        """Deserializer-level check; route coverage lives in test_app_reviews_api_keys_routes.py."""
        raw_keys = [
            {'id': 'k1', 'label': 'Valid Key'},
            {'invalid': 'Missing ID entirely'},
            {'id': 'k2'},  # missing label, should get fallback 'API Key'
        ]
        # In endpoint: keys = list_api_keys_db(app_id); return AppApiKeyResponse.deserialize_many_safe(keys)
        res = AppApiKeyResponse.deserialize_many_safe(raw_keys)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].id, 'k1')
        self.assertEqual(res[0].label, 'Valid Key')
        self.assertEqual(res[1].id, 'k2')
        self.assertEqual(res[1].label, 'API Key')


if __name__ == '__main__':
    unittest.main()
