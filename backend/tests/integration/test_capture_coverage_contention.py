"""Real committed-ledger contention; run only against a loopback emulator."""

import concurrent.futures
import os
from uuid import uuid4

import pytest


@pytest.mark.integration
def test_racing_writers_preserve_both_frame_contributions(monkeypatch):
    endpoint = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not endpoint.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from database import capture_coverage as store
    from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
    from utils.capture import coverage

    client = firestore.Client(project='demo-capture-coverage', credentials=AnonymousCredentials())
    monkeypatch.setattr(store, '_client', lambda: client)
    monkeypatch.setenv(coverage.FLAG, 'serve')
    subject = str(uuid4())
    key = CaptureKey(capture_root=str(uuid4()))

    def write(index):
        coverage.record(
            subject,
            key,
            CoverageRecord(
                conversation_id=f'contribution-{index % 2}',
                origin='live' if index % 2 else 'sync',
                ranges=[FrameRange(start=index * 10, end=(index + 1) * 10)],
            ),
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(write, range(8)))
        result = coverage.query(subject, key, [FrameRange(start=0, end=80)])
        assert result.uncovered == []
        assert result.covered == [FrameRange(start=0, end=80)]
        assert len(store.read(subject, key)) == 2
    finally:
        store.reference(client, subject, key).delete()
        client.close()
