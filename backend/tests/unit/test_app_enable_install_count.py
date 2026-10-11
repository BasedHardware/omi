import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import asyncio
from unittest.mock import MagicMock

from starlette.requests import Request

import database.redis_db as redis_db
import routers.apps as apps


def _fake_request() -> Request:
    """Minimal ASGI-scope Request double for request-taking endpoints.

    ``record_product_event`` only reads ``request.headers`` (fail-open on any
    other shape), so an empty-header Request is a sufficient double here —
    consistent with tests/unit/test_product_metrics.py.
    """
    return Request({'type': 'http', 'headers': []})


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


def _install(monkeypatch):
    enabled = set()
    counted = []
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, uid: _public_app())

    def sadd(uid, app_id):
        added = (uid, app_id) not in enabled
        enabled.add((uid, app_id))
        return added

    monkeypatch.setattr(apps, 'enable_app', sadd)
    monkeypatch.setattr(apps, 'is_tester', lambda uid: False)
    monkeypatch.setattr(apps, 'increase_app_installs_count', counted.append)
    return enabled, counted


def test_enabling_an_installed_app_again_counts_one_install(monkeypatch):
    enabled, counted = _install(monkeypatch)

    asyncio.run(apps.enable_app_endpoint('app-1', _fake_request(), uid='user-1'))
    asyncio.run(apps.enable_app_endpoint('app-1', _fake_request(), uid='user-1'))

    assert enabled == {('user-1', 'app-1')}
    assert counted == ['app-1']


def test_each_new_user_still_counts_an_install(monkeypatch):
    _enabled, counted = _install(monkeypatch)

    asyncio.run(apps.enable_app_endpoint('app-1', _fake_request(), uid='user-1'))
    asyncio.run(apps.enable_app_endpoint('app-1', _fake_request(), uid='user-2'))

    assert counted == ['app-1', 'app-1']


def test_enable_app_reports_whether_the_app_was_newly_enabled(monkeypatch):
    fake = MagicMock()
    fake.sadd.side_effect = [1, 0]
    monkeypatch.setattr(redis_db, 'r', fake)

    assert redis_db.enable_app('user-1', 'app-1') is True
    assert redis_db.enable_app('user-1', 'app-1') is False
