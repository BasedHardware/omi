"""The in-flight ledger is CAS-serialized and readable; loopback emulator only."""

from __future__ import annotations

import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import pipeline_ledger

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    return firestore.Client(project=f'pipeline-ledger-{uuid4().hex[:12]}', credentials=AnonymousCredentials())


def _ledger(client, uid, capture_id):
    snapshot = client.collection('users').document(uid).collection('pipeline_ledger').document(capture_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def test_stale_advance_cannot_overwrite_a_newer_stage(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-stale', 'c-stale'

    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.NOTED, now=200, firestore_client=client)
    assert not pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=300, firestore_client=client)

    doc = _ledger(client, uid, capture_id)
    assert doc['stage'] == pipeline_ledger.NOTED
    assert doc['attempt'] == 2


def test_disabled_ledger_writes_nothing(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    uid, capture_id = 'u-off', 'c-off'

    assert not pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert _ledger(client, uid, capture_id) is None


def test_census_window_reads_the_committed_rows(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-window', 'c-window'
    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)

    rows = pipeline_ledger.census_window(0, 10**12, uid=uid, firestore_client=client)
    assert len(rows) == 1
    assert rows[0]['stage'] == pipeline_ledger.SEALED
    assert rows[0]['owner_key'] == pipeline_ledger.owner_key(uid)
    assert 'capture_id' not in rows[0]


def test_census_window_never_reads_another_owner(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    assert pipeline_ledger.advance('u-a', 'c-a', pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert pipeline_ledger.advance('u-b', 'c-b', pipeline_ledger.SEALED, now=100, firestore_client=client)

    rows = pipeline_ledger.census_window(0, 10**12, uid='u-a', firestore_client=client)
    assert [row['owner_key'] for row in rows] == [pipeline_ledger.owner_key('u-a')]
