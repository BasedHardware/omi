"""GET /v1/screen-activity/ids returns the user's screen-activity document IDs.

The full list endpoint returns every field for every captured row; there was no cheap way to
fetch just the set of IDs for sync/reconciliation. This reuses the IDs-only
get_screen_activity_ids helper.

Test isolation: routers.focus_sessions imports cleanly, so the test imports it normally, patches
the import-cheap db helper with monkeypatch.setattr, and calls the handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import focus_sessions as fs_mod  # noqa: E402


def test_ids_returns_wrapped_list(monkeypatch):
    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity_ids', lambda uid: ['s1', 's2', 's3'])
    assert fs_mod.list_screen_activity_ids(uid='u1') == {'ids': ['s1', 's2', 's3']}


def test_ids_empty(monkeypatch):
    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity_ids', lambda uid: [])
    assert fs_mod.list_screen_activity_ids(uid='u1') == {'ids': []}


def test_ids_scopes_to_caller(monkeypatch):
    seen = {}

    def fake(uid):
        seen['uid'] = uid
        return []

    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity_ids', fake)
    fs_mod.list_screen_activity_ids(uid='user-7')
    assert seen['uid'] == 'user-7'
