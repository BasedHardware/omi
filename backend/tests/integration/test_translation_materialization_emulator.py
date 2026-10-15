"""Loopback Firestore proof for concurrent translation materialization.

FIRESTORE_EMULATOR_HOST=127.0.0.1:10288 backend/.venv/bin/python -m pytest -q \
  backend/tests/integration/test_translation_materialization_emulator.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import conversations


@pytest.fixture
def record(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('A loopback Firestore emulator is required')
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'true')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'a' * 32)
    client = firestore.Client(project='demo-translation', credentials=AnonymousCredentials())
    uid, conversation_id = uuid4().hex, uuid4().hex
    doc = (
        client.collection('users')
        .document(uid)
        .collection(conversations.conversations_collection)
        .document(conversation_id)
    )
    doc.set(
        conversations.encode_conversation_for_write(
            uid,
            {
                'id': conversation_id,
                'data_protection_level': 'standard',
                'transcript_segments': [{'id': 's', 'text': 'Yến nói với bác năm 2025.', 'translations': []}],
                'client_processing_projection': {'keep': True},
            },
            'standard',
        )
    )
    yield client, doc, uid, conversation_id
    client.close()


def test_concurrent_targets_and_policy_priority_preserve_raw_and_projection(record):
    client, doc, uid, conversation_id = record
    source = 'Yến nói với bác năm 2025.'
    barrier = Barrier(3)

    def write(target, value, policy):
        barrier.wait()
        return conversations.materialize_translation(
            uid,
            conversation_id,
            's',
            source,
            target,
            value,
            policy_version=policy,
            firestore_client=client,
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(write, 'en', 'Yến spoke with the elder in 2025.', 'viewed_v1'),
            pool.submit(write, 'en', 'bad legacy result', 'legacy'),
            pool.submit(write, 'fr', 'Yến a parlé avec son aîné en 2025.', 'legacy'),
        ]
        for future in futures:
            future.result(timeout=10)

    saved = conversations.prepare_conversation_for_read(doc.get().to_dict(), uid)
    segment = saved['transcript_segments'][0]
    assert segment['text'] == source
    assert saved['client_processing_projection'] == {'keep': True}
    assert {item['lang']: item['text'] for item in segment['translations']} == {
        'en': 'Yến spoke with the elder in 2025.',
        'fr': 'Yến a parlé avec son aîné en 2025.',
    }
    assert conversations.translation_materialization_is_current(uid, saved, segment, 'en', 'viewed_v1')
