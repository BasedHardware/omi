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
