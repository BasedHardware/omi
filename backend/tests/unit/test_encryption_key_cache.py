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
