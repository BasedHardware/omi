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
from unittest.mock import AsyncMock, patch

from models.app import App, AppReview
from routers.apps import _safe_app_from_dict, get_or_create_user_persona
from utils.apps import _extract_rating_stats


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
    """Test suite for AppReview.deserialize_safe, AppReview.from_records, and compute_rating_stats."""

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

    def test_compute_rating_stats_valid_and_missing_fields(self):
        records = [
            {"uid": "u1", "score": 4.0, "review": "good"},
            {"uid": "u2", "review": "no score"},  # Missing score - must not raise KeyError
            {"uid": "u3", "score": "not-a-number", "review": "bad score"},  # Non-numeric score
            {"uid": "u4", "score": 5.0},  # Missing review - still has valid score
            {"uid": "u5", "score": 6.0, "review": "high score"},  # Out of range clamped to 5.0
            {"uid": "u6", "score": -2.0, "review": "negative score"},  # Negative clamped to 0.0
        ]
        # Valid scores: 4.0, 5.0, 5.0 (clamped), 0.0 (clamped) -> sum=14.0 / 4 = 3.5
        avg, count = AppReview.compute_rating_stats(records)
        self.assertEqual(count, 4)
        self.assertEqual(avg, 3.5)

    def test_compute_rating_stats_falsy_and_empty(self):
        self.assertEqual(AppReview.compute_rating_stats(None), (None, 0))
        self.assertEqual(AppReview.compute_rating_stats([]), (None, 0))
        self.assertEqual(AppReview.compute_rating_stats({}), (None, 0))
        self.assertEqual(AppReview.compute_rating_stats(""), (None, 0))
        self.assertEqual(AppReview.compute_rating_stats([{"uid": "u1"}]), (None, 0))


class TestRatingAggregationSafety(unittest.TestCase):
    """Test suite ensuring rating aggregation helpers tolerate missing fields without KeyError."""

    def test_extract_rating_stats_resilience(self):
        reviews = {
            "u1": {"uid": "u1", "score": 4.0, "review": "great"},
            "u2": {"uid": "u2", "review": "missing score entirely"},  # Missing 'score'
            "u3": "not-a-dict",  # Corrupted entry
            "u4": {"uid": "u4", "score": 10.0, "review": "out of range"},  # Clamped to 5.0
        }
        avg, count = _extract_rating_stats(reviews)
        self.assertEqual(count, 2)
        self.assertEqual(avg, 4.5)  # (4.0 + 5.0) / 2

    def test_extract_rating_stats_falsy(self):
        self.assertEqual(_extract_rating_stats(None), (None, 0))
        self.assertEqual(_extract_rating_stats({}), (None, 0))
        self.assertEqual(_extract_rating_stats([]), (None, 0))

    def test_reviews_list_extraction_missing_review_key(self):
        """Guard against KeyError: 'review' when raw Redis reviews miss 'review' key."""
        reviews = {
            "u1": {"uid": "u1", "score": 5.0, "review": "Valid"},
            "u2": {"uid": "u2", "score": 4.0},  # Missing 'review' key
            "u3": None,
        }
        filtered = [d for d in reviews.values() if isinstance(d, dict) and d.get("review")]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["uid"], "u1")


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


class TestEndpointResilience(unittest.IsolatedAsyncioTestCase):
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

    def test_safe_app_from_dict_contract_resilience(self):
        """Contract: When DB returns a malformed persona doc, _safe_app_from_dict returns None,
        allowing get_or_create_user_persona to fall back to generation instead of raising HTTP 500."""
        malformed_persona = {
            "id": "persona_corrupt",
            # missing required App fields: name, category, author, description, image, capabilities
        }
        self.assertIsNone(_safe_app_from_dict(malformed_persona))

        valid_persona = _valid_app_dict("persona_good")
        safe = _safe_app_from_dict(valid_persona)
        self.assertIsNotNone(safe)
        self.assertEqual(safe.id, "persona_good")

    async def test_get_or_create_user_persona_malformed_record_deleted_and_regenerated(self):
        """Contract: When DB returns a corrupt persona record, get_or_create_user_persona must delete
        the malformed document from Firestore and Redis cache before creating a replacement,
        preventing duplicate persona proliferation and non-convergent recovery."""
        import routers.apps as apps_router

        malformed_persona = {"id": "corrupt_persona_123", "uid": "user_test"}

        with (
            patch.object(apps_router, "get_user_persona_by_uid", return_value=malformed_persona),
            patch.object(apps_router, "delete_app_from_db") as mock_del_db,
            patch.object(apps_router, "delete_app_cache_by_id") as mock_del_cache,
            patch.object(
                apps_router,
                "get_user_from_uid",
                return_value={"display_name": "Test User", "email": "test@example.com"},
            ),
            patch.object(apps_router, "increment_username", return_value="testuser"),
            patch.object(apps_router, "generate_persona_prompt", new=AsyncMock(return_value="Generated Prompt")),
            patch.object(apps_router, "save_username"),
            patch.object(apps_router, "add_app_to_db") as mock_add_db,
        ):
            result = await get_or_create_user_persona(uid="user_test")

            # Corrupt persona must be cleaned up from DB and cache
            mock_del_db.assert_called_once_with("corrupt_persona_123")
            mock_del_cache.assert_called_once_with("corrupt_persona_123")

            # A new persona was created and added to DB
            mock_add_db.assert_called_once()
            self.assertEqual(result["uid"], "user_test")
            self.assertEqual(result["author"], "Test User")

    async def test_get_or_create_user_persona_valid_record_returned_without_deletion(self):
        """Contract: When DB returns a valid persona record, get_or_create_user_persona returns it
        immediately without calling delete_app_from_db or generating a new persona."""
        import routers.apps as apps_router

        valid_persona = _valid_app_dict("persona_existing")
        valid_persona["category"] = "personality-emulation"
        valid_persona["capabilities"] = ["persona"]

        with (
            patch.object(apps_router, "get_user_persona_by_uid", return_value=valid_persona),
            patch.object(apps_router, "delete_app_from_db") as mock_del_db,
            patch.object(apps_router, "delete_app_cache_by_id") as mock_del_cache,
            patch.object(apps_router, "add_app_to_db") as mock_add_db,
        ):
            result = await get_or_create_user_persona(uid="user_1")

            mock_del_db.assert_not_called()
            mock_del_cache.assert_not_called()
            mock_add_db.assert_not_called()
            self.assertEqual(result.id, "persona_existing")


if __name__ == "__main__":
    unittest.main()
