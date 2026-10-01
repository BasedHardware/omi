"""Unit tests verifying safe AppReview deserialization and endpoint resilience against malformed records.

Ensures that malformed, legacy, or poison review records in Redis/Firestore do not
trigger unhandled ResponseValidationError / HTTP 500 crashes on:
- GET /v1/apps/{app_id}/reviews
- GET /v1/apps/{app_id} (App.reviews / App.user_review)
- POST /v1/user/persona
"""

from datetime import datetime
from typing import Any
import unittest

from models.app import App, AppReview


def _valid_review_dict(uid: str = "user_1") -> dict[str, Any]:
    return {
        "uid": uid,
        "rated_at": "2026-07-02T12:34:56",
        "score": 4.5,
        "review": "Excellent companion app",
        "username": "Alex",
        "response": "Thank you for the review!",
        "responded_at": "2026-07-02T13:00:00",
    }


def _valid_app_dict(app_id: str = "app_123") -> dict[str, Any]:
    return {
        "id": app_id,
        "name": "Test App",
        "category": "productivity",
        "author": "Tester",
        "description": "A valid test application",
        "image": "https://example.com/icon.png",
        "capabilities": ["chat"],
        "approved": True,
        "uid": "user_1",
    }


class TestAppReviewSafeDeserialization(unittest.TestCase):
    """Test suite for AppReview.deserialize_safe and AppReview.from_records."""

    def test_deserialize_safe_valid_review(self):
        data = _valid_review_dict("u1")
        review = AppReview.deserialize_safe(data)

        self.assertIsNotNone(review)
        self.assertEqual(review.uid, "u1")
        self.assertEqual(review.score, 4.5)
        self.assertEqual(review.review, "Excellent companion app")
        self.assertEqual(review.username, "Alex")
        self.assertEqual(review.rated_at, datetime(2026, 7, 2, 12, 34, 56))

    def test_deserialize_safe_existing_instance(self):
        original = AppReview(
            uid="u1",
            rated_at=datetime(2026, 7, 2, 12, 0, 0),
            score=5.0,
            review="Superb",
        )
        safe = AppReview.deserialize_safe(original)
        self.assertIs(safe, original)

    def test_deserialize_safe_non_dict_and_falsy(self):
        self.assertIsNone(AppReview.deserialize_safe(None))
        self.assertIsNone(AppReview.deserialize_safe({}))
        self.assertIsNone(AppReview.deserialize_safe(""))
        self.assertIsNone(AppReview.deserialize_safe(12345))
        self.assertIsNone(AppReview.deserialize_safe(["not", "a", "dict"]))

    def test_deserialize_safe_missing_required_fields(self):
        malformed = [
            {"uid": "u1"},  # Missing rated_at, score, review
            {"uid": "u2", "score": 5.0},  # Missing rated_at, review
            {"uid": "u3", "score": 5.0, "review": "Great"},  # Missing rated_at
            {"rated_at": "2026-07-02T12:00:00", "score": 5.0, "review": "No uid"},  # Missing uid
        ]
        for item in malformed:
            self.assertIsNone(AppReview.deserialize_safe(item))

    def test_deserialize_safe_invalid_types_and_empty_strings(self):
        # Empty string rated_at from legacy records
        self.assertIsNone(
            AppReview.deserialize_safe(
                {
                    "uid": "u1",
                    "rated_at": "",
                    "score": 5.0,
                    "review": "Legacy review with empty date",
                }
            )
        )

        # Invalid date format
        self.assertIsNone(
            AppReview.deserialize_safe(
                {
                    "uid": "u2",
                    "rated_at": "invalid-datetime-string",
                    "score": 5.0,
                    "review": "Corrupt date",
                }
            )
        )

        # Invalid score type
        self.assertIsNone(
            AppReview.deserialize_safe(
                {
                    "uid": "u3",
                    "rated_at": "2026-07-02T12:00:00",
                    "score": "five-stars",
                    "review": "Non-numeric score",
                }
            )
        )

    def test_from_records_skips_malformed_and_preserves_valid(self):
        records = [
            _valid_review_dict("valid_1"),
            {"uid": "malformed_1", "rated_at": "", "score": 5.0, "review": "bad date"},
            {"uid": "empty_review", "rated_at": "2026-07-02T12:00:00", "score": 5.0, "review": ""},
            {"uid": "no_review", "rated_at": "2026-07-02T12:00:00", "score": 5.0},
            _valid_review_dict("valid_2"),
            None,
            "invalid_record",
        ]

        result = AppReview.from_records(records)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].uid, "valid_1")
        self.assertEqual(result[1].uid, "valid_2")
        self.assertTrue(all(isinstance(r, AppReview) for r in result))

    def test_from_records_handles_redis_dict_format(self):
        redis_data = {
            "user_1": _valid_review_dict("user_1"),
            "user_2": {"uid": "user_2", "rated_at": "", "score": 1.0, "review": "corrupted"},
            "user_3": _valid_review_dict("user_3"),
        }

        result = AppReview.from_records(redis_data)
        self.assertEqual(len(result), 2)
        self.assertEqual([r.uid for r in result], ["user_1", "user_3"])

    def test_from_records_falsy_and_empty_inputs(self):
        self.assertEqual(AppReview.from_records(None), [])
        self.assertEqual(AppReview.from_records([]), [])
        self.assertEqual(AppReview.from_records({}), [])
        self.assertEqual(AppReview.from_records(""), [])


class TestAppModelReviewFieldSanitization(unittest.TestCase):
    """Test suite ensuring App model fields tolerate malformed review documents."""

    def test_app_reviews_field_sanitizes_malformed_entries(self):
        app_data = _valid_app_dict("app_with_reviews")
        app_data["reviews"] = [
            _valid_review_dict("u1"),
            {"uid": "u2", "rated_at": "", "score": 4.0, "review": "poison date"},
            _valid_review_dict("u3"),
        ]

        app = App(**app_data)
        self.assertEqual(len(app.reviews), 2)
        self.assertEqual([r.uid for r in app.reviews], ["u1", "u3"])

    def test_app_user_review_field_sanitizes_malformed_entry(self):
        app_data = _valid_app_dict("app_with_bad_user_review")
        app_data["user_review"] = {"uid": "u_bad", "rated_at": "", "score": 3.0, "review": "bad"}

        app = App(**app_data)
        self.assertIsNone(app.user_review)

        # When valid
        app_data["user_review"] = _valid_review_dict("u_good")
        app_valid = App(**app_data)
        self.assertIsNotNone(app_valid.user_review)
        self.assertEqual(app_valid.user_review.uid, "u_good")


class TestEndpointResilience(unittest.TestCase):
    """Test suite ensuring endpoint logic recovers cleanly from malformed records."""

    def test_app_reviews_endpoint_contract_resilience(self):
        """Contract: When Redis returns review records containing malformed or legacy documents,
        AppReview.from_records safely produces valid AppReview instances without raising ValidationError."""
        redis_reviews = {
            "u1": _valid_review_dict("u1"),
            "u_legacy_corrupt": {"uid": "u_legacy_corrupt", "rated_at": "", "score": 5.0, "review": "corrupt date"},
            "u_missing_fields": {"review": "only review text"},
            "u2": _valid_review_dict("u2"),
        }

        # Simulating endpoint logic: return AppReview.from_records(reviews.values())
        result = AppReview.from_records(redis_reviews.values())
        self.assertEqual(len(result), 2)
        self.assertEqual([r.uid for r in result], ["u1", "u2"])
        for r in result:
            self.assertIsInstance(r, AppReview)

    def test_persona_safe_deserialization_contract_resilience(self):
        """Contract: When DB returns a malformed persona doc, App.deserialize_safe returns None,
        allowing get_or_create_user_persona to fall back to generation instead of raising HTTP 500."""
        malformed_persona = {
            "id": "persona_corrupt",
            # missing required App fields: name, category, author, description, image, capabilities
        }
        self.assertIsNone(App.deserialize_safe(malformed_persona))

        valid_persona = _valid_app_dict("persona_good")
        safe = App.deserialize_safe(valid_persona)
        self.assertIsNotNone(safe)
        self.assertEqual(safe.id, "persona_good")


if __name__ == "__main__":
    unittest.main()
