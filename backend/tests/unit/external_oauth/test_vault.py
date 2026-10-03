import os

import pytest
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap

from utils.external_oauth.contracts import SecretBinding, SecretLeaseContext, SecretPurpose
from utils.external_oauth.vault import EnvelopeSecretExecutor, InMemoryCiphertextStore


class FakeKeyWrapper:
    key_version = 'fake-kms/versions/1'

    def __init__(self):
        self.kek = os.urandom(32)

    async def wrap(self, dek: bytes) -> bytes:
        return aes_key_wrap(self.kek, dek)

    async def unwrap(self, wrapped_dek: bytes, *, key_version: str) -> bytes:
        assert key_version == self.key_version
        return aes_key_unwrap(self.kek, wrapped_dek)


def _binding(generation: int = 1) -> SecretBinding:
    return SecretBinding('owner-1', 'connection-1', 'google', 'google_gmail_prod', generation, 1)


def _context(purpose: SecretPurpose, generation: int = 1) -> SecretLeaseContext:
    return SecretLeaseContext('connection-1', generation, 0, 'operation-1', purpose)


async def _authorize(secret, context):
    if secret.binding.connection_id != context.connection_id:
        raise PermissionError('wrong connection')
    if context.purpose not in {SecretPurpose.READ, SecretPurpose.REFRESH, SecretPurpose.REVOKE}:
        raise PermissionError('role cannot use this purpose')


@pytest.mark.asyncio
async def test_ciphertext_store_never_contains_plaintext_and_read_is_purpose_bound():
    store = InMemoryCiphertextStore()
    executor = EnvelopeSecretExecutor(key_wrapper=FakeKeyWrapper(), store=store, authorize=_authorize)
    created = await executor.create(binding=_binding(), plaintext=b'super-secret-refresh-token')
    assert b'super-secret-refresh-token' not in created.ciphertext
    assert b'super-secret-refresh-token' not in created.wrapped_dek

    async def consume(value: memoryview) -> bytes:
        return bytes(value)

    assert (
        await executor.with_secret_lease(
            secret_id=created.secret_id, context=_context(SecretPurpose.READ), operation=consume
        )
        == b'super-secret-refresh-token'
    )


@pytest.mark.asyncio
async def test_stale_generation_cannot_decrypt():
    executor = EnvelopeSecretExecutor(
        key_wrapper=FakeKeyWrapper(), store=InMemoryCiphertextStore(), authorize=_authorize
    )
    created = await executor.create(binding=_binding(), plaintext=b'secret')

    async def consume(value: memoryview) -> None:
        raise AssertionError('operation must not execute')

    with pytest.raises(PermissionError, match='generation'):
        await executor.with_secret_lease(
            secret_id=created.secret_id, context=_context(SecretPurpose.READ, generation=2), operation=consume
        )


@pytest.mark.asyncio
async def test_only_revoke_lease_can_destroy_secret():
    store = InMemoryCiphertextStore()
    executor = EnvelopeSecretExecutor(key_wrapper=FakeKeyWrapper(), store=store, authorize=_authorize)
    created = await executor.create(binding=_binding(), plaintext=b'secret')
    with pytest.raises(PermissionError, match='revocation'):
        await executor.destroy(secret_id=created.secret_id, context=_context(SecretPurpose.READ))
    await executor.destroy(secret_id=created.secret_id, context=_context(SecretPurpose.REVOKE))
    assert created.secret_id not in store.records


@pytest.mark.asyncio
async def test_stale_generation_cannot_destroy_secret_even_if_authorizer_allows_it():
    store = InMemoryCiphertextStore()
    executor = EnvelopeSecretExecutor(key_wrapper=FakeKeyWrapper(), store=store, authorize=_authorize)
    created = await executor.create(binding=_binding(), plaintext=b'secret')
    with pytest.raises(PermissionError, match='generation'):
        await executor.destroy(
            secret_id=created.secret_id,
            context=_context(SecretPurpose.REVOKE, generation=2),
        )
    assert created.secret_id in store.records
