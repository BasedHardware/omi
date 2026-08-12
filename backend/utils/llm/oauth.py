import base64
import json
import time
from typing import Any

import httpx

from database import llm_oauth as llm_oauth_db


class LLMOAuthError(Exception):
    pass


_PROVIDERS = {
    'chatgpt': {
        'client_id': 'app_EMoamEEZ73f0CkXaXp7hrann',
        'token_url': 'https://auth.openai.com/oauth/token',
    },
    'grok': {
        'client_id': 'b1a00492-073a-47ea-816f-4c329264a828',
        'token_url': 'https://auth.x.ai/oauth2/token',
    },
}


def supported_provider(provider: str) -> bool:
    return provider in _PROVIDERS


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
    return _credential(provider, payload)


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
    config = _PROVIDERS[credential_provider]
    try:
        response = httpx.post(
            config['token_url'],
            data={
                'grant_type': 'refresh_token',
                'client_id': config['client_id'],
                'refresh_token': credential['refresh_token'],
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
    refreshed = _credential(credential_provider, payload, credential['refresh_token'])
    llm_oauth_db.save_credential(uid, credential_provider, refreshed)
    return {'provider': credential_provider, **refreshed}
