import base64
import json
from unittest.mock import Mock, patch

import pytest

from utils.llm import oauth


def _token(account_id: str) -> str:
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({'https://api.openai.com/auth': {'chatgpt_account_id': account_id}}).encode()
        )
        .decode()
        .rstrip('=')
    )
    return f'header.{payload}.signature'


def test_exchange_chatgpt_code_uses_pkce_and_extracts_account_id():
    response = Mock(status_code=200)
    response.json.return_value = {
        'access_token': _token('acct-1'),
        'refresh_token': 'refresh-1',
        'expires_in': 3600,
    }
    with patch.object(oauth.httpx, 'post', return_value=response) as post:
        credential = oauth.exchange_authorization_code(
            'chatgpt', 'code-1', 'v' * 43, 'http://localhost:1455/auth/callback'
        )
    assert credential['account_id'] == 'acct-1'
    assert credential['refresh_token'] == 'refresh-1'
    assert post.call_args.kwargs['data']['code_verifier'] == 'v' * 43


def test_exchange_rejects_a_non_refreshable_provider_response():
    response = Mock(status_code=200)
    response.json.return_value = {'access_token': 'access-only'}
    with patch.object(oauth.httpx, 'post', return_value=response):
        with pytest.raises(oauth.LLMOAuthError, match='refreshable'):
            oauth.exchange_authorization_code('grok', 'code-1', 'v' * 43, 'http://127.0.0.1:56121/callback')


def test_expired_credential_refreshes_and_persists_the_replacement():
    response = Mock(status_code=200)
    response.json.return_value = {'access_token': 'access-2', 'refresh_token': 'refresh-2', 'expires_in': 3600}
    stored = {
        'provider': 'grok',
        'access_token': 'access-1',
        'refresh_token': 'refresh-1',
        'expires_at': 0,
        'account_id': None,
    }
    with patch.object(oauth.users_db, 'get_llm_oauth_credential', return_value=stored), patch.object(
        oauth.users_db, 'save_llm_oauth_credential'
    ) as save, patch.object(oauth.httpx, 'post', return_value=response) as post:
        credential = oauth.get_credential('user-1')
    assert credential is not None
    assert credential['access_token'] == 'access-2'
    assert post.call_args.kwargs['data']['grant_type'] == 'refresh_token'
    save.assert_called_once()


def test_chatgpt_oauth_client_uses_the_codex_responses_surface():
    from utils.llm.clients import _create_llm_oauth_client

    client = _create_llm_oauth_client({'provider': 'chatgpt', 'access_token': _token('acct-1'), 'account_id': 'acct-1'})
    assert client.openai_api_base == 'https://chatgpt.com/backend-api/codex'
    assert client.use_responses_api is True
    assert client.default_headers['chatgpt-account-id'] == 'acct-1'


def test_get_llm_uses_the_selected_oauth_provider_without_a_key_header():
    from utils.llm import clients

    credential = {'provider': 'grok', 'access_token': 'access-1', 'refresh_token': 'refresh-1'}
    with patch.object(clients, 'get_byok_key', return_value=None), patch.object(
        clients, 'get_byok_uid', return_value='user-1'
    ), patch.object(clients, 'get_byok_llm_provider', return_value='grok'), patch.object(
        clients, 'get_llm_oauth_credential', return_value=credential
    ):
        client = clients.get_llm('conv_structure')
    assert client.openai_api_base == 'https://api.x.ai/v1'
    assert client.model_name == 'grok-4.3'


def test_get_llm_does_not_fall_back_to_omi_when_oauth_refresh_fails():
    from utils.llm import clients

    with patch.object(clients, 'get_byok_key', return_value=None), patch.object(
        clients, 'get_byok_uid', return_value='user-1'
    ), patch.object(clients, 'get_byok_llm_provider', return_value='chatgpt'), patch.object(
        clients, 'get_llm_oauth_credential', side_effect=oauth.LLMOAuthError('expired')
    ), patch.object(
        clients, 'get_default_client'
    ) as default_client:
        with pytest.raises(RuntimeError, match='reconnect'):
            clients.get_llm('conv_structure')
    default_client.assert_not_called()
