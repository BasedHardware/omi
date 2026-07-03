"""GET /v1/announcements/dismissed returns the announcement IDs a user has dismissed.

Dismissal state is only ever written (POST /v1/announcements/{id}/dismiss) and consumed
server-side to filter the pending list, so a client could not read it back. The endpoint
returns the dismissed ids, sorted.

Test isolation: routers.announcements imports cleanly, so the test imports it normally,
patches the import-cheap db helper with monkeypatch.setattr, and calls the handler
directly (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import announcements as ann_mod  # noqa: E402


def test_dismissed_returns_sorted_ids(monkeypatch):
    # The db helper returns an unordered set; the endpoint returns a sorted, JSON-serializable list.
    monkeypatch.setattr(ann_mod, 'get_dismissed_announcement_ids', lambda uid: {'b2', 'a1', 'c3'})
    assert ann_mod.list_dismissed_announcements(uid='u1') == {'dismissed_ids': ['a1', 'b2', 'c3']}


def test_dismissed_empty(monkeypatch):
    monkeypatch.setattr(ann_mod, 'get_dismissed_announcement_ids', lambda uid: set())
    assert ann_mod.list_dismissed_announcements(uid='u1') == {'dismissed_ids': []}


def test_dismissed_scopes_to_caller_uid(monkeypatch):
    seen = {}

    def fake(uid):
        seen['uid'] = uid
        return set()

    monkeypatch.setattr(ann_mod, 'get_dismissed_announcement_ids', fake)
    ann_mod.list_dismissed_announcements(uid='user-42')
    assert seen['uid'] == 'user-42'
