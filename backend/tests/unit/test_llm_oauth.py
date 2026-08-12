import base64
import asyncio
import json
from unittest.mock import Mock, patch

import pytest

from database import llm_oauth as llm_oauth_db
from utils import encryption
from utils.llm import clients
from utils.llm import oauth
from utils.llm.clients import _create_llm_oauth_client


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
    models = Mock(status_code=200)
    models.json.return_value = {'models': [{'slug': 'gpt-5.4-mini'}]}
    with patch.object(oauth.httpx, 'post', return_value=response) as post, patch.object(
        oauth.httpx, 'get', return_value=models
    ) as get:
        credential = oauth.exchange_authorization_code(
            'chatgpt', 'code-1', 'v' * 43, 'http://localhost:1455/auth/callback'
        )
    assert credential['account_id'] == 'acct-1'
    assert credential['refresh_token'] == 'refresh-1'
    assert credential['model'] == 'gpt-5.4-mini'
    assert post.call_args.kwargs['data']['code_verifier'] == 'v' * 43
    assert get.call_args.args[0].endswith('/models?client_version=0.142.5')
    assert get.call_args.kwargs['headers']['chatgpt-account-id'] == 'acct-1'


def test_exchange_rejects_a_token_without_provider_model_access():
    token = Mock(status_code=200)
    token.json.return_value = {'access_token': _token('acct-1'), 'refresh_token': 'refresh-1', 'expires_in': 3600}
    models = Mock(status_code=403)
    with patch.object(oauth.httpx, 'post', return_value=token), patch.object(oauth.httpx, 'get', return_value=models):
        with pytest.raises(oauth.LLMOAuthError, match='model access'):
            oauth.exchange_authorization_code('chatgpt', 'code-1', 'v' * 43, 'http://localhost:1455/auth/callback')


def test_oauth_configuration_keeps_provider_connection_details_server_owned():
    configuration = oauth.oauth_configuration('chatgpt')
    assert configuration is not None
    assert configuration['redirect_uri'] == 'http://localhost:1455/auth/callback'
    assert configuration['authorization_parameters']['originator'] == 'omi'


def test_connection_status_includes_the_server_owned_provider_configuration(monkeypatch):
    from routers import llm_oauth

    async def run_blocking(_executor, function, *args, **_kwargs):
        return function(*args)

    monkeypatch.setattr(llm_oauth, 'run_blocking', run_blocking)
    monkeypatch.setattr(llm_oauth.llm_oauth_db, 'get_status', lambda _uid: {'connected': [], 'selected_provider': None})

    status = asyncio.run(llm_oauth._status_response('user-1'))

    assert status['configurations']['grok']['redirect_uri'] == 'http://127.0.0.1:56121/callback'


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
        'generation': 'generation-1',
    }
    with patch.object(oauth.llm_oauth_db, 'get_credential', return_value=stored), patch.object(
        oauth.llm_oauth_db, 'save_refreshed_credential', return_value=True
    ) as save, patch.object(oauth.httpx, 'post', return_value=response) as post:
        credential = oauth.get_credential('user-1')
    assert credential is not None
    assert credential['access_token'] == 'access-2'
    assert post.call_args.kwargs['data']['grant_type'] == 'refresh_token'
    save.assert_called_once()


def test_refresh_does_not_restore_a_credential_disconnected_during_the_provider_request():
    response = Mock(status_code=200)
    response.json.return_value = {'access_token': 'access-2', 'refresh_token': 'refresh-2', 'expires_in': 3600}
    stored = {
        'provider': 'grok',
        'access_token': 'access-1',
        'refresh_token': 'refresh-1',
        'expires_at': 0,
        'account_id': None,
        'generation': 'generation-1',
    }
    with patch.object(oauth.llm_oauth_db, 'get_credential', return_value=stored), patch.object(
        oauth.llm_oauth_db, 'save_refreshed_credential', return_value=False
    ) as save, patch.object(oauth.httpx, 'post', return_value=response):
        assert oauth.get_credential('user-1') is None
    save.assert_called_once()


def test_conditional_refresh_write_leaves_a_disconnected_credential_deleted():
    class Snapshot:
        def to_dict(self):
            return {'llm_oauth': {}}

    class UserRef:
        def get(self, transaction):
            return Snapshot()

    class Transaction:
        updates: list[dict] = []

        def update(self, _ref, update):
            self.updates.append(update)

    class Client:
        def __init__(self):
            self.transaction_instance = Transaction()

        def collection(self, _name):
            return self

        def document(self, _uid):
            return UserRef()

        def transaction(self):
            return self.transaction_instance

    client = Client()
    credential = {'access_token': 'access-2', 'refresh_token': 'refresh-2', 'expires_at': 4_000_000_000}
    with patch.object(llm_oauth_db, 'transactional', side_effect=lambda apply: apply), patch.object(
        encryption, 'encrypt', side_effect=lambda value, _uid: f'encrypted:{value}'
    ):
        assert not llm_oauth_db.save_refreshed_credential(
            'user-1', 'grok', credential, 'generation-1', firestore_client=client
        )
    assert client.transaction_instance.updates == []


def test_oauth_connect_and_disconnect_write_through_firestore_transactions():
    class Snapshot:
        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return self.data

    class UserRef:
        def __init__(self, data):
            self.data = data
            self.reads = 0

        def get(self, transaction):
            self.reads += 1
            return Snapshot(self.data)

    class Transaction:
        def __init__(self):
            self.sets: list[dict] = []
            self.updates: list[dict] = []

        def set(self, _ref, values, merge):
            assert merge
            self.sets.append(values)

        def update(self, _ref, values):
            self.updates.append(values)

    class Client:
        def __init__(self, data):
            self.user_ref = UserRef(data)
            self.transaction_instances: list[Transaction] = []

        def collection(self, _name):
            return self

        def document(self, _uid):
            return self.user_ref

        def transaction(self):
            transaction = Transaction()
            self.transaction_instances.append(transaction)
            return transaction

    credential = {'access_token': 'access-2', 'refresh_token': 'refresh-2', 'expires_at': 4_000_000_000}
    client = Client({'llm_oauth': {'chatgpt': {'generation': 'generation-1'}}, 'llm_oauth_provider': 'chatgpt'})
    with patch.object(llm_oauth_db, 'transactional', side_effect=lambda apply: apply), patch.object(
        encryption, 'encrypt', side_effect=lambda value, _uid: f'encrypted:{value}'
    ):
        llm_oauth_db.save_credential('user-1', 'grok', credential, firestore_client=client)
        llm_oauth_db.delete_credential('user-1', 'chatgpt', firestore_client=client)
    assert client.user_ref.reads == 2
    assert client.transaction_instances[0].sets[0]['llm_oauth_provider'] == 'grok'
    assert 'llm_oauth.chatgpt' in client.transaction_instances[1].updates[0]


def test_unexpired_credential_does_not_refresh():
    stored = {
        'provider': 'grok',
        'access_token': 'access-1',
        'refresh_token': 'refresh-1',
        'expires_at': 4_000_000_000,
        'account_id': None,
    }
    with patch.object(oauth.llm_oauth_db, 'get_credential', return_value=stored), patch.object(
        oauth.httpx, 'post'
    ) as post:
        assert oauth.get_credential('user-1') is stored
    post.assert_not_called()


def test_chatgpt_oauth_client_uses_the_codex_responses_surface():
    with patch.object(clients, '_cached_openai_chat') as create_client:
        _create_llm_oauth_client({'provider': 'chatgpt', 'access_token': _token('acct-1'), 'account_id': 'acct-1'})
    assert create_client.call_args.args[:2] == ('gpt-5.4-mini', _token('acct-1'))
    assert create_client.call_args.args[2]['base_url'] == 'https://chatgpt.com/backend-api/codex'
    assert create_client.call_args.args[2]['use_responses_api'] is True
    assert create_client.call_args.args[2]['default_headers']['chatgpt-account-id'] == 'acct-1'
    assert create_client.call_args.args[2]['default_headers']['originator'] == 'codex_cli_rs'


def test_chatgpt_oauth_client_uses_the_model_verified_at_connection_time():
    with patch.object(clients, '_cached_openai_chat') as create_client:
        _create_llm_oauth_client({'provider': 'chatgpt', 'access_token': _token('acct-1'), 'model': 'gpt-5.5'})
    assert create_client.call_args.args[0] == 'gpt-5.5'


def test_grok_oauth_client_uses_xai_surface():
    with patch.object(clients, '_cached_openai_chat') as create_client:
        _create_llm_oauth_client({'provider': 'grok', 'access_token': 'access-1'})
    assert create_client.call_args.args[:2] == ('grok-4.3', 'access-1')
    assert create_client.call_args.args[2]['base_url'] == 'https://api.x.ai/v1'


def test_get_llm_uses_the_selected_oauth_provider_without_a_key_header():
    credential = {'provider': 'grok', 'access_token': 'access-1', 'refresh_token': 'refresh-1'}
    with patch.object(clients, 'get_byok_key', return_value=None), patch.object(
        clients, 'get_byok_uid', return_value='user-1'
    ), patch.object(clients, 'get_byok_llm_provider', return_value='grok'), patch.object(
        clients, 'get_byok_oauth_credential', return_value=credential
    ), patch.object(
        clients, '_create_llm_oauth_client'
    ) as create_client:
        client = clients.get_llm('conv_structure')
    assert client is create_client.return_value
    assert create_client.call_args.args == (credential, False, 'conv_structure')


def test_get_llm_uses_oauth_for_chat_agent_when_direct_provider_mode_is_enabled():
    credential = {'provider': 'chatgpt', 'access_token': 'access-1', 'refresh_token': 'refresh-1'}
    with patch.object(clients, 'should_route_features_through_gateway', return_value=False), patch.object(
        clients, 'get_byok_key', return_value=None
    ), patch.object(clients, 'get_byok_oauth_credential', return_value=credential), patch.object(
        clients, '_create_llm_oauth_client'
    ) as create_client:
        client = clients.get_llm('chat_agent')
    assert client is create_client.return_value
    assert create_client.call_args.args == (credential, False, 'chat_agent')


def test_get_llm_does_not_fall_back_to_omi_when_oauth_refresh_fails():
    with patch.object(clients, 'get_byok_key', return_value=None), patch.object(
        clients, 'get_byok_uid', return_value='user-1'
    ), patch.object(clients, 'get_byok_llm_provider', return_value='chatgpt'), patch.object(
        clients, 'get_byok_oauth_credential', return_value=None
    ), patch.object(
        clients, 'get_llm_oauth_credential', side_effect=oauth.LLMOAuthError('expired')
    ), patch.object(
        clients, 'get_default_client'
    ) as default_client:
        with pytest.raises(RuntimeError, match='reconnect'):
            clients.get_llm('conv_structure')
    default_client.assert_not_called()
