"""Hermetic key lifecycle, race resolution and fail-closed service errors."""

import base64
from copy import deepcopy
import logging
import sys
from unittest.mock import patch

from google.api_core.exceptions import AlreadyExists, FailedPrecondition, ServiceUnavailable
import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.other import space_keys


class CountingKMS(space_keys.FakeKMS):
    def __init__(self):
        self.wraps = 0
        self.unwraps = 0
        self.raw = []

    def encrypt(self, *, request):
        self.wraps += 1
        self.raw.append(request['plaintext'])
        return super().encrypt(request=request)

    def decrypt(self, *, request):
        self.unwraps += 1
        return super().decrypt(request=request)


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    monkeypatch.delenv('OBJECT_LAKE_KEY_CACHE_TTL_SECONDS', raising=False)
    monkeypatch.delenv('OBJECT_LAKE_KMS_FAKE_SECRET', raising=False)
    store, kms = StrictFirestore(), CountingKMS()
    monkeypatch.setattr(space_keys, '_kms', lambda: kms)
    space_keys.clear_space_key_cache()
    yield store, kms
    space_keys.clear_space_key_cache()


def test_create_once_and_required_document_shape(keys):
    store, kms = keys
    first = space_keys.get_or_create_space_key('s', firestore_client=store)
    assert space_keys.get_or_create_space_key('s', firestore_client=store) == first
    assert kms.wraps == 1
    data = store.rows[('space_keys', 's')]
    assert set(data) == {'space_id', 'algo', 'kms_key', 'active_version', 'versions', 'created_at', 'updated_at'}
    assert data['space_id'] == 's' and data['algo'] == 'AES-256-GCM'
    assert kms.raw[0] not in repr(data).encode()
    assert base64.b64decode(first.versions[0].wrapped_b64).startswith(b'FAKEKMS1')


def test_create_race_discards_candidate_and_reads_winner(keys):
    store, kms = keys
    winner_store = StrictFirestore()
    winner = space_keys.get_or_create_space_key('s', firestore_client=winner_store)
    winner_doc = deepcopy(winner_store.rows[('space_keys', 's')])

    def raced_create(ref, data):
        store.rows[ref.path] = winner_doc
        raise AlreadyExists('concurrent create')

    with patch.object(StrictFirestoreDocument, 'create', raced_create):
        assert space_keys.get_or_create_space_key('s', firestore_client=store) == winner
    assert kms.wraps == 2
    assert space_keys.unwrap_space_dek('s', 1, firestore_client=store) == kms.raw[0]
    assert kms.raw[0] != kms.raw[1]


def test_cache_and_clear(keys):
    store, kms = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    assert space_keys.unwrap_space_dek('s', 1, firestore_client=store) == kms.raw[0]
    assert space_keys.unwrap_space_dek('s', 1, firestore_client=store) == kms.raw[0]
    assert kms.unwraps == 1
    space_keys.clear_space_key_cache()
    space_keys.unwrap_space_dek('s', 1, firestore_client=store)
    assert kms.unwraps == 2


def test_rotation_retains_old_versions_and_transaction_order(keys):
    store, kms = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    rotated = space_keys.rotate_space_key('s', firestore_client=store)
    assert rotated.active_version == 2
    assert [v.state for v in rotated.versions] == ['retired', 'active']
    assert space_keys.unwrap_space_dek('s', 1, firestore_client=store) == kms.raw[0]
    assert space_keys.unwrap_space_dek('s', 2, firestore_client=store) == kms.raw[1]
    assert len(store.transactions[0].updates) == 1
    assert store.rows[('space_keys', 's')]['created_at'] == rotated.versions[0].wrapped_at


def test_destroy_evicts_all_versions_and_is_idempotent(keys):
    store, _ = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    space_keys.rotate_space_key('s', firestore_client=store)
    for version in (1, 2):
        space_keys.unwrap_space_dek('s', version, firestore_client=store)
    assert space_keys.destroy_space_keys('s', firestore_client=store) == 2
    assert not space_keys._cache
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.get_space_keys('s', firestore_client=store)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.unwrap_space_dek('s', 1, firestore_client=store)
    assert space_keys.destroy_space_keys('s', firestore_client=store) == 0


def test_external_destroy_is_observed_even_with_cached_key(keys):
    store, _ = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    space_keys.unwrap_space_dek('s', 1, firestore_client=store)
    store.rows.clear()  # Another process completed the final destroy.
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.unwrap_space_dek('s', 1, firestore_client=store)


def test_missing_version_is_destroyed(keys):
    store, _ = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.unwrap_space_dek('s', 2, firestore_client=store)
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.rotate_space_key('absent', firestore_client=store)


def test_transient_kms_and_firestore_failure_is_sanitized(keys, caplog):
    store, kms = keys
    secret = 'sensitive-key-material'
    with patch.object(kms, 'encrypt', side_effect=ServiceUnavailable(secret)):
        with pytest.raises(space_keys.SpaceKeyUnavailable) as error:
            space_keys.get_or_create_space_key('s', firestore_client=store)
        assert secret not in str(error.value)
    space_keys.get_or_create_space_key('s', firestore_client=store)
    with patch.object(kms, 'decrypt', side_effect=ServiceUnavailable(secret)):
        with pytest.raises(space_keys.SpaceKeyUnavailable) as error:
            space_keys.unwrap_space_dek('s', 1, firestore_client=store)
        assert secret not in str(error.value)
    with patch.object(store, 'collection', side_effect=ServiceUnavailable(secret)):
        with pytest.raises(space_keys.SpaceKeyUnavailable):
            space_keys.get_space_keys('s', firestore_client=store)
    assert secret not in caplog.text


@pytest.mark.parametrize('state', ['DESTROYED', 'DISABLED'])
def test_disabled_or_destroyed_kms_version_is_destroyed(keys, state):
    store, kms = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    with patch.object(kms, 'decrypt', side_effect=FailedPrecondition(f'CryptoKeyVersion is {state}')):
        with pytest.raises(space_keys.SpaceKeyDestroyed):
            space_keys.unwrap_space_dek('s', 1, firestore_client=store)


def test_fake_kms_does_not_import_real_sdk(monkeypatch, caplog):
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    monkeypatch.setattr(space_keys, '_did_warn_fake', False)
    caplog.set_level(logging.WARNING)
    fake = space_keys._kms()
    raw = b'r' * 32
    wrapped = fake.encrypt(request={'plaintext': raw}).ciphertext
    assert wrapped.startswith(b'FAKEKMS1')
    assert fake.decrypt(request={'ciphertext': wrapped}).plaintext == raw
    space_keys._kms()
    assert caplog.text.count('using offline FakeKMS') == 1
    assert 'google.cloud.kms_v1' not in sys.modules
    assert raw.decode() not in caplog.text and base64.b64encode(wrapped).decode() not in caplog.text
    with pytest.raises(ValueError):
        fake.decrypt(request={'ciphertext': b'not-a-fake-envelope'})


def test_keys_never_logged(keys, caplog):
    store, kms = keys
    caplog.set_level(logging.DEBUG)
    key = space_keys.get_or_create_space_key('s', firestore_client=store)
    space_keys.unwrap_space_dek('s', 1, firestore_client=store)
    space_keys.destroy_space_keys('s', firestore_client=store)
    assert kms.raw[0].hex() not in caplog.text
    assert repr(kms.raw[0]) not in caplog.text
    assert key.versions[0].wrapped_b64 not in caplog.text


def test_destroy_requires_verified_absence(keys):
    store, _ = keys
    space_keys.get_or_create_space_key('s', firestore_client=store)
    original = StrictFirestoreDocument.get
    saved = deepcopy(store.rows)

    def resurrect(ref, transaction=None):
        if transaction is None and (store.rows.get(ref.path) or {}).get('state') == 'destroyed':
            store.rows.update(saved)
        return original(ref, transaction=transaction)

    with patch.object(StrictFirestoreDocument, 'get', resurrect):
        with pytest.raises(space_keys.SpaceKeyUnavailable, match='not verified'):
            space_keys.destroy_space_keys('s', firestore_client=store)


def test_zero_ttl_disables_key_cache(keys, monkeypatch):
    store, kms = keys
    monkeypatch.setenv('OBJECT_LAKE_KEY_CACHE_TTL_SECONDS', '0')
    space_keys.get_or_create_space_key('s', firestore_client=store)
    for _ in range(2):
        space_keys.unwrap_space_dek('s', 1, firestore_client=store)
    assert kms.unwraps == 2
