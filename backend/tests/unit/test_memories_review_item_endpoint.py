"""GET /v3/memories/review-queue/{review_id} fetches a single memory review conflict.

The list endpoint only returns conflicts with status 'pending', so once a conflict is
resolved it can no longer be retrieved. This endpoint fetches any of the user's review
conflicts by id (404 if missing), reusing the existing get_review_conflict helper.

Test isolation: routers.memories imports cleanly, so the test imports it normally, patches
the import-cheap review_queue helper with monkeypatch.setattr, and calls the handler
directly (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import memories as mem_mod  # noqa: E402


def test_get_review_item_returns_conflict(monkeypatch):
    conflict = {'review_id': 'r1', 'status': 'resolved', 'conflict': {}}
    monkeypatch.setattr(mem_mod.review_queue, 'get_review_conflict', lambda uid, review_id: conflict)
    assert mem_mod.get_memory_review_item(review_id='r1', uid='u1') == conflict


def test_get_review_item_404_when_missing(monkeypatch):
    monkeypatch.setattr(mem_mod.review_queue, 'get_review_conflict', lambda uid, review_id: None)
    with pytest.raises(HTTPException) as ei:
        mem_mod.get_memory_review_item(review_id='nope', uid='u1')
    assert ei.value.status_code == 404


def test_get_review_item_scopes_to_caller_uid(monkeypatch):
    seen = {}

    def fake(uid, review_id):
        seen['args'] = (uid, review_id)
        return {'review_id': review_id}

    monkeypatch.setattr(mem_mod.review_queue, 'get_review_conflict', fake)
    mem_mod.get_memory_review_item(review_id='r9', uid='user-7')
    assert seen['args'] == ('user-7', 'r9')
