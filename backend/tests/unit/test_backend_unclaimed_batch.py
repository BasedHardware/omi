"""Regression coverage for unclaimed backend fixes landed on this branch."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_fake_gcs_client_used_when_omi_use_fake_gcs(monkeypatch):
    monkeypatch.setenv('OMI_USE_FAKE_GCS', '1')
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('PROVIDER_MODE', raising=False)

    import utils.other.storage as storage_mod

    storage_mod.storage_client = None
    client = storage_mod._get_storage_client()
    from utils.other.fake_gcs import FakeStorageClient

    assert isinstance(client, FakeStorageClient)
    bucket = client.bucket('speech-profiles')
    blob = bucket.blob('uid/profile.wav')
    blob.upload_from_string(b'wav-bytes')
    assert blob.exists()
    storage_mod.storage_client = None


def test_enqueue_dev_webhook_dlq_stores_entry(monkeypatch):
    from database import webhook_health

    pushed = []

    class FakeRedis:
        def lpush(self, key, value):
            pushed.append((key, value))
            return 1

        def ltrim(self, *args):
            return True

        def expire(self, *args):
            return True

    monkeypatch.setattr(webhook_health, 'r', FakeRedis())
    webhook_health.enqueue_dev_webhook_dlq(
        webhook_name='memory_created_webhook',
        webhook_url='https://example.test/hook',
        status_code=500,
        error='HTTP 500',
        idempotency_key='evt-1',
        uid='uid-1',
    )
    assert pushed
    assert pushed[0][0] == 'dev_webhook_dlq:uid-1'
    assert 'memory_created_webhook' in pushed[0][1]


def test_short_conversation_hard_discard_constant():
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / 'utils' / 'conversations' / 'process_conversation.py'
    assert 'SHORT_CONVERSATION_HARD_DISCARD_SECONDS = 30.0' in source.read_text()


def test_crisp_unread_route_removed():
    from routers import desktop_screen_crisp

    paths = {getattr(route, 'path', None) for route in desktop_screen_crisp.router.routes}
    assert '/v1/crisp/unread' not in paths
    assert '/v1/screen-activity/sync' in paths
