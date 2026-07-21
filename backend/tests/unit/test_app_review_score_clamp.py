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


def _search_app_dict(app_id='a1'):
    return {
        'id': app_id,
        'name': 'Good App',
        'category': 'productivity',
        'author': 'Someone',
        'description': 'Does things',
        'image': 'http://img',
        'capabilities': ['chat'],
    }


def _search_with_reviews(monkeypatch, reviews):
    """Run the real /v2/apps/search handler over one app carrying `reviews`."""
    from routers import apps as routers_apps

    app_dict = _search_app_dict()
    monkeypatch.setattr(routers_apps, 'search_apps_db', lambda **kw: [dict(app_dict)])
    monkeypatch.setattr(routers_apps, 'get_enabled_apps', lambda uid: set())
    monkeypatch.setattr(routers_apps, 'get_apps_installs_count', lambda ids: {})
    monkeypatch.setattr(routers_apps, 'get_apps_reviews', lambda ids: {'a1': reviews})
    result = routers_apps.search_apps(
        q=None,
        category=None,
        rating=None,
        capability=None,
        sort=None,
        my_apps=None,
        installed_apps=None,
        offset=0,
        limit=20,
        uid='u1',
    )
    return result['data']


def test_search_averages_in_range_review_scores(monkeypatch):
    reviews = {'u1': {'score': 4, 'review': 'good'}, 'u2': {'score': 5, 'review': 'great'}}
    result = _search_with_reviews(monkeypatch, reviews)
    assert result[0]['rating_avg'] == 4.5
    assert result[0]['rating_count'] == 2


def test_search_reports_no_rating_without_reviews(monkeypatch):
    result = _search_with_reviews(monkeypatch, {})
    assert result[0]['rating_avg'] is None
    assert result[0]['rating_count'] == 0


def test_search_clamps_out_of_range_stored_review_score(monkeypatch):
    """A drifted/legacy stored score must not escape through the search endpoint.

    /v2/apps/search computed rating_avg itself and was the one aggregation path that
    skipped _clamp_review_score, even though the helper's docstring says it closes the
    bound "on the write and aggregation paths". App.rating_avg is unbounded, so a stored
    score of 100 surfaced verbatim, passed any `rating` filter and pinned the app to the
    top of sort=rating_desc — while every other listing endpoint reported 5.0.
    """
    reviews = {'u1': {'score': 100, 'review': 'gamed'}}
    result = _search_with_reviews(monkeypatch, reviews)
    assert result[0]['rating_avg'] == 5.0


def test_search_clamps_negative_stored_review_score(monkeypatch):
    reviews = {'u1': {'score': -50, 'review': 'sabotage'}}
    result = _search_with_reviews(monkeypatch, reviews)
    assert result[0]['rating_avg'] == 0.0


def test_search_rating_matches_the_single_app_endpoint(monkeypatch):
    """The search average must agree with utils.apps' aggregation for the same reviews."""
    reviews = {'u1': {'score': 100, 'review': 'gamed'}, 'u2': {'score': 4, 'review': 'ok'}}
    result = _search_with_reviews(monkeypatch, reviews)
    expected = sum(_clamp_review_score(r['score']) for r in reviews.values()) / len(reviews)
    assert result[0]['rating_avg'] == expected == 4.5


def test_every_rating_avg_aggregation_clamps_its_scores():
    """No aggregation may read a raw review score.

    The bug this guards was a single averaging expression that skipped
    _clamp_review_score while four identical ones in utils/apps.py applied it. Any line
    that comprehends over review scores must clamp, so a future site cannot quietly
    reintroduce the gap.
    """
    from pathlib import Path as _Path

    backend = _Path(__file__).resolve().parents[2]
    offenders = []
    for relative in ('utils/apps.py', 'routers/apps.py'):
        for number, line in enumerate((backend / relative).read_text(encoding='utf-8').splitlines(), start=1):
            if "['score']" in line and ' for ' in line and '_clamp_review_score' not in line:
                offenders.append(f'{relative}:{number}')
    assert offenders == [], f'unclamped review-score aggregation at: {offenders}'
