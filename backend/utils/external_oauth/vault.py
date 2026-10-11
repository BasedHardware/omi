"""Application-level envelope-encryption custody with purpose-bound leases.

The executor intentionally has no default KMS or persistence implementation.
Production construction must inject reviewed adapters; missing adapters cannot
fall back to plaintext or a local key.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict
from typing import Awaitable, Callable, Dict, Protocol, TypeVar

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.external_oauth.contracts import (
    EncryptedSecretVersion,
    SecretBinding,
    SecretLeaseContext,
    SecretOperation,
    SecretPurpose,
)


class KeyWrapper(Protocol):
    @property
    def key_version(self) -> str: ...

    async def wrap(self, dek: bytes) -> bytes: ...

    async def unwrap(self, wrapped_dek: bytes, *, key_version: str) -> bytes: ...


class SecretVersionStore(Protocol):
    async def put(self, secret: EncryptedSecretVersion) -> None: ...

    async def get(self, secret_id: str) -> EncryptedSecretVersion: ...

    async def destroy(self, secret_id: str) -> None: ...


LeaseAuthorizer = Callable[[EncryptedSecretVersion, SecretLeaseContext], Awaitable[None]]
T = TypeVar('T')


def binding_aad(binding: SecretBinding) -> bytes:
    # Stable external_owner_id is deliberately included; mutable Omi UID/email is not.
    payload = json.dumps(asdict(binding), sort_keys=True, separators=(',', ':')).encode()
    return b'omi.external-oauth.secret.v1\x00' + payload


class EnvelopeSecretExecutor:
    def __init__(self, *, key_wrapper: KeyWrapper, store: SecretVersionStore, authorize: LeaseAuthorizer):
        self._key_wrapper = key_wrapper
        self._store = store
        self._authorize = authorize

    async def create(self, *, binding: SecretBinding, plaintext: bytes) -> EncryptedSecretVersion:
        if not plaintext:
            raise ValueError('refusing to persist an empty external secret')
        dek = bytearray(os.urandom(32))
        nonce = os.urandom(12)
        aad = binding_aad(binding)
        try:
            ciphertext = AESGCM(bytes(dek)).encrypt(nonce, plaintext, aad)
            wrapped_dek = await self._key_wrapper.wrap(bytes(dek))
        finally:
            dek[:] = b'\x00' * len(dek)
        secret = EncryptedSecretVersion(
            secret_id=str(uuid.uuid4()),
            binding=binding,
            ciphertext=ciphertext,
            nonce=nonce,
            wrapped_dek=wrapped_dek,
            kms_key_version=self._key_wrapper.key_version,
            aad_digest=hashlib.sha256(aad).hexdigest(),
        )
        await self._store.put(secret)
        return secret

    async def with_secret_lease(
        self, *, secret_id: str, context: SecretLeaseContext, operation: SecretOperation[T]
    ) -> T:
        secret = await self._store.get(secret_id)
        if secret.binding.connection_id != context.connection_id:
            raise PermissionError('external secret connection is fenced')
        if secret.binding.generation != context.generation:
            raise PermissionError('external secret generation is fenced')
        await self._authorize(secret, context)
        if secret.status != 'active':
            raise PermissionError('external secret generation is fenced')
        if context.purpose == SecretPurpose.REWRAP:
            raise PermissionError('rewrap does not expose plaintext to an operation')
        aad = binding_aad(secret.binding)
        if hashlib.sha256(aad).hexdigest() != secret.aad_digest:
            raise PermissionError('external secret AAD mismatch')
        dek = bytearray(await self._key_wrapper.unwrap(secret.wrapped_dek, key_version=secret.kms_key_version))
        plaintext = bytearray()
        try:
            plaintext.extend(AESGCM(bytes(dek)).decrypt(secret.nonce, secret.ciphertext, aad))
            return await operation(memoryview(plaintext))
        finally:
            plaintext[:] = b'\x00' * len(plaintext)
            dek[:] = b'\x00' * len(dek)

    async def destroy(self, *, secret_id: str, context: SecretLeaseContext) -> None:
        secret = await self._store.get(secret_id)
        if secret.binding.connection_id != context.connection_id:
            raise PermissionError('external secret connection is fenced')
        if secret.binding.generation != context.generation:
            raise PermissionError('external secret generation is fenced')
        await self._authorize(secret, context)
        if context.purpose != SecretPurpose.REVOKE:
            raise PermissionError('only a revocation lease may destroy a credential')
        await self._store.destroy(secret_id)


class InMemoryCiphertextStore:
    """Ciphertext-only fake used by conformance tests; never a runtime default."""

    def __init__(self):
        self.records: Dict[str, EncryptedSecretVersion] = {}

    async def put(self, secret: EncryptedSecretVersion) -> None:
        self.records[secret.secret_id] = secret

    async def get(self, secret_id: str) -> EncryptedSecretVersion:
        return self.records[secret_id]

    async def destroy(self, secret_id: str) -> None:
        del self.records[secret_id]
