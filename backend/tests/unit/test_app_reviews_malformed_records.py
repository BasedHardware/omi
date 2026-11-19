from typing import Any
import pytest
from models.app import AppReview, App
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


class TestAppReviewSafeDeserialization:
    def test_deserialize_safe_valid(self):
        data = _valid_review_dict()
        review = AppReview.deserialize_safe(data)
        assert review is not None
        assert review.score == 4.5

    def test_deserialize_safe_malformed_non_dict(self):
        assert AppReview.deserialize_safe("not a dict") is None
        assert AppReview.deserialize_safe(None) is None

    def test_from_records_filters_malformed(self):
        records = [
            _valid_review_dict("u1"),
            "bad_record",
            _valid_review_dict("u2"),
        ]
        reviews = AppReview.from_records(records)
        assert len(reviews) == 2
        assert reviews[0].uid == "u1"
        assert reviews[1].uid == "u2"


class TestRatingAggregationSafety:
    def test_extract_rating_stats_clamping(self):
        reviews = {
            "u1": {"score": 10.0, "review": "a"},
            "u2": {"score": -1.0, "review": "b"},
        }
        avg, count = _extract_rating_stats(reviews)
        assert count == 2
        assert avg == 2.5

    def test_extract_rating_stats_missing_score(self):
        reviews = {
            "u1": {"review": "no score here"},
            "u2": {"score": 4.0, "review": "valid"},
        }
        avg, count = _extract_rating_stats(reviews)
        assert count == 1
        assert avg == 4.0

    def test_extract_rating_stats_non_dict_entries(self):
        reviews = {
            "u1": "not a dict",
            "u2": None,
            "u3": {"score": 3.0, "review": "valid"},
        }
        avg, count = _extract_rating_stats(reviews)
        assert count == 1
        assert avg == 3.0

    def test_extract_rating_stats_empty_input(self):
        assert _extract_rating_stats({}) == (None, 0)
        assert _extract_rating_stats([]) == (None, 0)
