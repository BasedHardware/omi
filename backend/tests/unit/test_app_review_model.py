from datetime import datetime

from models.app import AppReview


def test_app_review_from_json_uses_public_schema_field_names():
    review = AppReview.from_json(
        {
            'uid': 'u1',
            'rated_at': '2026-07-02T12:34:56',
            'score': 4.5,
            'review': 'Helpful app',
            'username': 'David',
        }
    )

    assert review.uid == 'u1'
    assert review.rated_at == datetime(2026, 7, 2, 12, 34, 56)
    assert review.score == 4.5
    assert review.review == 'Helpful app'
    assert review.username == 'David'
