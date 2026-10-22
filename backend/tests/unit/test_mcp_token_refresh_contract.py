"""Provider responses and cleanup failures cannot undo durable credential ownership."""

import asyncio
from copy import deepcopy
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from database import redis_db
from models.mcp_client import McpCredentialError, RefreshClaim
from tests.unit.test_mcp_client_token_persistence import connection  # noqa: F401 -- shared strict-store fixture
from utils import mcp_client, mcp_token_refresh

URL = 'https://mcp.example/http'
PRIVATE = 'private-provider-response-and-token'


def stored_tokens(store):
    return store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']


@pytest.mark.parametrize('expires_in', [None, 0, -1, 'invalid', 'nan', 'inf', {}, 30, '90'])
@pytest.mark.asyncio
async def test_expiry_is_replaced_only_by_a_positive_finite_provider_lifetime(connection, monkeypatch, expires_in):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    stored_tokens(store)['expires_at'] = tokens['expires_at'] = 1
    now = time.time()
    monkeypatch.setattr(mcp_token_refresh, 'time', SimpleNamespace(time=lambda: now, monotonic=time.monotonic))
    monkeypatch.setattr(
        mcp_client,
        'refresh_oauth_token',
        AsyncMock(
            return_value={'access_token': 'next-access', 'refresh_token': 'next-refresh', 'expires_in': expires_in}
        ),
    )
    assert await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0') == 'next-access'
    saved = stored_tokens(store)
    assert saved == tokens and saved['refresh_token'] == 'next-refresh'
    if expires_in in (30, '90'):
        assert saved['expires_at'] == now + float(expires_in)
    else:
        assert 'expires_at' not in saved
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh'] is None


@pytest.mark.parametrize('returned_refresh', [None, ''])
@pytest.mark.asyncio
async def test_provider_without_rotation_preserves_refresh_token_and_oauth_bindings(
    connection, monkeypatch, returned_refresh
):
    store, _, _ = connection
    stored_tokens(store).update({'client_secret': 'client-secret', 'redirect_uri': 'https://omi.example/callback'})
    tokens = deepcopy(stored_tokens(store))
    monkeypatch.setattr(
        mcp_client,
        'refresh_oauth_token',
        AsyncMock(return_value={'access_token': 'next', 'refresh_token': returned_refresh}),
    )
    await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0')
    assert stored_tokens(store) == {**tokens, 'refresh_token': 'refresh-0'}
    assert tokens['client_secret'] == 'client-secret' and tokens['redirect_uri'] == 'https://omi.example/callback'
    mcp_client.refresh_oauth_token.assert_awaited_once_with(
        'https://issuer.example/token', 'refresh-0', 'client', 'client-secret'
    )


@pytest.mark.parametrize('access_token', [None, '', 42, {}, []])
@pytest.mark.asyncio
async def test_malformed_success_never_replaces_credentials_or_leaves_a_lease(
    connection, monkeypatch, access_token, caplog
):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    before = deepcopy(tokens)
    monkeypatch.setattr(
        mcp_client,
        'refresh_oauth_token',
        AsyncMock(return_value={'access_token': access_token, 'refresh_token': PRIVATE}),
    )
    with pytest.raises(McpCredentialError, match='did not return an access token') as error:
        await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0')
    assert tokens == stored_tokens(store) == before
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh'] is None
    redis_db.delete_app_cache_by_id.assert_not_called()
    assert PRIVATE not in str(error.value) + caplog.text


@pytest.mark.asyncio
async def test_stale_sibling_reloads_committed_credentials_without_refresh_or_cache_write(connection):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    stored_tokens(store).update({'access_token': 'already-saved', 'refresh_token': 'already-rotated'})
    assert await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0') == 'already-saved'
    assert tokens == stored_tokens(store)
    mcp_client.refresh_oauth_token.assert_not_awaited()
    redis_db.delete_app_cache_by_id.assert_not_called()
    assert all(not transaction.updates for transaction in store.transactions)


@pytest.mark.asyncio
async def test_failed_cache_invalidation_does_not_lose_rotation_or_reuse_its_refresh_token(
    connection, monkeypatch, caplog
):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    stale_sibling = deepcopy(tokens)
    cache = MagicMock(side_effect=RuntimeError(PRIVATE))
    monkeypatch.setattr(redis_db, 'delete_app_cache_by_id', cache)
    with pytest.raises(McpCredentialError) as error:
        await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0')
    assert tokens == stored_tokens(store)
    assert tokens['refresh_token'] == 'refresh-1'
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh'] is None
    assert await mcp_token_refresh.refresh_mcp_access_token('app', URL, stale_sibling, 'access-0') == 'access-1'
    assert stale_sibling == tokens
    mcp_client.refresh_oauth_token.assert_awaited_once()
    cache.assert_called_once_with('app')
    assert PRIVATE not in str(error.value) + caplog.text


@pytest.mark.asyncio
async def test_provider_and_release_failure_keep_credentials_fenced_without_secret_leak(
    connection, monkeypatch, caplog
):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    monkeypatch.setattr(mcp_client, 'refresh_oauth_token', AsyncMock(side_effect=RuntimeError(PRIVATE)))
    monkeypatch.setattr(mcp_token_refresh, 'release_refresh', MagicMock(side_effect=RuntimeError(PRIVATE)))
    with pytest.raises(McpCredentialError) as error:
        await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0')
    assert tokens == stored_tokens(store)
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh']['owner']
    redis_db.delete_app_cache_by_id.assert_not_called()
    assert PRIVATE not in str(error.value) + caplog.text


@pytest.mark.asyncio
async def test_waiter_adopts_completed_owner_tokens_without_releasing_another_lease(connection, monkeypatch):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    current = {**tokens, 'access_token': 'saved', 'refresh_token': 'rotated'}
    claim = MagicMock(side_effect=[RefreshClaim('busy', {}), RefreshClaim('current', current)])
    release = MagicMock()
    sleep = AsyncMock()
    monkeypatch.setattr(mcp_token_refresh, 'claim_refresh', claim)
    monkeypatch.setattr(mcp_token_refresh, 'release_refresh', release)
    monkeypatch.setattr(
        mcp_token_refresh, 'asyncio', SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError)
    )
    assert await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0') == 'saved'
    assert tokens == current and claim.call_count == 2
    sleep.assert_awaited_once_with(0.1)
    release.assert_not_called()
    mcp_client.refresh_oauth_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_release_the_active_owners_lease(connection, monkeypatch):
    store, _, _ = connection
    tokens = deepcopy(stored_tokens(store))
    release = MagicMock()
    monkeypatch.setattr(mcp_token_refresh, 'claim_refresh', MagicMock(return_value=RefreshClaim('busy', {})))
    monkeypatch.setattr(mcp_token_refresh, 'release_refresh', release)
    monkeypatch.setattr(
        mcp_token_refresh,
        'asyncio',
        SimpleNamespace(sleep=AsyncMock(side_effect=asyncio.CancelledError), CancelledError=asyncio.CancelledError),
    )
    with pytest.raises(asyncio.CancelledError):
        await mcp_token_refresh.refresh_mcp_access_token('app', URL, tokens, 'access-0')
    release.assert_not_called()
    mcp_client.refresh_oauth_token.assert_not_awaited()
