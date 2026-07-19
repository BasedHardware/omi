"""Regression: an out-of-range app review score must not skew the marketplace ranking.

ReviewAppRequest.score is an unbounded float on the write path, so a review posted with a huge or
negative score used to flow into rating_avg (utils.apps averaging sites) and from there into
weighted_rating / compute_app_score, pinning one app to the top or bottom of every listing. The read
path already bounds score with Field(ge=0, le=5); _clamp_review_score closes the same bound on the
write boundary (set_app_review) and the aggregation sites without changing the request contract.
"""

import pytest

import utils.apps as apps_mod
from utils.apps import _clamp_review_score, set_app_review


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1e6, 5.0),
        (10, 5.0),
        (5, 5.0),
        (3.5, 3.5),
        (0, 0.0),
        (-1, 0.0),
        (-1e9, 0.0),
        ("bad", 0.0),
        (None, 0.0),
    ],
)
def test_clamp_review_score(raw, expected):
    assert _clamp_review_score(raw) == expected


def test_set_app_review_clamps_out_of_range_score(monkeypatch):
    captured = {}
    monkeypatch.setattr(apps_mod, "set_app_review_in_db", lambda app_id, uid, review: captured.update(review=review))
    monkeypatch.setattr(apps_mod, "set_app_review_cache", lambda app_id, uid, review: None)

    result = set_app_review("app1", "uid1", {"score": 1e6, "review": "great"})

    assert result == {"status": "ok"}
    assert captured["review"]["score"] == 5.0


def test_set_app_review_clamps_negative_score(monkeypatch):
    captured = {}
    monkeypatch.setattr(apps_mod, "set_app_review_in_db", lambda app_id, uid, review: captured.update(review=review))
    monkeypatch.setattr(apps_mod, "set_app_review_cache", lambda app_id, uid, review: None)

    set_app_review("app1", "uid1", {"score": -3})

    assert captured["review"]["score"] == 0.0
