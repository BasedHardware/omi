import uuid

import pytest

from database import speaker_evidence as storage
from models.speaker_evidence import SpeakerEvidence
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def test_encrypted_compressed_roundtrip_and_deleted_conversation():
    account = str(uuid.uuid4())
    parent = ('users', account, 'conversations', 'c')
    child = (*parent, 'speaker_evidence', 'current')
    client = StrictFirestore({parent: {'status': 'completed'}})
    record = SpeakerEvidence(status='unavailable', policy_version='test', abstentions=['no_audio'])
    storage.store_evidence(account, 'c', record, firestore_client=client)
    assert 'no_audio' not in client.rows[child]['payload']
    assert client.rows[parent] == {'status': 'completed'}
    assert storage.get_evidence(account, 'c', firestore_client=client) == record
    client.rows[parent]['deleted'] = True
    assert storage.get_evidence(account, 'c', firestore_client=client) is None
    with pytest.raises(ValueError, match='parent unavailable'):
        storage.store_evidence(account, 'c', record, firestore_client=client)


def test_size_budget_rejects_before_firestore_write(monkeypatch):
    monkeypatch.setattr(storage, 'MAX_DECODED_BYTES', 1)
    client = StrictFirestore()
    record = SpeakerEvidence(status='unavailable', policy_version='test')
    with pytest.raises(ValueError, match='size budget'):
        storage.store_evidence(str(uuid.uuid4()), 'c', record, firestore_client=client)
    assert not client.rows


def test_stale_source_revision_cannot_publish():
    from datetime import datetime, timezone

    account = str(uuid.uuid4())
    parent = ('users', account, 'conversations', 'c')
    client = StrictFirestore({parent: {'status': 'completed'}})
    record = SpeakerEvidence(status='unavailable', policy_version='test')
    with pytest.raises(ValueError, match='source revision changed'):
        storage.store_evidence(
            account, 'c', record, expected_updated_at=datetime.now(timezone.utc), firestore_client=client
        )
    assert (*parent, 'speaker_evidence', 'current') not in client.rows


def test_malformed_record_uses_safe_shared_read_boundary(caplog):
    import base64
    import json
    import zlib
    from database.read_boundary import MalformedDocError

    account = str(uuid.uuid4())
    parent = ('users', account, 'conversations', 'c')
    raw = json.dumps({'status': 'invalid', 'policy_version': 'private-calibration-marker'})
    encoded = storage.encrypt(base64.b64encode(zlib.compress(raw.encode())).decode(), account)
    client = StrictFirestore({parent: {}, (*parent, 'speaker_evidence', 'current'): {'version': 1, 'payload': encoded}})
    with pytest.raises(MalformedDocError) as error:
        storage.get_evidence(account, 'c', firestore_client=client)
    assert 'private-calibration-marker' not in caplog.text
    assert account not in caplog.text and account not in str(error.value)
