"""Regression + microbench: derive_key must reuse HKDF results per uid."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import utils.encryption as encryption


def test_derive_key_caches_per_uid(monkeypatch):
    encryption.clear_derived_key_cache()
    derive_calls = {'count': 0}
    real_derive = HKDF.derive

    def counting_derive(self, key_material):
        derive_calls['count'] += 1
        return real_derive(self, key_material)

    monkeypatch.setattr(HKDF, 'derive', counting_derive)

    first = encryption.derive_key('uid-a')
    second = encryption.derive_key('uid-a')
    other = encryption.derive_key('uid-b')

    assert first == second
    assert first != other
    assert derive_calls['count'] == 2


def test_encrypt_decrypt_roundtrip_uses_cached_key():
    encryption.clear_derived_key_cache()
    plaintext = 'hello encryption cache'
    ciphertext = encryption.encrypt(plaintext, 'uid-roundtrip')
    assert encryption.decrypt(ciphertext, 'uid-roundtrip') == plaintext


def test_audio_chunk_roundtrip_uses_cached_key():
    encryption.clear_derived_key_cache()
    payload = b'\x00\x01\x02\x03' * 256
    encrypted = encryption.encrypt_audio_chunk(payload, 'uid-audio')
    decrypted, consumed = encryption.decrypt_audio_chunk(encrypted, 'uid-audio')
    assert decrypted == payload
    assert consumed == len(encrypted)


@pytest.mark.slow
def test_derive_key_cache_speedup_is_measurable():
    encryption.clear_derived_key_cache()
    uid = 'uid-bench'
    cold_start = time.perf_counter()
    for _ in range(200):
        encryption.clear_derived_key_cache()
        encryption.derive_key(uid)
    cold_elapsed = time.perf_counter() - cold_start

    encryption.clear_derived_key_cache()
    encryption.derive_key(uid)
    warm_start = time.perf_counter()
    for _ in range(200):
        encryption.derive_key(uid)
    warm_elapsed = time.perf_counter() - warm_start

    assert warm_elapsed < cold_elapsed * 0.25, (
        f'cached derive_key should be much faster than cold HKDF; ' f'cold={cold_elapsed:.4f}s warm={warm_elapsed:.4f}s'
    )


TEST_SECRET = b'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv'
# Made by encrypt('pinned user data', 'uid-pinned') before key purposes existed, under TEST_SECRET.
PINNED_CIPHERTEXT = 'GTDED9Tizrlc278IuDE1AEVDnN8Jld1Tf2oV4HY1wKesr0J55ntkW6f9Vqk='
PINNED_KEY_HEX = '3a5a331399edcb6e28f9ccda3cc59f5b79ab4bbaf82ddcc04c95f65ec3485a25'


@pytest.fixture
def pinned_secret(monkeypatch):
    monkeypatch.setattr(encryption, 'ENCRYPTION_SECRET', TEST_SECRET)
    encryption.clear_derived_key_cache()
    yield
    encryption.clear_derived_key_cache()


def test_default_purpose_is_the_original_user_data_key(pinned_secret):
    # Stored user data was encrypted before purposes existed; the default must still open it.
    assert encryption.derive_key('uid-pinned').hex() == PINNED_KEY_HEX
    assert encryption.derive_key('uid-pinned', purpose=encryption.USER_DATA_KEY_PURPOSE).hex() == PINNED_KEY_HEX
    assert encryption.decrypt(PINNED_CIPHERTEXT, 'uid-pinned') == 'pinned user data'


def test_each_purpose_derives_its_own_key_and_cache_entry(pinned_secret, monkeypatch):
    derive_calls = {'count': 0}
    real_derive = HKDF.derive

    def counting_derive(self, key_material):
        derive_calls['count'] += 1
        return real_derive(self, key_material)

    monkeypatch.setattr(HKDF, 'derive', counting_derive)
    user_data = encryption.derive_key('uid-a')
    signing = encryption.derive_key('uid-a', purpose=b'webhook-signing-secret')
    assert user_data != signing
    # A cached user-data key must never be handed out for another purpose, or the reverse.
    assert encryption.derive_key('uid-a') == user_data
    assert encryption.derive_key('uid-a', purpose=b'webhook-signing-secret') == signing
    assert derive_calls['count'] == 2


def test_a_ciphertext_only_decrypts_under_the_purpose_it_was_made_for(pinned_secret):
    signing = b'webhook-signing-secret'
    sealed = encryption.encrypt('whsec_value', 'uid-a', purpose=signing)
    assert encryption.decrypt(sealed, 'uid-a', purpose=signing) == 'whsec_value'
    # decrypt fails open by returning its input; it must not return the plaintext.
    assert encryption.decrypt(sealed, 'uid-a') == sealed
    user_data = encryption.encrypt('whsec_value', 'uid-a')
    assert encryption.decrypt(user_data, 'uid-a', purpose=signing) == user_data
