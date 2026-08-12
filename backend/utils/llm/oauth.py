import base64
import json
import threading
import time
from typing import Any, TypedDict

import httpx

from database import llm_oauth as llm_oauth_db


class LLMOAuthError(Exception):
    pass


class ProviderConfiguration(TypedDict):
    client_id: str
    authorization_url: str
    redirect_uri: str
    scope: str
    authorization_parameters: dict[str, str]
    token_url: str
    models_url: str


_PROVIDERS: dict[str, ProviderConfiguration] = {
    'chatgpt': {
        'client_id': 'app_EMoamEEZ73f0CkXaXp7hrann',
        'authorization_url': 'https://auth.openai.com/oauth/authorize',
        'redirect_uri': 'http://localhost:1455/auth/callback',
        'scope': 'openid profile email offline_access',
        'authorization_parameters': {
            'id_token_add_organizations': 'true',
            'codex_cli_simplified_flow': 'true',
            'originator': 'omi',
        },
        'token_url': 'https://auth.openai.com/oauth/token',
        'models_url': 'https://chatgpt.com/backend-api/codex/models?client_version=0.142.5',
    },
    'grok': {
        'client_id': 'b1a00492-073a-47ea-816f-4c329264a828',
        'authorization_url': 'https://auth.x.ai/oauth2/authorize',
        'redirect_uri': 'http://127.0.0.1:56121/callback',
        'scope': 'openid profile email offline_access grok-cli:access api:access',
        'authorization_parameters': {},
        'token_url': 'https://auth.x.ai/oauth2/token',
        'models_url': 'https://api.x.ai/v1/models',
    },
}
_refresh_locks: dict[tuple[str, str], threading.Lock] = {}
_refresh_locks_lock = threading.Lock()


def supported_provider(provider: str) -> bool:
    return provider in _PROVIDERS


def oauth_configuration(provider: str) -> dict[str, Any] | None:
    config = _PROVIDERS.get(provider)
    if config is None:
        return None
    return {
        'authorization_url': config['authorization_url'],
        'client_id': config['client_id'],
        'redirect_uri': config['redirect_uri'],
        'scope': config['scope'],
        'authorization_parameters': config['authorization_parameters'],
    }


def _account_id(access_token: str) -> str | None:
    parts = access_token.split('.')
    if len(parts) < 2:
        return None
    payload = parts[1] + '=' * (-len(parts[1]) % 4)
    try:
        value = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    auth_claim = value.get('https://api.openai.com/auth')
    if isinstance(auth_claim, dict) and isinstance(auth_claim.get('chatgpt_account_id'), str):
        return auth_claim['chatgpt_account_id']
    return value.get('chatgpt_account_id') if isinstance(value.get('chatgpt_account_id'), str) else None


def _credential(provider: str, payload: dict[str, Any], refresh_token: str | None = None) -> dict[str, Any]:
    access_token = payload.get('access_token')
    next_refresh_token = payload.get('refresh_token') or refresh_token
    if not isinstance(access_token, str) or not isinstance(next_refresh_token, str):
        raise LLMOAuthError('Provider did not return a refreshable credential')
    expires_in = payload.get('expires_in', 3600)
    if not isinstance(expires_in, int | float):
        raise LLMOAuthError('Provider returned an invalid expiration')
    credential: dict[str, Any] = {
        'access_token': access_token,
        'refresh_token': next_refresh_token,
        'expires_at': time.time() + expires_in,
    }
    if provider == 'chatgpt':
        credential['account_id'] = _account_id(access_token)
    return credential


def _available_models(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    values = payload.get('models') or payload.get('data') or payload.get('items')
    if not isinstance(values, list):
        return []
    models: list[str] = []
    for value in values:
        model = (
            value
            if isinstance(value, str)
            else next(
                (
                    value.get(name)
                    for name in ('slug', 'id', 'model', 'name')
                    if isinstance(value, dict) and isinstance(value.get(name), str)
                ),
                None,
            )
        )
        if isinstance(model, str) and model and model not in models:
            models.append(model)
    return models


def verify_credential(provider: str, credential: dict[str, Any]) -> dict[str, Any]:
    config = _PROVIDERS.get(provider)
    if config is None:
        raise LLMOAuthError('Unsupported LLM OAuth provider')
    headers = {'authorization': f"Bearer {credential['access_token']}"}
    if provider == 'chatgpt':
        account_id = credential.get('account_id')
        if not isinstance(account_id, str) or not account_id:
            raise LLMOAuthError('ChatGPT did not return an account identity')
        headers.update(
            {
                'chatgpt-account-id': account_id,
                'openai-beta': 'responses=experimental',
                'originator': 'codex_cli_rs',
            }
        )
    try:
        response = httpx.get(config['models_url'], headers=headers, timeout=15.0)
    except httpx.HTTPError as error:
        raise LLMOAuthError('Provider could not verify model access') from error
    if response.status_code >= 400:
        raise LLMOAuthError('Provider account does not have model access')
    try:
        models = _available_models(response.json())
    except ValueError as error:
        raise LLMOAuthError('Provider returned an invalid model response') from error
    if not models:
        raise LLMOAuthError('Provider account does not have an available model')
    preferred = 'gpt-5.4-mini' if provider == 'chatgpt' else 'grok-4.3'
    credential['model'] = preferred if preferred in models else models[0]
    return credential


def exchange_authorization_code(provider: str, code: str, code_verifier: str, redirect_uri: str) -> dict[str, Any]:
    config = _PROVIDERS.get(provider)
    if config is None:
        raise LLMOAuthError('Unsupported LLM OAuth provider')
    try:
        response = httpx.post(
            config['token_url'],
            data={
                'grant_type': 'authorization_code',
                'client_id': config['client_id'],
                'code': code,
                'code_verifier': code_verifier,
                'redirect_uri': redirect_uri,
            },
            timeout=15.0,
        )
    except httpx.HTTPError as error:
        raise LLMOAuthError('Provider could not complete sign-in') from error
    if response.status_code >= 400:
        raise LLMOAuthError('Provider rejected the authorization code')
    try:
        payload = response.json()
    except ValueError as error:
        raise LLMOAuthError('Provider returned an invalid token response') from error
    if not isinstance(payload, dict):
        raise LLMOAuthError('Provider returned an invalid token response')
    return verify_credential(provider, _credential(provider, payload))


def _refresh_lock(uid: str, provider: str) -> threading.Lock:
    with _refresh_locks_lock:
        return _refresh_locks.setdefault((uid, provider), threading.Lock())


def get_credential(uid: str, provider: str | None = None) -> dict[str, Any] | None:
    credential = llm_oauth_db.get_credential(uid, provider)
    if credential is None:
        return None
    expires_at = credential.get('expires_at')
    if isinstance(expires_at, int | float) and expires_at > time.time() + 60:
        return credential
    credential_provider = credential.get('provider')
    if not isinstance(credential_provider, str) or credential_provider not in _PROVIDERS:
        raise LLMOAuthError('Provider session is invalid; reconnect it in Settings')
    with _refresh_lock(uid, credential_provider):
        latest = llm_oauth_db.get_credential(uid, credential_provider)
        if latest is None:
            return None
        latest_expires_at = latest.get('expires_at')
        if isinstance(latest_expires_at, int | float) and latest_expires_at > time.time() + 60:
            return latest
        config = _PROVIDERS[credential_provider]
        try:
            response = httpx.post(
                config['token_url'],
                data={
                    'grant_type': 'refresh_token',
                    'client_id': config['client_id'],
                    'refresh_token': latest['refresh_token'],
                },
                timeout=15.0,
            )
        except httpx.HTTPError as error:
            raise LLMOAuthError('Provider session could not refresh') from error
        if response.status_code >= 400:
            raise LLMOAuthError('Provider session expired; reconnect it in Settings')
        try:
            payload = response.json()
        except ValueError as error:
            raise LLMOAuthError('Provider returned an invalid refresh response') from error
        if not isinstance(payload, dict):
            raise LLMOAuthError('Provider returned an invalid refresh response')
        refreshed = _credential(credential_provider, payload, latest['refresh_token'])
        if isinstance(latest.get('model'), str):
            refreshed['model'] = latest['model']
        generation = latest.get('generation')
        if not isinstance(generation, str) or not llm_oauth_db.save_refreshed_credential(
            uid, credential_provider, refreshed, generation
        ):
            return None
        return {'provider': credential_provider, **refreshed}
