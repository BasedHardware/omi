"""Credential writes are fenced by the current app, credentials and refresh owner."""

from copy import deepcopy

import pytest

from models.mcp_client import McpCredentialError

from database import mcp_client_credentials as credentials
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

URL = 'https://mcp.example/http'
TOKENS = {
    'access_token': 'a0',
    'refresh_token': 'r0',
    'token_endpoint': 'https://issuer.example/token',
    'client_id': 'c',
}
NEXT = {**TOKENS, 'access_token': 'a1', 'refresh_token': 'r1', 'expires_at': 1000}


@pytest.fixture
def store():
    return StrictFirestore(
        {
            ('plugins_data', 'app'): {
                'name': 'Keep me',
                'external_integration': {'mcp_server_url': URL, 'mcp_oauth_tokens': TOKENS, 'other': 'keep'},
            }
        }
    )


def claim(store, owner='worker', now=100, tokens=TOKENS, rejected='a0'):
    return credentials.claim_refresh('app', URL, tokens, rejected, owner, now=now, firestore_client=store)


def complete(store, owner='worker', now=101):
    credentials.complete_refresh('app', URL, TOKENS, owner, NEXT, now=now, firestore_client=store)


def test_lease_admits_one_owner_and_preserves_unrelated_fields(store):
    assert claim(store).state == 'claimed'
    assert claim(store, owner='other').state == 'busy'
    complete(store)
    row = store.rows[('plugins_data', 'app')]
    assert row['name'] == 'Keep me'
    assert row['external_integration']['other'] == 'keep'
    assert row['external_integration']['mcp_oauth_tokens'] == NEXT
    assert row['mcp_oauth_refresh'] is None
    current = claim(store, owner='other')
    assert current.state == 'current' and current.tokens == NEXT


def test_long_stale_cache_refreshes_the_latest_expired_credentials(store):
    store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens'] = {**NEXT, 'expires_at': 99}
    result = claim(store)
    assert result.state == 'claimed' and result.tokens['refresh_token'] == 'r1'


def test_expired_owner_cannot_commit_or_release_a_successor_lease(store):
    claim(store)
    assert claim(store, owner='successor', now=161).state == 'claimed'
    with pytest.raises(McpCredentialError):
        complete(store, now=162)
    credentials.release_refresh('app', TOKENS, 'worker', firestore_client=store)
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh']['owner'] == 'successor'
    complete(store, owner='successor', now=162)


@pytest.mark.parametrize(
    'field,value',
    [
        ('access_token', 'reconnected'),
        ('refresh_token', 'reconnected'),
        ('client_id', 'new-client'),
        ('client_secret', 'new-secret'),
        ('redirect_uri', 'https://other.example/callback'),
        ('token_endpoint', 'https://other.example/token'),
        ('code_verifier', 'new-code'),
    ],
)
def test_refresh_cannot_overwrite_a_reconnected_integration(store, field, value):
    claim(store)
    row = store.rows[('plugins_data', 'app')]
    row['external_integration']['mcp_oauth_tokens'][field] = value
    before = deepcopy(row)
    with pytest.raises(McpCredentialError):
        complete(store)
    assert row == before


def test_refresh_cannot_recreate_a_deleted_integration(store):
    claim(store)
    store.rows.pop(('plugins_data', 'app'))
    with pytest.raises(McpCredentialError):
        complete(store)
    credentials.release_refresh('app', TOKENS, 'worker', firestore_client=store)
    assert not store.rows


def test_removed_integration_cannot_acquire_a_refresh_lease(store):
    store.rows.clear()
    with pytest.raises(McpCredentialError, match='integration was removed'):
        claim(store)
    assert not store.rows


def test_server_reconfiguration_and_missing_authorization_are_rejected(store):
    row = store.rows[('plugins_data', 'app')]
    row['external_integration']['mcp_server_url'] = 'https://other.example/mcp'
    with pytest.raises(McpCredentialError):
        claim(store)
    row['external_integration']['mcp_server_url'] = URL
    row['external_integration']['mcp_oauth_tokens'] = None
    with pytest.raises(McpCredentialError):
        claim(store)


def test_release_clears_only_the_owned_claim(store):
    claim(store)
    credentials.release_refresh('app', TOKENS, 'worker', firestore_client=store)
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh'] is None
    assert claim(store, owner='retry').state == 'claimed'


@pytest.mark.parametrize('now,state', [(159.999, 'busy'), (160, 'claimed'), (160.001, 'claimed')])
def test_lease_takeover_has_an_exact_expiry_boundary(store, now, state):
    assert claim(store).state == 'claimed'
    assert claim(store, owner='successor', now=now).state == state
    expected_owner = 'worker' if state == 'busy' else 'successor'
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh']['owner'] == expected_owner


@pytest.mark.parametrize('now', [160, 161])
def test_expired_owner_cannot_commit_even_without_a_successor(store, now):
    claim(store)
    before = deepcopy(store.rows)
    with pytest.raises(McpCredentialError):
        complete(store, now=now)
    assert store.rows == before


@pytest.mark.parametrize('field', ['access_token', 'refresh_token', 'token_endpoint', 'client_id'])
@pytest.mark.parametrize('value', [None, '', 42])
def test_incomplete_authorization_never_creates_a_lease(store, field, value):
    row = store.rows[('plugins_data', 'app')]
    row['external_integration']['mcp_oauth_tokens'][field] = value
    expected = deepcopy(row['external_integration']['mcp_oauth_tokens'])
    before = deepcopy(store.rows)
    with pytest.raises(McpCredentialError, match='authorization is unavailable'):
        claim(store, tokens=expected)
    assert store.rows == before


@pytest.mark.parametrize('expires_at,state', [(99, 'claimed'), (100, 'claimed'), (101, 'current'), (None, 'current')])
def test_stale_caller_uses_authoritative_token_expiry(store, expires_at, state):
    current = {**NEXT, 'expires_at': expires_at}
    store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens'] = current
    result = claim(store)
    assert result.state == state
    assert result.tokens == current


def test_completion_preserves_metadata_changed_while_the_provider_is_running(store):
    claim(store)
    row = store.rows[('plugins_data', 'app')]
    row['name'] = 'Renamed during refresh'
    row['external_integration']['other'] = {'new': 'metadata'}
    row['external_integration']['webhook_url'] = 'https://hooks.example/new'
    complete(store)
    assert row['name'] == 'Renamed during refresh'
    assert row['external_integration'] == {
        'mcp_server_url': URL,
        'mcp_oauth_tokens': NEXT,
        'other': {'new': 'metadata'},
        'webhook_url': 'https://hooks.example/new',
    }


def test_release_with_wrong_credentials_cannot_clear_an_owned_lease(store):
    claim(store)
    before = deepcopy(store.rows)
    credentials.release_refresh('app', NEXT, 'worker', firestore_client=store)
    assert store.rows == before


def test_returned_credentials_are_detached_from_storage(store):
    result = claim(store)
    result.tokens['refresh_token'] = 'caller-mutation'
    assert store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens'] == TOKENS


def test_leases_are_isolated_by_app_even_with_identical_credentials(store):
    store.rows[('plugins_data', 'other-app')] = deepcopy(store.rows[('plugins_data', 'app')])
    assert claim(store).state == 'claimed'
    assert (
        credentials.claim_refresh('other-app', URL, TOKENS, 'a0', 'other', now=100, firestore_client=store).state
        == 'claimed'
    )
    complete(store)
    other = store.rows[('plugins_data', 'other-app')]
    assert other['external_integration']['mcp_oauth_tokens'] == TOKENS
    assert other['mcp_oauth_refresh']['owner'] == 'other'
