"""GET /v1/action-items/ids returns the user's action-item IDs (lightweight reconciliation).

The full list endpoint returns every field for every task; there was no cheap way to fetch
just the set of IDs a user has. This reuses the IDs-only get_action_item_ids helper.

Test isolation: routers.action_items imports cleanly, so the test imports it normally,
patches the import-cheap db helper with monkeypatch.setattr, and calls the handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import action_items as ai_mod  # noqa: E402


def test_list_action_item_ids_returns_ids(monkeypatch):
    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_item_ids', lambda uid: ['a1', 'a2', 'a3'])
    assert ai_mod.list_action_item_ids(uid='u1') == {'ids': ['a1', 'a2', 'a3']}


def test_list_action_item_ids_empty(monkeypatch):
    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_item_ids', lambda uid: [])
    assert ai_mod.list_action_item_ids(uid='u1') == {'ids': []}


def test_list_action_item_ids_scopes_to_caller(monkeypatch):
    seen = {}

    def fake(uid):
        seen['uid'] = uid
        return []

    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_item_ids', fake)
    ai_mod.list_action_item_ids(uid='user-9')
    assert seen['uid'] == 'user-9'
