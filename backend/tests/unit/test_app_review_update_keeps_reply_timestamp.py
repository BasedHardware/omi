"""Regression: editing a review must not erase the developer's reply timestamp.

`PATCH /v1/apps/{app_id}/review` rebuilds the review document and `set_app_review`
writes it with Firestore `.set()`, which replaces the whole document. The handler
already carries over `response` and `rated_at`, but not `responded_at`, so a
reviewer editing their review after the developer replied deleted the reply
timestamp: the app's review list only renders "developer responded <time ago>"
when `responded_at` is present, so the reply silently lost its date.

The sibling POST route (posting the review again) preserves both the reply and its
timestamp; the edit path must keep them too.
"""

import routers.apps as apps


def _public_app() -> dict:
    return {
        'id': 'app-1',
        'uid': 'developer-1',
        'name': 'Daily Journal',
        'category': 'productivity-and-organization',
        'author': 'Developer',
        'description': 'Summarizes the day',
        'image': 'https://example.com/icon.png',
        'capabilities': {'memories'},
        'approved': True,
        'private': False,
    }


def _install(monkeypatch, existing=None):
    stored = {}
    if existing is not None:
        stored[('app-1', 'user-1')] = dict(existing)
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, uid: _public_app())
    monkeypatch.setattr(apps, 'get_specific_user_review', lambda app_id, uid: stored.get((app_id, uid)))
    monkeypatch.setattr(apps, 'set_app_review', lambda app_id, uid, review: stored.__setitem__((app_id, uid), review))
    monkeypatch.setattr(apps, 'send_new_app_review_notification', lambda **kwargs: None)
    return stored


def test_editing_a_review_keeps_the_developer_reply_timestamp(monkeypatch):
    stored = _install(
        monkeypatch,
        existing={
            'score': 2,
            'review': 'meh',
            'uid': 'user-1',
            'rated_at': '2026-01-01T00:00:00+00:00',
            'response': 'Fixed in 1.2, thanks',
            'responded_at': '2026-01-02T00:00:00+00:00',
        },
    )

    result = apps.update_app_review('app-1', apps.ReviewAppRequest(score=4, review='better now'), uid='user-1')

    assert result == {'status': 'ok'}
    review = stored[('app-1', 'user-1')]
    assert review['score'] == 4
    assert review['review'] == 'better now'
    assert review['response'] == 'Fixed in 1.2, thanks'
    assert review['responded_at'] == '2026-01-02T00:00:00+00:00'
    assert review['rated_at'] == '2026-01-01T00:00:00+00:00'


def test_editing_a_review_without_a_reply_adds_no_reply_timestamp(monkeypatch):
    stored = _install(
        monkeypatch,
        existing={
            'score': 3,
            'review': 'ok',
            'uid': 'user-1',
            'rated_at': '2026-01-01T00:00:00+00:00',
        },
    )

    apps.update_app_review('app-1', apps.ReviewAppRequest(score=5), uid='user-1')

    assert 'responded_at' not in stored[('app-1', 'user-1')]
