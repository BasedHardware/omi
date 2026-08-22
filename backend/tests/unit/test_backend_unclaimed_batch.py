"""Regression coverage for unclaimed backend fixes landed on this branch."""

from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_fake_gcs_selection_uses_runtime_safe_module():
    source = (BACKEND / 'utils' / 'other' / 'storage.py').read_text()
    assert 'from utils.other.fake_gcs import FakeStorageClient, setup_fake_storage' in source
    assert 'OMI_USE_FAKE_GCS' in source
    assert (BACKEND / 'utils' / 'other' / 'fake_gcs.py').is_file()


def test_enqueue_dev_webhook_dlq_is_defined():
    source = (BACKEND / 'database' / 'webhook_health.py').read_text()
    assert 'def enqueue_dev_webhook_dlq(' in source


def test_short_conversation_hard_discard_constant():
    source = (BACKEND / 'utils' / 'conversations' / 'process_conversation.py').read_text()
    assert 'SHORT_CONVERSATION_HARD_DISCARD_SECONDS = 30.0' in source


def test_crisp_unread_route_removed():
    source = (BACKEND / 'routers' / 'desktop_screen_crisp.py').read_text()
    assert '/v1/crisp/unread' not in source
    assert '/v1/screen-activity/sync' in source
