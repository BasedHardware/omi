"""Real Firestore query proof for the action-item legacy completion probe.

Run from the repository root:

    firebase emulators:exec --only firestore --project demo-action-items-read \
      "PYTHONPATH=backend backend/.venv/bin/pytest -q \
      backend/tests/integration/test_action_items_legacy_probe_emulator.py"
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import pytest

PROJECT_ID = os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'demo-action-items-read')
os.environ.setdefault('GCLOUD_PROJECT', PROJECT_ID)
os.environ.setdefault('FIREBASE_PROJECT_ID', PROJECT_ID)

from database import action_items  # noqa: E402
from database._client import get_firestore_client  # noqa: E402


def _assert_emulator_only() -> None:
    host = (os.environ.get('FIRESTORE_EMULATOR_HOST') or '').strip()
    hostname = urlparse(f'//{host}').hostname
    if hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('FIRESTORE_EMULATOR_HOST must point to a loopback Firestore emulator')


def _seed(uid: str, rows: list[tuple[str, dict[str, Any]]]) -> None:
    client = get_firestore_client()
    batch = client.batch()
    collection = client.collection('users').document(uid).collection('action_items')
    for item_id, payload in rows:
        batch.set(collection.document(item_id), payload)
    batch.commit()


def test_canonical_probe_skips_scan_without_hiding_legacy_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _assert_emulator_only()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    canonical_uid = f'action-items-canonical-{uuid.uuid4().hex}'
    canonical_rows = [
        (
            f'completed-{index:03d}',
            {'description': f'completed {index}', 'completed': True, 'status': 'completed', 'created_at': now},
        )
        for index in range(300)
    ] + [
        (
            f'active-{index:03d}',
            {'description': f'active {index}', 'completed': False, 'status': 'active', 'created_at': now},
        )
        for index in range(5)
    ]
    _seed(canonical_uid, canonical_rows)

    reads: list[int] = []
    monkeypatch.setattr(action_items, 'record_firestore_read', lambda _family, _mode, count: reads.append(count))
    canonical_page = action_items.get_action_items(canonical_uid, limit=10)

    assert [row['id'] for row in canonical_page[:5]] == [f'active-{index:03d}' for index in range(5)]
    assert reads == [44]

    legacy_uid = f'action-items-legacy-{uuid.uuid4().hex}'
    _seed(
        legacy_uid,
        [
            ('active', {'description': 'active', 'completed': False, 'status': 'active', 'created_at': now}),
            ('missing', {'description': 'missing', 'status': 'active', 'created_at': now}),
            ('null', {'description': 'null', 'completed': None, 'status': 'active', 'created_at': now}),
            ('done', {'description': 'done', 'completed': True, 'status': 'completed', 'created_at': now}),
        ],
    )
    reads.clear()
    legacy_page = action_items.get_action_items(legacy_uid, limit=4)

    assert {row['id'] for row in legacy_page} == {'active', 'missing', 'null', 'done'}
    assert all(isinstance(row['completed'], bool) for row in legacy_page)
    assert reads == [8]
