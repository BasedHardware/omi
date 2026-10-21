import asyncio
import os
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap

from utils.external_oauth.contracts import Connector, SecretPurpose
from utils.external_oauth.fake_provider import FakeOAuthProvider
from utils.external_oauth.repository import InMemoryExternalConnectionRepository
from utils.external_oauth.scopes import GRANT_FAMILIES
from utils.external_oauth.service import ExternalOAuthService
from utils.external_oauth.vault import EnvelopeSecretExecutor, InMemoryCiphertextStore


class FakeKeyWrapper:
    key_version = 'fake-kms/versions/1'

    def __init__(self):
        self.kek = os.urandom(32)

    async def wrap(self, dek: bytes) -> bytes:
        return aes_key_wrap(self.kek, dek)

    async def unwrap(self, wrapped_dek: bytes, *, key_version: str) -> bytes:
        return aes_key_unwrap(self.kek, wrapped_dek)


async def _authorize(secret, context):
    if secret.binding.connection_id != context.connection_id or secret.binding.generation != context.generation:
        raise PermissionError('lease binding mismatch')
    if context.purpose not in {SecretPurpose.CALLBACK_EXCHANGE, SecretPurpose.REVOKE}:
        raise PermissionError('purpose denied')


def _service(connector: Connector = Connector.GMAIL):
    repository = InMemoryExternalConnectionRepository()
    store = InMemoryCiphertextStore()
    provider = FakeOAuthProvider(scopes=GRANT_FAMILIES[connector].scopes)
    vault = EnvelopeSecretExecutor(key_wrapper=FakeKeyWrapper(), store=store, authorize=_authorize)
    service = ExternalOAuthService(repository=repository, secrets_executor=vault, providers={connector: provider})
    return service, repository, store, provider


@pytest.mark.asyncio
async def test_start_stores_only_hashed_state_and_encrypted_pkce_nonce():
    service, repository, store, _provider = _service()
    started = await service.start(
        external_owner_id='owner-1', connector=Connector.GMAIL, fixed_return_target_id='desktop'
    )
    raw_state = parse_qs(urlparse(started.authorization_url).query)['state'][0]
    assert raw_state not in repository.attempts
    assert all(raw_state.encode() not in record.ciphertext for record in store.records.values())
    assert 'code_challenge_method=S256' in started.authorization_url


@pytest.mark.asyncio
async def test_callback_activates_exact_scope_grant_and_replay_never_reexchanges():
    service, repository, _store, provider = _service()
    started = await service.start(
        external_owner_id='owner-1', connector=Connector.GMAIL, fixed_return_target_id='desktop'
    )
    state = parse_qs(urlparse(started.authorization_url).query)['state'][0]
    assert await service.callback(raw_state=state, code='authorization-code') == 'connected'
    assert await service.callback(raw_state=state, code='authorization-code') == 'connected'
    assert provider.exchange_count == 1
    assert len(_store.records) == 1  # active credential only; attempt material is destroyed
    connection = await repository.get(external_owner_id='owner-1', connector=Connector.GMAIL)
    assert connection is not None
    assert connection.state.value == 'active'
    assert connection.provider_subject == 'provider-subject-1'


@pytest.mark.asyncio
async def test_concurrent_callbacks_exchange_at_most_once():
    service, _repository, _store, provider = _service()
    started = await service.start(
        external_owner_id='owner-1', connector=Connector.GMAIL, fixed_return_target_id='desktop'
    )
    state = parse_qs(urlparse(started.authorization_url).query)['state'][0]
    results = await asyncio.gather(
        service.callback(raw_state=state, code='authorization-code'),
        service.callback(raw_state=state, code='authorization-code'),
    )
    assert provider.exchange_count == 1
    assert 'connected' in results
    assert set(results) <= {'connected', 'exchange_claimed'}


@pytest.mark.asyncio
async def test_partial_or_extra_scope_grant_never_activates():
    service, repository, _store, provider = _service()
    provider.scopes = frozenset({'openid', 'email'})
    started = await service.start(
        external_owner_id='owner-1', connector=Connector.GMAIL, fixed_return_target_id='desktop'
    )
    state = parse_qs(urlparse(started.authorization_url).query)['state'][0]
    with pytest.raises(Exception, match='provider_scope_set_mismatch'):
        await service.callback(raw_state=state, code='authorization-code')
    assert not _store.records
    assert await service.callback(raw_state=state, code='authorization-code') == 'callback_failed'
    connection = await repository.get(external_owner_id='owner-1', connector=Connector.GMAIL)
    assert connection is not None
    assert connection.state.value == 'pending_consent'


@pytest.mark.asyncio
async def test_calendar_and_gmail_have_independent_cardinality_and_grants():
    repository = InMemoryExternalConnectionRepository()
    store = InMemoryCiphertextStore()
    vault = EnvelopeSecretExecutor(key_wrapper=FakeKeyWrapper(), store=store, authorize=_authorize)
    providers = {connector: FakeOAuthProvider(scopes=GRANT_FAMILIES[connector].scopes) for connector in Connector}
    service = ExternalOAuthService(repository=repository, secrets_executor=vault, providers=providers)
    for connector in Connector:
        await service.start(external_owner_id='owner-1', connector=connector, fixed_return_target_id='desktop')
    assert len(repository.connections) == 2
    assert {connection.grant_family for connection in repository.connections.values()} == {
        'google_calendar_read',
        'google_gmail_read',
    }
