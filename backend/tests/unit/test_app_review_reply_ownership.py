import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

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
        stored[('app-1', 'user-1')] = existing
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, uid: _public_app())
    monkeypatch.setattr(apps, 'get_specific_user_review', lambda app_id, uid: stored.get((app_id, uid)))
    monkeypatch.setattr(apps, 'set_app_review', lambda app_id, uid, review: stored.__setitem__((app_id, uid), review))
    monkeypatch.setattr(apps, 'send_new_app_review_notification', lambda **kwargs: None)
    return stored


def test_reviewer_cannot_write_the_developer_reply(monkeypatch):
    stored = _install(monkeypatch)

    apps.review_app('app-1', apps.ReviewAppRequest(score=5, review='great', response='Official reply'), uid='user-1')

    assert stored[('app-1', 'user-1')]['response'] == ''


def test_posting_again_keeps_the_developer_reply(monkeypatch):
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

    apps.review_app('app-1', apps.ReviewAppRequest(score=4, review='better now'), uid='user-1')

    review = stored[('app-1', 'user-1')]
    assert review['score'] == 4
    assert review['review'] == 'better now'
    assert review['response'] == 'Fixed in 1.2, thanks'
    assert review['responded_at'] == '2026-01-02T00:00:00+00:00'
