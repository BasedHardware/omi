"""Firestore proof that concurrent checkpoints cannot overwrite each other."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_release import advance_held_partial_cursor, load_held_partial_cursor
from database.batch_pipeline_store import FirestoreStore


def test_concurrent_advance_and_wrap_have_one_winner():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('local Firestore emulator required')
    assert host.split(':')[0] in {'127.0.0.1', 'localhost'}
    project = os.environ.get('GCLOUD_PROJECT', 'demo-held-cursor')
    assert project.startswith('demo-')
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    store = ProjectionStore(FirestoreStore(f'batch_pipeline_test_{uuid4().hex}', firestore_client=client))
    try:
        assert advance_held_partial_cursor(store, {}, 'a', 1) is not None
        ready = Barrier(2, timeout=5)

        def publish(after_id):
            baseline = load_held_partial_cursor(store)
            ready.wait()
            return advance_held_partial_cursor(store, baseline, after_id, 2)

        with ThreadPoolExecutor(max_workers=2) as pool:
            writes = list(pool.map(publish, ('b', None)))
        committed = [row for row in writes if row is not None]
        assert len(committed) == 1
        assert load_held_partial_cursor(store) == committed[0]
    finally:
        client.close()
